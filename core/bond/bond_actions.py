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
from core.bond.sentence_splitter import split_paragraph

# 选项数量上限（收敛分支: 至多 3 个, 全部收敛同一主线）
MAX_SCENE_CHOICES = 3

# 单场景解析/执行最大重试次数（llm.chat(json_object) 内部另有 3 次语法自纠错）
MAX_SCENE_RETRIES = 3


# 煽情值封顶 / 单次增长（2026-08-30: 情感尺度控制——从日常逐步解锁情感场景）
EMOTIVE_STEP = 15


def _parse_paragraphs(payload: dict[str, Any]) -> list[dict]:
    """必填 paragraphs 白名单校验 + 机器侧容错（硬错误抛 ContractError）。

    每项（2026-09-02 切分权移交定稿——断句是程序的事, LLM 只写自然段）:
        {"text": **自然段文本**（可长可短、可含多句/对白/括号动作——引擎
         sentence_splitter 切成句段: 引号/括号块不拆、数字句点不拆、碎句合并）,
         "inner": 可选内心独白（创作内容——骨架给, 挂切分后首句）}
        ——骨架 emotion 一律忽略（标注层唯一真源, 防双源/锚定; 旧输出带
        emotion 兼容丢弃, 不再逐句复制）。
    兼容旧输入: 裸字符串 str → 当单自然段（旧习惯模型不崩）。

    Returns: 至少 1 个 {text, inner?} 组成的句段列表（strip 后, 已切分）。
    """
    return _parse_paragraphs_seg(payload)[0]


def _parse_paragraphs_seg(payload: dict[str, Any]) -> tuple[list[dict], list[int]]:
    """同 _parse_paragraphs, 额外返回**段分组边界**（2026-09-08 SceneStream P1）:

    seg_ends[i] = 前 i+1 个自然段累计产出的句数（句平铺列表中每个自然段的终点
    下标, 半开区间用）——段分组此前在平铺时丢弃, P1 起标注按自然段流水需要
    它。仅引擎侧消费（_seg_ends 进 parse 结果, 不进事件/渲染）。
    """
    raw_paras = payload.get("paragraphs")
    if isinstance(raw_paras, str):
        raw_paras = [raw_paras]          # 单段裸字符串 → 包成单元素列表
    if not isinstance(raw_paras, list):
        raise ContractError("paragraphs 必须是数组（每项 {text, inner?} 或字符串）")
    paragraphs: list[dict] = []
    seg_ends: list[int] = []
    for p in raw_paras:
        before = len(paragraphs)
        if isinstance(p, str) and p.strip():
            for sent in split_paragraph(p):
                paragraphs.append({"text": sent})
        elif isinstance(p, dict):
            text = p.get("text")
            if isinstance(text, str) and text.strip():
                inner = p.get("inner")
                inner_s = inner.strip() if isinstance(inner, str) else ""
                for i, sent in enumerate(split_paragraph(text)):
                    item: dict[str, Any] = {"text": sent}
                    if i == 0 and inner_s:
                        item["inner"] = inner_s     # 内心独白挂首句（低频惊喜）
                    paragraphs.append(item)
        if len(paragraphs) > before:
            seg_ends.append(len(paragraphs))
    if not paragraphs:
        raise ContractError("paragraphs 至少需要一个非空段落")
    return paragraphs, seg_ends


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
    paragraphs, seg_ends = _parse_paragraphs_seg(payload)
    choices = _parse_choices(payload)
    branches = _parse_branches(payload, choices)
    place = _parse_place(payload)
    result: dict[str, Any] = {"paragraphs": paragraphs, "choices": choices,
                              "_seg_ends": seg_ends}      # 引擎侧段边界（不进事件）
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
    paragraphs, seg_ends = _parse_paragraphs_seg(payload)

    raw_choices = payload.get("choices")
    if raw_choices is None:
        return _end_result(paragraphs, payload, seg_ends)
    if isinstance(raw_choices, str):
        raw_choices = [raw_choices]
    if not isinstance(raw_choices, list):
        raise ContractError("choices 必须是字符串数组（或单个字符串）")
    if any(isinstance(c, str) and c.strip() for c in raw_choices):
        raise ContractError(
            "story_end 是收尾场景, 不出选项——choices 必须为空。"
            "若剧情尚未到结尾, 请改用 story_scene 动作继续。"
        )
    return _end_result(paragraphs, payload, seg_ends)


def _end_result(paragraphs: list[dict], payload: dict[str, Any],
                seg_ends: list[int] | None = None) -> dict[str, Any]:
    """story_end 结果组装: paragraphs 必含; place 兼容旧输出（v2 主 LLM 不写,
    地点由标注层判定, 2026-09-07——机器侧保留容错）; _seg_ends 引擎侧段边界。"""
    result: dict[str, Any] = {"paragraphs": paragraphs}
    if seg_ends:
        result["_seg_ends"] = seg_ends
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
        place      兼容旧输出（v2 主 LLM 不写——地点由标注层判定, 2026-09-07）

    切换动作归**发出方域**（bond 剧情中输出 → 属 story 域; 仿 mmt_trigger_bond_story
    属 mmt 域）——纪念模式内的收尾动作 memorial_exit 才归 memorial 域。
    """
    raw_prompt = payload.get("prompt")
    if not isinstance(raw_prompt, str) or not raw_prompt.strip():
        raise ContractError(
            "prompt 必填——生图场景总结（角色外观+场景+氛围+构图, 精炼, 当场写与剧情一致）"
        )
    paragraphs, seg_ends = _parse_paragraphs_seg(payload)
    choices = _parse_choices(payload)
    place = _parse_place(payload)
    result: dict[str, Any] = {
        "prompt": raw_prompt.strip(),
        "paragraphs": paragraphs,
        "choices": choices,
        "_seg_ends": seg_ends,                    # 引擎侧段边界（不进事件）
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
            "  paragraphs: 必填, 数组——每项 {text, inner?}:\n"
            "      text: **一个自然段**（2026-09-02: 你只管写, 引擎自动断句）——\n"
            "          可长可短, 可含多句对白与动作（小说式自然书写, 不用数句子、\n"
            "          不用自己拆段）; 每场 2~5 个自然段, 一段一个节拍;\n"
            "          引号「」与括号（）内的内容写完整, 别拆开\n"
            "      emotion: **不要写**——系统自动切句并按句标注表情（写了也忽略）\n"
            "      inner: 可选, 字符串——**内心独白**（角色没说出口的心理活动, 屏幕变黑\n"
            "          单独展示）。低频惊喜: 只在情感的关键时刻写（遥香的自卑、阿露的逞强\n"
            "          心理这类）; 不必每场都有, 没有就省略, 不要为了写而写\n"
            "      分段（v2 定稿, 2026-09-07）: **空间/时间明显跳变 → 另起一个 text**——\n"
            "          一个 text = 一个画面节拍（走出教室/来到天台这类换场是段落重音,\n"
            "          系统按段自动跟随切换背景——**地点你不用写**, 规则见前）\n"
            "  choices: 数组——给 sensei 的选项文本列表（1~3 个）。**带 choices 时\n"
            "      必须同时提供 branches**（见下）; 纯叙事板块可省略 choices\n"
            "      （缺省 = 本板块不提供选项, sensei 读完点继续）\n"
            "  branches: dict——**同响应分支内容**（板块契约 2026-08-30）: 键 = choices\n"
            "      里的选项文本, 值 = 该选项对应的段落数组（每项同 paragraphs）。\n"
            "      老师选了这个选项后**立即看到**这段内容（零等待）——\n"
            "      是选项引发的即时反应（1~3 句）, 不是新板块。**有 choices 必须带\n"
            "      branches, 键与 choices 完全一致**; 纯叙事板块不需要\n"
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
            "  paragraphs: 必填, 数组——同 story_scene（每项 {text, inner?}, 自然段语义;\n"
            "      emotion 不要写——系统自动切句并标注; 空间/时间跳变另起一段, 同 story_scene）\n"
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
            "  paragraphs: 必填, 数组——纪念场景的煽情文字, 同 story_scene（自然段语义,\n"
            "      每项 {text, inner?}; emotion 不要写——系统自动切句并标注; 这是本场剧情内容）\n"
            "  choices: 可选, 数组——同 story_scene（1~3 个; 缺省 = 无选项——剧情内没有自由打字通道, sensei 的话只经选项说出; 无选项时点继续推进）\n"
            "约束: memorial_enter 是**进入纪念时刻**的专属动作——这是剧情的决定时刻, 只\n"
            "      在该真正值得纪念的场景使用（约定/告白/道别/重大转折）, 一段剧情至多\n"
            "      一次（重复会被引擎拒绝）。输出后本场生成纪念立绘。文字要煽情, 配得上\n"
            "      这个时刻。字符串一律双引号。每次只输出一个动作。"
        ),
    ))
    return registry
