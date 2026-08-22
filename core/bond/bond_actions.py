"""STORY 域动作 — 羁绊剧情（Bond Story）场景契约。

动作集（v2, 双动作全部 APPROVAL_AUTO）:
    story_scene   中段场景（叙事段落 + 选项, is_end 隐含 False）
    story_end     收尾场景（叙事段落, 无选项, is_end 隐含 True）

与 MMT 域的关系: momotalk 用 mmt_ 动作在手机聊天里决策; 切进羁绊剧情后,
VN 每场景就是一条 story_scene 或 story_end——纯输出契约, 程序不执行任何
副作用, 只解析 → 渲染 → 存档。契约 JSON 的副产物是存档 json[]（一解析器
两用: 运行时解析 LLM 输出 + 读存档回放）, 见 core/DESIGN_BOND_STORY.md。

设计决策（v2 双核升级, 2026-08-22 用户拍板）:
    - **动作集拆分**: 收尾成为一等动作 story_end, 结构上保证「收尾必无选项」
      ——is_end 不再由字段携带, 而由动作类型推导（story_scene 隐含 False,
      story_end 隐含 True）。删 validate 软校验钩子, 跨字段一致性成为结构性
      保证。story_end 的 payload 带非空 choices 会被 parse 硬拒绝（含 nudge
      「请改用 story_scene」）。
    - **残留 is_end 迁移容错**: story_scene 里残留的 is_end 字段被白名单静默
      丢弃（当作中段继续, 双层兜底照常兜住）——宁缺勿错不过度拒绝。
    - prompt_fields = {action, payload}——无 summary: 场景自身即完整输出,
      让 LLM 额外写一句话说明是纯浪费 token。
    - payload 与 core/bond_story.BondScene 一一对应; parse_payload 只做机器侧
      容错 + 类型硬校验（抛 ContractError）。
    - 机器侧容错（仿 registry._normalize_str_list）: LLM 偶发把单段写成裸字符串
      自动包成单元素列表; choices 超 3 截断——宁缺勿错但不过度拒绝。

注意: 绑定故事规则的长 prompt 在 llm/prompts/bond_story_rules.md, 这里只管 schema。
"""

from __future__ import annotations

from typing import Any

from contract import (
    StoryActionRegistry,
    ActionSpec,
    APPROVAL_AUTO,
    ContractError,
)

# 选项数量上限（收敛分支: 至多 3 个, 全部收敛同一主线）
MAX_SCENE_CHOICES = 3

# 单场景解析/执行最大重试次数（llm.chat(json_object) 内部另有 3 次语法自纠错）
MAX_SCENE_RETRIES = 3


def _parse_paragraphs(payload: dict[str, Any]) -> list[str]:
    """必填 paragraphs 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    Returns: 至少 1 个非空段落组成的列表（strip 后的干净 str）。
    """
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
    return paragraphs


def _parse_choices(payload: dict[str, Any]) -> list[str]:
    """可选 choices 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    Returns: strip 后的干净 str 列表, 截断到 MAX_SCENE_CHOICES。
    """
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
    return choices[:MAX_SCENE_CHOICES]


def _parse_beats(payload: dict[str, Any]) -> list[dict]:
    """可选 beats 白名单校验（视觉意图协议 §3, 向后兼容: 缺失 → []）。

    beats: [{text: str, emotion: str}] —— 每拍的情绪标注（per-beat）。
    结构错误（非数组/项非对象/字段非 str）→ ContractError（格式问题回灌）;
    emotion 空串 → 保留该项（下游视为缺失, 走降级, 宁缺勿错不拒绝）。
    """
    raw = payload.get("beats")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ContractError("beats 必须是数组（每项 {text, emotion}）")
    beats: list[dict] = []
    for b in raw:
        if not isinstance(b, dict):
            raise ContractError("beats 每项必须是对象 {text, emotion}")
        text = b.get("text")
        emotion = b.get("emotion")
        if not isinstance(text, str) or not isinstance(emotion, str):
            raise ContractError("beats 每项需要 text(字符串) 和 emotion(字符串)")
        beats.append({"text": text, "emotion": emotion.strip()})
    return beats


def _parse_place(payload: dict[str, Any]) -> str | None:
    """可选 place 白名单校验（协议 §5: 场景级地点, 不切省略）。缺失 → None。

    只做类型校验; 是否合法 scene_id 由引擎/导演层判（非法 → 静默降级, 不进 retry）。
    """
    raw = payload.get("place")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ContractError("place 必须是字符串")
    return raw.strip()


def parse_story_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """story_scene payload 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    返回 {paragraphs: [str], choices: [str], beats: [dict], place: str|None}——
    is_end 由动作类型推导（story_scene 隐含 False）。残留 is_end 字段被白名单静默
    丢弃（迁移容错: 旧习惯模型仍输出 is_end 也当中段继续, 双层兜底照常兜住）。
    beats/place 可选（协议 §3）: 缺失 → []/None, 纯文本模式照跑。
    """
    paragraphs = _parse_paragraphs(payload)
    choices = _parse_choices(payload)
    beats = _parse_beats(payload)
    place = _parse_place(payload)
    result: dict[str, Any] = {"paragraphs": paragraphs, "choices": choices}
    if beats:
        result["beats"] = beats
    if place is not None:
        result["place"] = place
    return result


def parse_story_end(payload: dict[str, Any]) -> dict[str, Any]:
    """story_end payload 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    返回 {paragraphs: [str], beats: [dict], place: str|None}——收尾无选项由动作类型
    结构性保证（story_end 隐含 is_end=True）。**非空 choices 硬拒绝**（含 nudge 措辞
    「请改用 story_scene」）; 空/缺省 choices 静默忽略。beats/place 可选（同 story_scene）。
    """
    paragraphs = _parse_paragraphs(payload)

    raw_choices = payload.get("choices")
    if raw_choices is None:
        return _end_result(paragraphs, payload)
    if isinstance(raw_choices, str):
        raw_choices = [raw_choices]
    if not isinstance(raw_choices, list):
        raise ContractError("choices 必须是字符串数组（或单个字符串）")
    if any(isinstance(c, str) and c.strip() for c in raw_choices):
        raise ContractError(
            "story_end 是收尾场景, 不出选项——choices 必须为空。"
            "若剧情尚未到结尾, 请改用 story_scene 动作继续。"
        )
    return _end_result(paragraphs, payload)


def _end_result(paragraphs: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    """story_end 结果组装: paragraphs 必含; beats/place 可选仅在出现时存在。"""
    result: dict[str, Any] = {"paragraphs": paragraphs}
    beats = _parse_beats(payload)
    if beats:
        result["beats"] = beats
    place = _parse_place(payload)
    if place is not None:
        result["place"] = place
    return result


def build_story_registry() -> StoryActionRegistry:
    """构建注册了全部 story 动作的注册表（动作名 story_ 前缀）。"""
    registry = StoryActionRegistry()
    registry.register(ActionSpec(
        "story_scene",
        parse_story_scene,
        APPROVAL_AUTO,
        prompt_fields=frozenset({"action", "payload"}),
        payload_schema=(
            "payload 字段（story_scene 中段场景参数）:\n"
            "  paragraphs: 必填, 字符串数组——本场景的叙事段落列表。每项一个段落, 可含\n"
            "      动作描写（括号标注）, 可含长对白; 至少 1 段（空数组会被拒绝）。\n"
            "      段落之间不用手工加分隔符——数组天然分隔。\n"
            "  choices: 数组——给 sensei 的选项文本列表（1~3 个）。可省略（缺省 = 本场景\n"
            "      不提供选项, sensei 将自由输入一句话推进）。选项要有分歧感、让 sensei\n"
            "      有参与感, 但必须收敛到同一主线——无论选哪个, 剧情都走向同一结局, 只\n"
            "      影响紧接着的对白语气与细节, 不要因选项分裂出不同剧情线。\n"
            "  beats: 可选, 数组——每拍的情绪标注（视觉意图, 按节奏给表情）:\n"
            "      [{text: 该拍文本, emotion: 表情词表内的情绪名}]。词表外的情绪不要\n"
            "      标（会被忽略）; 不想细分可省略整个 beats。\n"
            "  place: 可选, 字符串——本场地点（从地点词表选）。只有场景切换时才标,\n"
            "      地点不变省略（保持上一场）。\n"
            "约束: story_scene 是**中段场景**——剧情尚未结束, 不要在本动作里表达收尾\n"
            "      （收尾用 story_end 动作）。字符串一律双引号。\n"
            "      每次只输出一个动作。"
        ),
    ))
    registry.register(ActionSpec(
        "story_end",
        parse_story_end,
        APPROVAL_AUTO,
        prompt_fields=frozenset({"action", "payload"}),
        payload_schema=(
            "payload 字段（story_end 收尾场景参数）:\n"
            "  paragraphs: 必填, 字符串数组——收尾段落。剧情到了自然结尾时（约定达成、\n"
            "      感情升温到位、道别告别、夜色收场等这一幕告一段落的时刻）使用本动作; \n"
            "      至少 1 段（空数组会被拒绝）。\n"
            "  beats: 可选, 数组——同 story_scene（每拍 {text, emotion}, 收尾也可标注）\n"
            "  place: 可选, 字符串——同 story_scene（场景切换才标）\n"
            "约束: story_end 是**收尾场景**——输出后剧情结束, 不再有选项、不再开新场景。\n"
            "      choices 必须为空（结构上收尾无选项, 传非空会被拒绝）。宁可及早收尾, \n"
            "      也不要无限续写新场景。字符串一律双引号。\n"
            "      每次只输出一个动作。"
        ),
    ))
    return registry
