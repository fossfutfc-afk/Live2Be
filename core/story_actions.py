"""STORY 域动作 — 羁绊剧情（Bond Story）场景契约。

动作集（v1, 单一动作 APPROVAL_AUTO）:
    story_scene   一个剧情场景（叙事段落 + 选项 + 是否收尾）

与 MMT 域的关系: momotalk 用 mmt_ 动作在手机聊天里决策; 切进羁绊剧情后,
VN 每场景就是一条 story_scene——纯输出契约, 程序不执行任何副作用,
只解析 → 渲染 → 存档。契约 JSON 的副产物是存档 json[]（一解析器两用:
运行时解析 LLM 输出 + 读存档回放）, 见 core/DESIGN_BOND_STORY.md。

设计决策:
    - prompt_fields = {action, payload}——无 summary: 场景自身即完整输出,
      让 LLM 额外写一句话说明是纯浪费 token。
    - payload = {paragraphs, choices, is_end}, 与 core/bond_story.BondScene
      一一对应; parse_payload 只做机器侧容错 + 类型硬校验（抛 ContractError）,
      跨字段一致性（is_end=true 时 choices 必须为空）走软校验 validate 钩子。
    - 机器侧容错（仿 registry._normalize_str_list）: LLM 偶发把单段写成裸字符串
      自动包成单元素列表; choices 超 3 截断——宁缺勿错但不过度拒绝。
    - is_end 是唯一的收尾信号（替代旧文本标记【完】）——模型不再需要在自由
      文本里夹特殊标记, 结构由 JSON 字段强制。

注意: 绑定故事规则的长 prompt 在 llm/prompts/bond_story_rules.md, 这里只管 schema。
"""

from __future__ import annotations

from typing import Any

from contract import (
    StoryActionRegistry,
    ActionSpec,
    APPROVAL_AUTO,
    ContractError,
    ValidationResult,
)

# 选项数量上限（收敛分支: 至多 3 个, 全部收敛同一主线）
MAX_SCENE_CHOICES = 3

# 单场景语义校验最大重试次数（llm.chat(json_object) 内部另有 3 次语法自纠错）
MAX_SCENE_RETRIES = 3


def parse_story_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """story_scene payload 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    返回 {paragraphs: [str], choices: [str], is_end: bool}。
    """
    # ---- paragraphs: 必填, 至少 1 个非空段落 ----
    raw_paras = payload.get("paragraphs")
    if isinstance(raw_paras, str):
        raw_paras = [raw_paras]          # 单段裸字符串 → 包成单元素列表
    if not isinstance(raw_paras, list):
        raise ContractError("paragraphs 必须是字符串数组（或单个字符串）")
    paragraphs: list[str] = []
    for p in raw_paras:
        if isinstance(p, str) and p.strip():
            paragraphs.append(p.strip())
    if not paragraphs:
        raise ContractError("paragraphs 至少需要一个非空段落")

    # ---- choices: 可选, 字符串数组, 超上限截断（宁缺勿错不过度拒绝）----
    raw_choices = payload.get("choices", [])
    if isinstance(raw_choices, str):
        raw_choices = [raw_choices]
    if raw_choices is None:
        raw_choices = []
    if not isinstance(raw_choices, list):
        raise ContractError("choices 必须是字符串数组（或单个字符串）")
    choices: list[str] = []
    for c in raw_choices:
        if isinstance(c, str) and c.strip():
            choices.append(c.strip())
    choices = choices[:MAX_SCENE_CHOICES]

    # ---- is_end: bool（接受 int 0/1 强转）----
    is_end = payload.get("is_end", False)
    if isinstance(is_end, int) and is_end in (0, 1):
        is_end = bool(is_end)
    if not isinstance(is_end, bool):
        raise ContractError("is_end 必须是布尔值")

    return {"paragraphs": paragraphs, "choices": choices, "is_end": is_end}


def validate_story_scene(payload: dict[str, Any]) -> ValidationResult:
    """软校验（跨字段一致性）: 收尾场景不再出选项。"""
    if payload.get("is_end") and payload.get("choices"):
        return ValidationResult(errors=("is_end=true 时 choices 必须为空数组（收尾场景不再出选项）",))
    return ValidationResult()


def build_story_registry() -> StoryActionRegistry:
    """构建注册了全部 story 动作的注册表（动作名 story_ 前缀）。"""
    registry = StoryActionRegistry()
    registry.register(ActionSpec(
        "story_scene",
        parse_story_scene,
        APPROVAL_AUTO,
        prompt_fields=frozenset({"action", "payload"}),
        validate=validate_story_scene,
        payload_schema=(
            "payload 字段（story_scene 场景参数）:\n"
            "  paragraphs: 必填, 字符串数组——本场景的叙事段落列表。每项一个段落, 可含\n"
            "      动作描写（括号标注）, 可含长对白; 至少 1 段（空数组会被拒绝）。\n"
            "      段落之间不用手工加分隔符——数组天然分隔。\n"
            "  choices: 数组——给 sensei 的选项文本列表（1~3 个）。可省略（缺省 = 本场景\n"
            "      不提供选项, sensei 将自由输入一句话推进）。选项要有分歧感、让 sensei\n"
            "      有参与感, 但必须收敛到同一主线——无论选哪个, 剧情都走向同一结局, 只\n"
            "      影响紧接着的对白语气与细节, 不要因选项分裂出不同剧情线。\n"
            "  is_end: 布尔——是否结束剧情。**只在剧情走到自然结尾时**（约定达成、感情\n"
            "      升温到位、道别告别、夜色收场等这一幕告一段落的时刻）才设 true, 且此时\n"
            "      choices 必须为空数组 [], paragraphs 应为收尾段落。宁可及早收尾, 也不要\n"
            "      无限续写新场景。其余情况一律 false。\n"
            "约束: is_end=true 时 choices 必须为 []。字符串一律双引号。\n"
            "      每次只输出一个 story_scene 动作。"
        ),
    ))
    return registry
