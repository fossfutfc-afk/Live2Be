"""MMT 域动作 — MomoTalk 运行时（动作名带 mmt_ 前缀）。

动作集（v1, 全部 APPROVAL_AUTO——运行时校验通过即执行）:
    mmt_chat                 说一句话（对白在 reply 字段, 可选模拟手机操作）
    mmt_inspect_character    深挖后备: 查角色私密资料（静默推理轮, 权重分级）
    mmt_send_media           发图片（禁视频; 图片先查资源库, 库内没有才生成）
    mmt_trigger_bond_story   判定进入羁绊剧情（bool 触发器: 好感度门槛 + LLM 决策）

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
    - 历史记载: 每轮至少记动作名 + reply（用户可追溯 agent 干了什么）;
      history 格式在 momotalk 全 JSON 化时一并清理。
    - 禁视频: 项目没有视频生成能力——mmt_send_media 只允许图片,
      media_type 白名单 = {'image'}, 传 video 会被硬性拒绝并回灌给 LLM。
    - 图片管线: 先查资源库（library_id）, 库内没有现成图才按 image 描述生成。
    - 自检防护（双重）: payload_schema 提示禁止查自己 + executor 代码级报错。
    - 羁绊剧情是 LLM 生成的（返回 BondOutput + 表情/立绘控制）, 不是点选剧本——
      mmt_trigger_bond_story 只是 bool 触发信号（算法好感度 + LLM 决策）,
      true 才切换羁绊剧情模式, false 继续聊天。
    - 外壳字段统一走 RUNTIME_SHELL_FIELDS + reply（运行时动作, 无 sources/basis）。

TODO（后续 session）:
    - core/parsing/relation_parser.py: 自表条目注入函数 + 访问层级
      （当前逻辑内联在 mmt_executor.py, 待移入）
    - knowledge.yml 拆分 人际/硬知识 两个 section（L1/L2 分层, 轻量选项 A）
    - mmt_executor.py: 自检守卫 / 无记录拒绝 / trigger 好感度门槛已完成; send_media 媒体管线待接入
"""

from __future__ import annotations

from typing import Any

from contract import (
    MMTActionRegistry,
    ActionSpec,
    APPROVAL_AUTO,
    RUNTIME_SHELL_FIELDS,
    ContractError,
    is_valid_identifier,
)

# MMT 运行时外壳字段: 最小集 + reply（对白 / 给用户的话）
MMT_RUNTIME_FIELDS = RUNTIME_SHELL_FIELDS | frozenset({"reply"})

# 禁视频: MMT 只允许图片（项目无视频生成能力）
MMT_MEDIA_TYPES = frozenset({"image"})


# ============================================================================
# mmt_chat — 说一句话
# ============================================================================

def parse_mmt_chat(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    对白在 reply 字段（外壳层校验）。payload 只带可选模拟手机操作。
    """
    operation = payload.get("operation", "")
    if not isinstance(operation, str):
        raise ContractError("operation 必须是字符串")
    return {"operation": operation.strip()}


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

    羁绊剧情不是点选剧本——它是 LLM 自行的 bool 判定（算法好感度 + LLM 决策）,
    true 才切换羁绊剧情模式。payload 只带可选触发理由。
    """
    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        raise ContractError("reason 必须是字符串")
    return {"reason": reason.strip()}


# ============================================================================
# 注册表
# ============================================================================

def build_mmt_registry() -> MMTActionRegistry:
    """构建注册了全部 MMT 动作的注册表（动作名带 mmt_ 前缀）。"""
    registry = MMTActionRegistry()
    registry.register(ActionSpec(
        "mmt_chat",
        parse_mmt_chat,
        APPROVAL_AUTO,
        prompt_fields=MMT_RUNTIME_FIELDS,
        payload_schema=(
            "operation: 可选, 模拟手机操作说明（如 '点击气泡' '已读不回'）;\n"
            "      缺省表示普通文字回复\n"
            "对白写在 reply 字段（外壳字段, 角色说的话）——这是本动作的核心输出"
        ),
    ))
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
            "附带的话写在 reply 字段"
        ),
    ))
    registry.register(ActionSpec(
        "mmt_trigger_bond_story",
        parse_mmt_trigger_bond_story,
        APPROVAL_AUTO,
        prompt_fields=MMT_RUNTIME_FIELDS,
        payload_schema=(
            "reason: 可选, 触发理由（你判断此刻关系到了新阶段）——供追溯\n"
            "用途: 羁绊剧情触发是 bool 判定（算法好感度 + 你自行判断）——\n"
            "      你判断此刻是羁绊剧情时刻才输出此动作; 引擎按好感度门槛校验,\n"
            "      true 则切换羁绊剧情模式（你继续生成剧情, 输出 BondOutput 并\n"
            "      控制表情/立绘）, false 则拒绝并继续聊天"
        ),
    ))
    return registry
