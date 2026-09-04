"""查看角色动作 — view_character（只读工具, 结果回灌 LLM）。

AI 在用户要求"补全/完善某角色"时先调用它, 摸清现状:
    五件套各文件 已存在(字符数)/缺失 + profile 显示名与 SIG/REQ 完整度;
    带 file 时返回该文件全文 + 完整度。
拿到结果后再决定写哪些文件——不重复已存在的内容, 不缺漏缺失的。

只读: APPROVAL_NEVER, 不落盘。契约层只校验请求结构; 读取与回灌是执行层职责。
"""

from __future__ import annotations

from typing import Any

from contract import ContractError, is_valid_identifier

from ide.actions.common import CHARACTER_FILE_SET, CHARACTER_FILES


def parse_view_character(payload: dict[str, Any]) -> dict[str, Any]:
    """结构白名单校验（硬错误, 抛 ContractError）。"""
    char_id = payload.get("character_id")
    if not is_valid_identifier(char_id):
        raise ContractError(
            f"character_id 必须匹配 [a-z0-9_]+ 且 ≤64 字符: {char_id!r}"
        )
    clean: dict[str, Any] = {"character_id": char_id}

    file = payload.get("file")
    if file is not None:
        if not isinstance(file, str) or file not in CHARACTER_FILE_SET:
            raise ContractError(
                f"file 必须是五件套之一: {', '.join(CHARACTER_FILES)} (得 {file!r})"
            )
        clean["file"] = file
    return clean
