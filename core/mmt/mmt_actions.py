"""MMT 域动作 — MomoTalk 运行时（动作名带 mmt_ 前缀）。

动作集（v1, 全部 APPROVAL_AUTO——运行时校验通过即执行）:
    mmt_chat                 说一句话（对白在 reply 字段, 可选模拟手机操作）
    mmt_inspect_character    查角色资料（回灌给 LLM 继续推理; 访问层级由
                             interperson 权重决定, 见 core/parsing/relation_parser.py）
    mmt_send_media           发图片（禁视频; 图片先查资源库, 库内没有才生成）
    mmt_trigger_bond_story   触发羁绊剧情

设计决策:
    - mmt_ 前缀: 动作名自带域标识——LLM 输出 / schema 渲染 / 历史记载
      一眼可辨是 MMT 动作, 不依赖额外 domain 字段。
    - 历史记载: 每轮至少记动作名 + reply（用户可追溯 agent 干了什么）;
      history 格式在 momotalk 全 JSON 化时一并清理。
    - 禁视频: 项目没有视频生成能力——mmt_send_media 只允许图片,
      media_type 白名单 = {'image'}, 传 video 会被硬性拒绝并回灌给 LLM。
    - 图片管线: 先查资源库（library_id）, 库内没有现成图才按 image 描述生成。
    - 外壳字段统一走 RUNTIME_SHELL_FIELDS + reply（运行时动作, 无 sources/basis）,
      所有动作都有 reply 位置承载对白/给用户的话。

TODO（后续 session）:
    - core/parsing/relation_parser.py 落地后, inspect 的访问层级决定才真正生效
    - mmt_trigger_bond_story 的触发条件（羁绊值/前置剧情）在 trigger.py 规划中
    - mmt_executor.py 按 approval=auto 执行动作, 结果回灌给 LLM 继续推理
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
# mmt_inspect_character — 查角色资料
# ============================================================================

def parse_mmt_inspect_character(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。

    只校验请求结构; 访问层级由执行层按 interperson 权重决定。
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

    只校验请求结构; 触发条件（羁绊值/前置剧情）由执行层校验。
    """
    story_id = payload.get("story_id")
    if not is_valid_identifier(story_id):
        raise ContractError(
            f"story_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {story_id!r}"
        )
    return {"story_id": story_id}


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
            "character_id: 要查资料的角色 id\n"
            "用途: 玩家提及角色关系/想了解某角色时先调用——查出的资料回灌给你继续推理, "
            "不是给玩家的文字\n"
            "访问层级由 interperson 权重决定（1=只见 profile, 2=+personality, "
            "3=+experience）, 查不到的角色视为不认识"
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
            "story_id: 要触发的羁绊剧情 id\n"
            "用途: 满足羁绊触发条件时启动剧情; 执行层校验剧情存在与触发条件"
        ),
    ))
    return registry
