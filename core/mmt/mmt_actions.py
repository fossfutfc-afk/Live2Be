"""MMT 域动作 — MomoTalk 运行时（动作名带 mmt_ 前缀）。

动作集（对白不是动作）:
    说一句话 = 一行**消息行**（`{"text": …}`）, 不是动作;
    动作只承载**需要引擎介入的操作**（**操作行**）:
    mmt_inspect_character    深挖后备: 查角色私密资料（静默推理轮, 权重分级）
    mmt_look                 翻阅**她自己的记忆**（静默推理轮; 查到的东西回灌, 她接着说）
    mmt_send_media           发图片（禁视频; 图片先查资源库, 库内没有才生成）
    mmt_trigger_bond_story   判定进入羁绊剧情（模式切换: 独占操作行）

行协议（⑥-2e 起; 解析见 `core/mmt/mmt_lines.py`, 契约见
`docs/DESIGN_STREAM_CONTRACT.md`）:
    {"text": "话"}                                    ← 消息行（一行 = 一个气泡）
    {"action": "<动作名>", "payload": {…}}            ← 操作行（不上屏）
    任意交错（话→图→话 微信节奏）; 操作行外壳只有 {action, payload}。
    ⚠️ 旧形状（`{"messages": […]}` / `{"reply","actions"}`）**已整段退役**（⑥-2f）。

信息架构（v2 五层认知）:
    L0 自我层   角色设定（五件套）+ 世界观 → 常驻 system prompt
    L1 人际层   注入 interperson 自表条目（键值+权重）+ 人际 knowledge
    L2 硬知识层 knowledge 硬知识 + LLM 世界知识
    L3 深挖层   对方 profile/personality/experience —— 仅 mmt_inspect_character 可取

    - 关系问答 / 大人物常识 → 走 L0-L2 直接回答, 不查
    - 只有玩家深挖私密细节（如"她狙击枪叫什么"）→ 才走 mmt_inspect_character
    - 无记录 = 素不相识（可耳闻）: inspect 会被拒绝, 用知识回答其公开信息
    - 键值映射靠 L1 注入的自表条目（LLM 无需猜 id, 也不烧 token 注入全量名单）

设计决策:
    - mmt_ 前缀: 动作名自带域标识——LLM 输出 / schema 渲染 / 历史记载
      一眼可辨是 MMT 动作, 不依赖额外 domain 字段。
    - 2026-09-02 协议重构 + ⑥-2e 行协议: `mmt_chat` 从来不是动作（说话 = 消息行）;
      summary/operation 移除（MMT 域零消费的死字段）; 操作行外壳 = {action, payload}。
      隐含 mmt_chat 由引擎的行办理层构造（`_run_lines`; 事件流/历史/渲染零改动）。
    - 禁视频: 项目没有视频生成能力——mmt_send_media 只允许图片,
      media_type 白名单 = {'image'}, 传 video 会被硬性拒绝并回灌给 LLM。
    - 图片管线: 先查资源库（library_id）, 库内没有现成图才按 image 描述生成。
    - 自检防护（双重）: payload_schema 提示禁止查自己 + executor 代码级报错。
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
    is_valid_identifier,
)
from core.brain.read.find import ClueError, compile_clue

# MMT 操作行外壳: {action, payload}——对白一律走消息行（`{"text": …}`）;
# summary 也不出现在 MMT（IDE 域残留语义, MMT 零消费）
MMT_RUNTIME_FIELDS = frozenset({"action", "payload"})

# 禁视频: MMT 只允许图片（项目无视频生成能力）
MMT_MEDIA_TYPES = frozenset({"image"})


# ============================================================================
# mmt_inspect_character — 深挖后备: 查角色私密资料
# ============================================================================

def parse_mmt_inspect_character(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    只校验请求结构; 访问层级 / 无记录拒绝由执行层按 interperson 权重决定。
    """
    char_id = payload.get("character_id")
    if not is_valid_identifier(char_id):
        raise ContractError(
            f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
        )
    return {"character_id": char_id}


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
    上下文（同 `mmt_inspect_character` 的分工: "访问层级由执行层决定"）。
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
        "mmt_inspect_character",
        parse_mmt_inspect_character,
        APPROVAL_AUTO,
        prompt_fields=MMT_RUNTIME_FIELDS,
        payload_schema=(
            "character_id: 目标角色 id——用系统提示里『你的关系记录』的键值, "
            "如 rikuhachima_aru\n"
            "用途: 深挖后备手段, 静默推理轮（玩家看不到, 结果回灌给你）——\n"
            "      仅当玩家追问某角色的私密具体细节（如『她的狙击枪叫什么』）\n"
            "      而你无法凭自己的知识回答时才调用; 普通关系问答、大人物常识\n"
            "      直接用你的知识回答, 不要查\n"
            "访问层级由你的关系记录权重决定: 1=萍水相逢(只见profile) "
            "2=社团(+personality) 3=故知(+experience);\n"
            "      无记录=素不相识（但可耳闻）——会被拒绝, 此时用你的知识回答其\n"
            "      公开信息即可\n"
            "不要查你自己——你完全了解自己; 也不要查玩家, 或玩家明显胡编乱造的名字;\n"
            "      完整资料已在你的角色设定中"
        ),
    ))
    registry.register(ActionSpec(
        "mmt_look",
        parse_mmt_look,
        APPROVAL_AUTO,
        prompt_fields=MMT_RUNTIME_FIELDS,
        payload_schema=(
            "clue: 要翻找的线索（**字面**文字, 不要写正则）:\n"
            "      两个词都要有 → `苔藓 && 杂草`（`&` 也行）; 任一即可 → `苔藓 || 杂草`;\n"
            "      分组用**半角**括号 → `(苔藓 || 杂草) && 老师`\n"
            "when: 可选, 大概什么时候的事 —— `last 1 week`（上周）/ `back 1 year`"
            "（一年前的今天）/\n"
            "      `2026/09/25`（那天）; 日常说法也行（`上周` `去年圣诞` `一年前的今天`）\n"
            "用途: **翻你自己的记忆**（旧事 / 你说过的话）——静默推理轮, 老师看不到,\n"
            "      翻到的东西回灌给你, 你再接着说。仅当你**必须知道它才能说下一句**时用\n"
            "      （「那次到底是哪天来着」）; 翻不到就照实说想不起来, 再问老师\n"
            "clue 与 when **至少给一个**; 这是单独一轮——那一轮只有这一条行"
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
