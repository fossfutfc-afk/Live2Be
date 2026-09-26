"""MMT 域动作 — MomoTalk 运行时（动作名带 mmt_ 前缀）。

动作集（v2, 2026-09-02 协议重构——对白不再是动作）:
    说一句话 = 一轮的**默认产物**（轮级 reply 字段）, 不是动作;
    动作只承载**需要引擎介入的操作**:
    mmt_inspect_character    深挖后备: 查角色私密资料（静默推理轮, 权重分级）
    mmt_send_media           发图片（禁视频; 图片先查资源库, 库内没有才生成）
    mmt_trigger_bond_story   判定进入羁绊剧情（bool 触发器: 轮数门槛 + LLM 决策）

消息流协议（见 momotalk._parse_messages）:
    {"messages": [{"text": "话"}, {"action": 真操作, "payload": …}, {"text": "话"}]}
    —— text 单元说话（不是动作, 引擎渲染为气泡）; action 单元只放需引擎介入的
    操作, 外壳只有 {action, payload}; 任意交错（话→图→话 微信节奏）。
    旧输出兼容: reply/actions/mmt_chat 动作 → 解析层归一为消息单元。

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
    - 2026-09-02 协议重构: mmt_chat 不再是动作（说话 = 默认产物, 轮级 reply）;
      summary/operation 移除（MMT 域零消费的死字段）; 动作外壳 = {action, payload}。
      隐含 mmt_chat 由 momotalk 解析层构造（事件流/历史/渲染零改动）。
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

# MMT 动作外壳: {action, payload}——对白一律走轮级 reply（2026-09-02）;
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
