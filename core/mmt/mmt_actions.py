"""MMT 域动作 — MomoTalk 运行时（动作名带 mmt_ 前缀）。

动作集（对白不是动作）:
    说一句话 = 一行**消息行**（`{"text": …}`）, 不是动作;
    动作只承载**需要引擎介入的操作**（**操作行**）:
    mmt_look                 翻阅**她自己的记忆**（静默推理轮; 查到的东西回灌, 她接着说）
    mmt_send_media           发图片（禁视频; 图片先查资源库, 库内没有才生成）
    mmt_trigger_bond_story   判定进入羁绊剧情（模式切换: 独占操作行）

行协议（⑥-2e 起; 解析见 `core/mmt/mmt_lines.py`, 契约见
`docs/DESIGN_STREAM_CONTRACT.md`）:
    {"text": "话"}                                    ← 消息行（一行 = 一个气泡）
    {"action": "<动作名>", "payload": {…}}            ← 操作行（不上屏）
    任意交错（话→图→话 微信节奏）; 操作行外壳只有 {action, payload}。
    ⚠️ 旧形状（`{"messages": […]}` / `{"reply","actions"}`）**已整段退役**（⑥-2f）。

信息架构（2026-10-08 校正 —— ⛔ L3 深挖层随 `mmt_inspect_character` 一起退役）:
    L0 自我层   角色设定（六件套）+ 世界观 → 常驻 system prompt
    L1 人际层   ⭐ **她眼里的他们**: `interperson.yml` 的立场物化成 `entity.text`,
                注入 brain 段的「我眼里的他们」（+ 她自己那一行「我是这样看自己的」）
    L2 硬知识层 knowledge 硬知识 + LLM 世界知识

    - 关系问答 / 大人物常识 → 走 L0-L2 直接回答, **没有"查资料"这个动作了**
    - ⚠️ **他人的私密档案不再是她的信息来源**（用户 2026-10-08 裁）: 从前按
      `interperson` 权重分级读别人的 profile/personality/experience, 那是**客观档案**
      混进她主观的看法里; 现在她只知道**自己眼里的他们**（立场句本身就可以是错的、
      片面的 —— 那才是角色）。

设计决策:
    - mmt_ 前缀: 动作名自带域标识——LLM 输出 / schema 渲染 / 历史记载
      一眼可辨是 MMT 动作, 不依赖额外 domain 字段。
    - 2026-09-02 协议重构 + ⑥-2e 行协议: `mmt_chat` 从来不是动作（说话 = 消息行）;
      summary/operation 移除（MMT 域零消费的死字段）; 操作行外壳 = {action, payload}。
      隐含 mmt_chat 由引擎的行办理层构造（`_run_lines`; 事件流/历史/渲染零改动）。
    - 禁视频: 项目没有视频生成能力——mmt_send_media 只允许图片,
      media_type 白名单 = {'image'}, 传 video 会被硬性拒绝并回灌给 LLM。
    - 图片管线: 先查资源库（library_id）, 库内没有现成图才按 image 描述生成。
    - 羁绊剧情是 LLM 生成的（BondScene + 表情/立绘控制）, 不是点选剧本——
      mmt_trigger_bond_story 只是触发信号（算法轮数门槛 + LLM 决策）,
      放行才切换羁绊剧情模式。
"""

from __future__ import annotations

from typing import Any

from contract import (
    MMTActionRegistry,
    ActionSpec,
    APPROVAL_AUTO,
    ContractError,
)
from core.brain.read.find import ClueError, compile_clue

# MMT 操作行外壳: {action, payload}——对白一律走消息行（`{"text": …}`）;
# summary 也不出现在 MMT（IDE 域残留语义, MMT 零消费）
MMT_RUNTIME_FIELDS = frozenset({"action", "payload"})

# 禁视频: MMT 只允许图片（项目无视频生成能力）
MMT_MEDIA_TYPES = frozenset({"image"})


# ============================================================================
# mmt_send_media — 发图片（禁视频）
# ============================================================================

def parse_mmt_send_media(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    禁视频: media_type 白名单只有 'image'——传 video 直接拒绝, 让 LLM 修正。
    图片管线: 先查资源库（library_id）, 库内没有才按 image 描述生成。
    附带的话走**另一行消息行**（⑥-2e 起：行流契约里"话"永远是独立的一行）。
    """
    media_type = payload.get("media_type", "image")
    if media_type not in MMT_MEDIA_TYPES:
        raise ContractError(
            f"media_type 必须是 {sorted(MMT_MEDIA_TYPES)}; "
            f"MMT 禁发视频（项目无视频生成能力）: {media_type!r}"
        )

    image = payload.get("image")
    if not isinstance(image, str) or not image.strip():
        raise ContractError(
            "image 必须是非空字符串（图片内容描述, 查库无果时按此生成）"
        )

    library_id = payload.get("library_id", "")
    if not isinstance(library_id, str):
        raise ContractError("library_id 必须是字符串（资源库已有图片 id）")

    return {
        "media_type": media_type,
        "image": image.strip(),
        "library_id": library_id.strip(),
    }


# ============================================================================
# mmt_trigger_bond_story — 触发羁绊剧情
# ============================================================================

def parse_mmt_trigger_bond_story(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    羁绊剧情不是点选剧本——它是 LLM 自行的触发判定（算法轮数门槛 + LLM 决策）,
    放行才切换羁绊剧情模式。payload 带本章标题（chapter_title——触发即命题:
    章节标题卡的来源, 进上下文/事件流; 空则调用方降级, **不拦触发**）。
    reason 字段已退役（2026-09-05——起因由上下文窗口承载）; 旧模型输出兼容
    透传丢弃, 消费方不再读。
    """
    title = payload.get("chapter_title", "")
    if not isinstance(title, str):
        raise ContractError("chapter_title 必须是字符串（本章标题, 3-16 字）")
    return {"chapter_title": title.strip()}


# ============================================================================
# mmt_look — 翻阅她自己的记忆（静默推理轮）
# ============================================================================

def parse_mmt_look(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    ⚠️ **两格都是字符串进出, ⛔ 不把编译好的 `Clue` 塞进 payload**:
    `payload` 会进 `TurnResult` / trace / 前端 JSON —— 塞一个自定义对象进去,
    序列化那一层迟早出事。编译是纯函数, 执行层再编一次零成本（**一份实现, 两处调用**）。

    ⚠️ **`when` 只校验"是字符串"** —— 时间语法要 `now` 才能判, 而 parse 层没有会话
    上下文（同 `send_media` 的分工: "库里的图由执行层查"）。
    ⚠️ 也不在这里做**检索**（那是执行层 + `core.brain.read.find` 的事）。

    两格**至少给一个**（`DESIGN_MMT_NEW_ACTION §3.1`）: 只想查"那阵子的事"时
    可以不写 `clue`; 只想问"某件事"时可以不写 `when`。
    """
    clue = payload.get("clue", "")
    if not isinstance(clue, str):
        raise ContractError("clue 必须是字符串（要翻找的线索）")
    when = payload.get("when", "")
    if not isinstance(when, str):
        raise ContractError("when 必须是字符串（时间范围, 可省）")
    clue, when = clue.strip(), when.strip()
    if not clue and not when:
        raise ContractError(
            "clue 与 when 至少要给一个——说不出要找什么、也不知道大概什么时候, 就没法翻"
        )
    if clue:
        # ⛔ 线索只认**字面** + `&`/`|`/半角括号; 正则味的字符当场拒（可归因, 不静默）
        try:
            compile_clue(clue)
        except ClueError as e:
            raise ContractError(f"clue 看不懂: {e}") from None
    return {"clue": clue, "when": when}


# ============================================================================
# 注册表
# ============================================================================

def build_mmt_registry() -> MMTActionRegistry:
    """构建注册了全部 MMT 动作的注册表（动作名带 mmt_ 前缀）。

    2026-09-02: 不含 mmt_chat——说话是轮级默认产物, 不是动作（旧输出兼容由
    momotalk 解析层抽取, 引擎构造隐含 mmt_chat 走原管线）。
    """
    registry = MMTActionRegistry()
    registry.register(ActionSpec(
        "mmt_look",
        parse_mmt_look,
        APPROVAL_AUTO,
        prompt_fields=MMT_RUNTIME_FIELDS,
        payload_schema=(
            # ⚠️ 这一段是她**看得见的那一份 when 语法摘录**（真源 = `core/worldtime/when.py`）——
            # 改语法必须**同批**改这里, 否则她照旧写法写、引擎已经不认（或反过来）。
            # ⛔ **契约暂不教节日名**（用户 2026-10-08: 将来注入节日表, 由她自己判断日期）,
            # 但引擎**照收**（`last 1 christmas` / 裸「圣诞节」今天就能用）—— 别当没实现删掉。
            "clue: 要翻找的**字面**文字（不要写正则）:\n"
            "      两个词都要有 → `苔藓 && 杂草`（`&` 也行）; 任一即可 → `苔藓 || 杂草`;\n"
            "      分组用**半角**括号 → `(苔藓 || 杂草) && 老师`\n"
            "when: 可选, 什么时间的事 —— **只写时间, 别写整句话**:\n"
            "      整段 → `last 1 week`（上周）· `last 1 month` · `last 1 year`（去年）\n"
            "      那天 → `back 1 week`（一周前的今天）· `back 3 day` · `back 1 year`\n"
            "      区间 → `back 0..7 day`（最近七天）· `last 1..=3 week`（前三个整周）;\n"
            "             `..` 不含右端, `..=` 含, 左端可省（`back ..=6 day`）\n"
            "      某天 → `2026/09/25` · 没年份写 `09/25`（= 最近那一次）· 整月 `2026/09`\n"
            "      单位 = day / week / month / year（中文 `天 周 个月 年` 也收）\n"
            "用途: **翻你自己的记忆**（旧事 / 你说过的话）——老师看不到这一行,\n"
            "      翻到的东西回灌给你, 你再接着说。仅当你**必须知道它才能说下一句**时用\n"
            "      （「那次到底是哪天来着」）; 翻不到就照实说想不起来, 再问老师\n"
            "clue 与 when **至少给一个**; 它是这一轮**唯一的操作行**（放最后一行 ——\n"
            "      想说的那句「唔……我找找看」写在它**前面**的消息行里）"
        ),
    ))
    registry.register(ActionSpec(
        "mmt_send_media",
        parse_mmt_send_media,
        APPROVAL_AUTO,
        prompt_fields=MMT_RUNTIME_FIELDS,
        payload_schema=(
            "image: 图片内容描述（必填, 非空）——程序先查资源库, 库里有现成图"
            "（角色差分/表情）就发, 没有才按此描述生成\n"
            "library_id: 可选, 资源库已有图片的 id（如 'haruka_smile_02'）;\n"
            "      填了且库中命中则直接发这张\n"
            "media_type: 可选, 只能 'image'（MMT 禁发视频——项目没有视频生成能力, "
            "传 video 会被拒绝）\n"
            "附带的话**另起一行消息行**（操作行不上屏, 只负责把图发出去）"
        ),
        # ⛔ **封印（2026-10-12 用户裁: *"动作提示词被注入了，可以暂时先删掉/注释掉"*）**:
        # 媒体管线还没接 —— 执行层只回"[图片占位]"、前端没有渲染分支, 而契约在承诺
        # "先查资源库…就发"（AUDIT B10 记过这条"端到端 no-op"）⇒ 先把这座承诺**从
        # prompt 上收掉**（动作表不列、payload 描述不印）。
        # ⚠️ **只管"她看不看得见"**: 解析 / 校验 / 执行**一律照旧**（她万一还是写了,
        # 走老路: `repair_send_media` → `parse` → 执行占位, 不炸）。
        # ⏭ **恢复** = 这一格改回 `True` + **同批**改回: `momotalk_rules.md` 三处
        # （【说话与做事】的"发图" / 操作使用时机的"发图片 →" / trigger 段的"不能再夹发图"）
        # · `momotalk_environment.md` 两处（"文字 + 图片" / "图片 → 用 mmt_send_media 发"）
        # · `build_line_schema` 的示例（"话 → 图 → 话"那一段）+ 刷 promptkit 夹具。
        in_prompt=False,
    ))
    registry.register(ActionSpec(
        "mmt_trigger_bond_story",
        parse_mmt_trigger_bond_story,
        APPROVAL_AUTO,
        prompt_fields=MMT_RUNTIME_FIELDS,
        payload_schema=(
            "chapter_title: **必填**——本章羁绊剧情的标题（3-16 字, 中文）:\n"
            "      此刻你握着刚发生的对话与契机, 上下文最强——起一个有剧情分量的\n"
            "      章节名（不是对话的重复, 是这段故事的命题, 如『杂草屋的午后』\n"
            "      『夏莱的邀请函』『雨中的秘密』）——它是章节标题卡与剧情记录的来源\n"
            "用途: 把对话从手机聊天切换到当面相见的羁绊剧情——面对面推进。\n"
            "      当你判断手机消息进行不下去/共处契机出现时, 可以发起;\n"
            "      邀约/见面的话写在它**前面的消息行**里（见到老师时说的话——不是告别, 是见面的话）\n"
            "[系统] 节奏是**建议不是拦截**: 程序不会拒绝你的触发——每轮注记会\n"
            "      提示当前时机（距上次剧情轮数）; 紧急/危险场面（sensei 遇险等）\n"
            "      你判断该去就去, 不必等轮数; 刚演完剧情也别立刻连开, 自然沉淀"
        ),
    ))
    return registry
