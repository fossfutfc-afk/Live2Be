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

import re
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


# 句末标点（2026-08-30: 一句一段硬校验——段落含 >1 个句末标点 → 打回重试。
# 目的: 保证"每一句话都伴随表情变化"——多句压一段 = 一个 emotion 字段,
# 切分继承表情 = 粒度名存实亡; 强制 LLM 自己按句拆段、每句标 emotion。
# 省略号不算句末（语气停顿, "老师……我这种人……"不误判））
_SENTENCE_END = re.compile(r"[。！？；]")
# 煽情值封顶 / 单次增长（2026-08-30: 情感尺度控制——从日常逐步解锁情感场景）
EMOTIVE_STEP = 15


def _split_sentences(text: str) -> list[str]:
    """按句末标点切分（保留标点）——句数统计/兼容兜底（校验后不再有多句段）。

    无标点的文本 → 原样单段。标点后无内容（结尾）不产生空段。
    """
    parts = re.split(r"(?<=[。！？；])", text)
    return [p.strip() for p in parts if p.strip()]


def _parse_paragraphs(payload: dict[str, Any]) -> list[dict]:
    """必填 paragraphs 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    每项（2026-08-23 架构定稿: 情绪内联; 2026-08-30 一句一段; 2026-08-31 两遍式×2）:
        {"text": 段落文本, "emotion": 可选表情词表键, "inner": 可选内心独白}
        ——emotion 可选（两遍式 C: 生成骨架与情绪标注解耦——缺省段落由标注层
        批量补标, 契约不再打回）。
        ——一句一段软化（两遍式 C 实测定版）: 多句段落**不再打回**, 引擎按
        句末标点切分（_split_sentences）→ 每句一段; 标注层对切分后的每句
        独立标注——切分不再"继承表情"（旧问题: 切分+单 emotion = 粒度粗）,
        每句独立标注 = 粒度仍到句。骨架生成的结构失败源只剩 JSON 格式,
        重试率趋零（真实测试: 场 1 契约重试 1, 场 2 多句长段 3 次耗尽中断——
        实测定版后不再发生）。
    兼容旧输入: 裸字符串 str → 包成 {"text": str}（旧习惯模型不崩）。

    Returns: 至少 1 个 {text, emotion?, inner?} 组成的列表（strip 后, 已切分）。
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
                emotion = p.get("emotion")
                inner = p.get("inner")
                inner_s = inner.strip() if isinstance(inner, str) else ""
                for i, sent in enumerate(_split_sentences(text.strip())):
                    item: dict[str, Any] = {"text": sent}
                    if isinstance(emotion, str) and emotion.strip():
                        item["emotion"] = emotion.strip()
                    if i == 0 and inner_s:
                        item["inner"] = inner_s     # 内心独白挂首句（低频惊喜）
                    paragraphs.append(item)
    if not paragraphs:
        raise ContractError("paragraphs 至少需要一个非空段落")
    return _merge_bracket_fragments(paragraphs)


#: 孤闭括号/引号（LLM 偶发把 （…）「…」 拆段——schema 已禁, 引擎再兜底）
_ORPHAN_CLOSE = ("）", "」", ")", '"')


def _merge_bracket_fragments(paragraphs: list[dict]) -> list[dict]:
    """括号碎片净化（2026-09-02 用户反馈: 出现单独一段"）"）: LLM 偶发把
    （动作描写）或「对白」拆成两段——开括号段 + 孤闭括号段（常见于把 inner
    塞进括号时的格式幻觉）。规则: 若段落以孤闭括号开头, 且上一段以对应开
    括号开头且未闭合 → 并入上一段末尾（括号成对, 渲染不出现光秃秃的
    "）" 成段）。段间 emotion 保留上一段的（碎片段的 emotion 丢弃）。
    """
    out: list[dict] = []
    for p in paragraphs:
        text = p.get("text", "").strip()
        if out and text and text[0] in _ORPHAN_CLOSE:
            prev = out[-1]
            ptext = prev.get("text", "")
            # 上一段以开括号开头且同型未闭合 → 补尾
            opener = "（" if text[0] == "）" else ("「" if text[0] == "」" else None)
            if opener is not None and ptext.startswith(opener) \
                    and _closer(opener) not in ptext:
                prev["text"] = (ptext + text).strip()
                continue
            if text[0] == ")" and ptext.startswith("(") and ")" not in ptext:
                prev["text"] = (ptext + text).strip()
                continue
        out.append(dict(p))
    return out


def _closer(opener: str) -> str:
    return {"（": "）", "「": "」", "(": ")"}.get(opener, opener)


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


def _parse_branches(payload: dict[str, Any], choices: list[str]) -> dict[str, list]:
    """可选 branches 白名单校验（2026-08-30 板块契约: 同响应分支内容）。

    branches = {选项文本: [段落…]}——玩家选该选项后**立即展示**的内容（零等待,
    Storyloom <choice>+<branch> 同响应模式）。每个分支段落复用 _parse_paragraphs
    （emotion 必填 + 按句切分）。约束:
      - branches 必须是 dict; 键 = choices 里的选项文本（只取 choices 中的键）
      - 键对应的值必须是段落数组（str 或 {text, emotion}——同 paragraphs 容错）
      - **有 choices 时必须带 branches**（用户方案核心: 分支同响应才零等待——
        缺失 → ContractError → feedback 提示, 防 LLM 省略, memorial 教训）
      - story_end 无 choices → 不需要 branches
    """
    raw = payload.get("branches")
    if raw is None:
        if choices:
            raise ContractError(
                "story_scene 带 choices 时必须同时提供 branches（dict: 选项文本 → "
                "该选项对应的段落数组）——玩家选完立即展示分支内容, 零等待。"
                "例: \"branches\": {\"走过去\": [{\"text\": \"…\", \"emotion\": \"…\"}]}")
        return {}
    if not isinstance(raw, dict):
        raise ContractError("branches 必须是 dict（选项文本 → 段落数组）")
    branches: dict[str, list] = {}
    for choice in choices:                       # 只取 choices 里的键（对齐）
        val = raw.get(choice)
        if val is None:
            continue
        if isinstance(val, str):
            val = [val]
        if not isinstance(val, list):
            raise ContractError(f"branches[{choice}] 必须是段落数组（或单段字符串）")
        branches[choice] = _parse_paragraphs({"paragraphs": val})
    return branches


def parse_story_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """story_scene payload 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    返回 {paragraphs: [{text, emotion?}], choices: [str], branches: {choice: [段]},
    place: str|None}——is_end 由动作类型推导（story_scene 隐含 False）。残留 is_end
    字段被白名单静默丢弃（迁移容错: 旧习惯模型仍输出 is_end 也当中段继续, 双层兜底
    照常兜住）。旧 beats 字段静默忽略（2026-08-23 情绪内联进 paragraphs, 兼容旧输出）。
    branches（2026-08-30 板块契约）: 有 choices 时必须带——同响应分支内容, 选完
    零等待; 无 choices（纯叙事场）不需要。
    """
    paragraphs = _parse_paragraphs(payload)
    choices = _parse_choices(payload)
    branches = _parse_branches(payload, choices)
    place = _parse_place(payload)
    result: dict[str, Any] = {"paragraphs": paragraphs, "choices": choices}
    if branches:
        result["branches"] = branches
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
            "  paragraphs: 必填, 数组——每项 {text, emotion?, inner?}:\n"
            "      text: 一个情绪单元（**一句话**——一句对白 或 一个动作描写;\n"
            "          句子要短: 旁白 15~40 字只说一件事, 对白一句一段）; 至少 1 单元\n"
            "      emotion: **可选**——系统自动标注（独立标注层补标, 你不用管;\n"
            "          带了也行, 系统优先用你的）\n"
            "      inner: 可选, 字符串——**内心独白**（角色没说出口的心理活动, 屏幕变黑\n"
            "          单独展示）。低频惊喜: 只在情感的关键时刻写（遥香的自卑、阿露的逞强\n"
            "          心理这类）; 不必每场都有, 没有就省略, 不要为了写而写\n"
            "      **括号与引号必须成对出现在同一段 text 内**: （动作描写）整段写全,\n"
            "         禁止把「（」和「）」拆成两段输出; 内心独白只用 inner 字段,\n"
            "         不要用括号把 inner 包起来; 不要输出单独一行只有 ）或 」 的段落\n"
            "  choices: 数组——给 sensei 的选项文本列表（1~3 个）。**带 choices 时\n"
            "      必须同时提供 branches**（见下）; 纯叙事板块可省略 choices\n"
            "      （缺省 = 本板块不提供选项, sensei 读完点继续）\n"
            "  branches: dict——**同响应分支内容**（板块契约 2026-08-30）: 键 = choices\n"
            "      里的选项文本, 值 = 该选项对应的段落数组（每项同 paragraphs）。\n"
            "      老师选了这个选项后**立即看到**这段内容（零等待）——\n"
            "      是选项引发的即时反应（1~3 句）, 不是新板块。**有 choices 必须带\n"
            "      branches, 键与 choices 完全一致**; 纯叙事板块不需要\n"
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
            "  paragraphs: 必填, 数组——同 story_scene（每项 {text, emotion?}, emotion 可选, 系统自动标注; inner 可选同 story_scene）\n"
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
            "  paragraphs: 必填, 数组——纪念场景的煽情文字, 同 story_scene 格式（inner 可选同 story_scene）\n"
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
