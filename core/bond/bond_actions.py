"""STORY 域动作 — 羁绊剧情（Bond Story）场景契约。

动作集（v3, 全部 APPROVAL_AUTO）:
    story_scene     中段场景（叙事段落 + 选项, is_end 隐含 False）
    story_end       收尾场景（叙事段落, 无选项, is_end 隐含 True）
    memorial_enter  进入纪念子模式（§4.7: 生图 prompt + 煽情文字, 独占一轮）——
                    切换动作归发出方域（仿 mmt_trigger_bond_story 属 mmt 域）

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


def _parse_paragraphs(payload: dict[str, Any]) -> list[dict]:
    """必填 paragraphs 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    每项（2026-08-23 架构定稿: 情绪内联, 删 beats）:
        {"text": 段落文本, "emotion": 可选表情词表键}——emotion 缺省 = 延续上一段
    兼容旧输入: 裸字符串 str → 包成 {"text": str}（旧习惯模型不崩）。

    Returns: 至少 1 个 {text, emotion?} 组成的列表（strip 后）。
    """
    raw_paras = payload.get("paragraphs")
    if isinstance(raw_paras, str):
        raw_paras = [raw_paras]          # 单段裸字符串 → 包成单元素列表
    if not isinstance(raw_paras, list):
        raise ContractError("paragraphs 必须是数组（每项 {text, emotion?} 或字符串）")
    paragraphs: list[dict] = []
    for p in raw_paras:
        if isinstance(p, str) and p.strip():
            paragraphs.append({"text": p.strip()})
        elif isinstance(p, dict):
            text = p.get("text")
            if isinstance(text, str) and text.strip():
                item: dict[str, Any] = {"text": text.strip()}
                emotion = p.get("emotion")
                if isinstance(emotion, str) and emotion.strip():
                    item["emotion"] = emotion.strip()
                paragraphs.append(item)
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

    返回 {paragraphs: [{text, emotion?}], choices: [str], place: str|None}——
    is_end 由动作类型推导（story_scene 隐含 False）。残留 is_end 字段被白名单静默
    丢弃（迁移容错: 旧习惯模型仍输出 is_end 也当中段继续, 双层兜底照常兜住）。
    旧 beats 字段静默忽略（2026-08-23 情绪内联进 paragraphs, 兼容旧输出）。
    """
    paragraphs = _parse_paragraphs(payload)
    choices = _parse_choices(payload)
    place = _parse_place(payload)
    result: dict[str, Any] = {"paragraphs": paragraphs, "choices": choices}
    if place is not None:
        result["place"] = place
    return result


def parse_story_end(payload: dict[str, Any]) -> dict[str, Any]:
    """story_end payload 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    返回 {paragraphs: [{text, emotion?}], place: str|None}——收尾无选项由动作类型
    结构性保证（story_end 隐含 is_end=True）。**非空 choices 硬拒绝**（含 nudge 措辞
    「请改用 story_scene」）; 空/缺省 choices 静默忽略。place 可选（同 story_scene）。
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


def _end_result(paragraphs: list[dict], payload: dict[str, Any]) -> dict[str, Any]:
    """story_end 结果组装: paragraphs 必含; place 可选仅在出现时存在。"""
    result: dict[str, Any] = {"paragraphs": paragraphs}
    place = _parse_place(payload)
    if place is not None:
        result["place"] = place
    return result


def parse_memorial_enter(payload: dict[str, Any]) -> dict[str, Any]:
    """memorial_enter payload 白名单校验 + 机器侧容错（进入纪念子模式, §4.7）。

    返回 {prompt: str, paragraphs: [{text, emotion?}], choices: [str], place: str|None}:
        prompt     必填: 生图场景总结（当场写, 与剧情一致——角色外观+场景+氛围+构图, 精炼）
        paragraphs 必填: 纪念场景的煽情文字（同 story_scene 格式——本场剧情内容）
        choices    可选: 给 sensei 的回应（同 story_scene）
        place      可选: 本场地点（同 story_scene, 场景切换才标）

    切换动作归**发出方域**（bond 剧情中输出 → 属 story 域; 仿 mmt_trigger_bond_story
    属 mmt 域）——纪念模式内的收尾动作 memorial_exit 才归 memorial 域。
    """
    raw_prompt = payload.get("prompt")
    if not isinstance(raw_prompt, str) or not raw_prompt.strip():
        raise ContractError(
            "prompt 必填——生图场景总结（角色外观+场景+氛围+构图, 精炼, 当场写与剧情一致）"
        )
    paragraphs = _parse_paragraphs(payload)
    choices = _parse_choices(payload)
    place = _parse_place(payload)
    result: dict[str, Any] = {
        "prompt": raw_prompt.strip(),
        "paragraphs": paragraphs,
        "choices": choices,
    }
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
            "  paragraphs: 必填, 数组——每项 {text, emotion}:\n"
            "      text: 一个情绪单元（一句对白 或 一个动作描写; 情绪一致的多句可合并;\n"
            "          动作描写单独成单元, 不塞进对白单元）; 至少 1 单元\n"
            "      emotion: 必填, 表情词表内的情绪名（见【表情标注词表】）——\n"
            "          **每个情绪单元都必须标 emotion, 不要省略、不要留空**\n"
            "          情绪连续就合并成一个单元; 情绪一变就切新单元并标新 emotion\n"
            "  choices: 数组——给 sensei 的选项文本列表（1~3 个）。可省略（缺省 = 本场景\n"
            "      不提供选项, sensei 将自由输入一句话推进）。选项要有分歧感、让 sensei\n"
            "      有参与感, 但必须收敛到同一主线——无论选哪个, 剧情都走向同一结局, 只\n"
            "      影响紧接着的对白语气与细节, 不要因选项分裂出不同剧情线。\n"
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
            "  paragraphs: 必填, 数组——同 story_scene（每项 {text, emotion}, 每单元必填 emotion）\n"
            "  place: 可选, 字符串——同 story_scene（场景切换才标）\n"
            "约束: story_end 是**收尾场景**——输出后剧情结束, 不再有选项、不再开新场景。\n"
            "      choices 必须为空（结构上收尾无选项, 传非空会被拒绝）。宁可及早收尾, \n"
            "      也不要无限续写新场景。字符串一律双引号。\n"
            "      每次只输出一个动作。"
        ),
    ))
    registry.register(ActionSpec(
        "memorial_enter",
        parse_memorial_enter,
        APPROVAL_AUTO,
        prompt_fields=frozenset({"action", "payload"}),
        payload_schema=(
            "payload 字段（memorial_enter 进入纪念子模式参数）:\n"
            "  prompt: 必填, 字符串——**中文场景指令**（场景/时间/光线/情感/构图, 如\n"
            "      \"她在湖边微笑，眼角带着一滴泪，黄昏暖光，晚风吹起鬓发，中景半身\"）——\n"
            "      角色外观/画风/配饰不用写（引擎自动附角色参考图锚定, 2026-08-24）\n"
            "  paragraphs: 必填, 数组——纪念场景的煽情文字, 同 story_scene 格式\n"
            "      （每项 {text, emotion}, 每单元必填 emotion; 这是本场剧情内容）\n"
            "  choices: 可选, 数组——同 story_scene（1~3 个; 缺省 = sensei 自由输入）\n"
            "  place: 可选, 字符串——同 story_scene（场景切换才标）\n"
            "约束: memorial_enter 是**进入纪念时刻**的专属动作——这是剧情的决定时刻, 只\n"
            "      在该真正值得纪念的场景使用（约定/告白/道别/重大转折）, 一段剧情至多\n"
            "      一次（重复会被引擎拒绝）。输出后本场生成纪念立绘。文字要煽情, 配得上\n"
            "      这个时刻。字符串一律双引号。每次只输出一个动作。"
        ),
    ))
    return registry
