# -*- coding: utf-8 -*-
"""会话存储 IO 原语 — 原子写 JSON / append-only JSONL（行级容错）。

设计（core/DESIGN_SAVE.md §七）:
    - meta.json / vn_state.json: atomic_write_json（temp 同目录 + os.replace,
      Windows 同卷原子替换——不半写）
    - history.jsonl / scenes.jsonl: append_jsonl（open("a") 单行追加, 不重写全文件）
      + read_jsonl（逐行 try/except, 坏行/半行丢弃, 宁缺勿错）
    - 写失败 re-raise（上层 try 包裹降级为"本轮不记录", 不阻断主流程）

注: atomic_write_json 模式与 core/bond/bond_save.py 的 _atomic_write_json 相同;
session 是独立底层, 不 import bond_save（避免依赖方向 bond→session→bond）, 故下沉于此。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


def atomic_write_json(path: str | Path, data: dict, *, indent: int = 2) -> None:
    """原子写 JSON: temp 与目标同目录 → os.replace（Windows 同卷原子替换）。

    异常清理 tmp 后 re-raise。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="._savetmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=indent)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_jsonl(path: str | Path, obj: Any) -> None:
    """追加一行 JSON 到 jsonl（open("a") 单行写, 不重写全文件）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)


def append_jsonls(path: str | Path, objs: Iterable[Any]) -> None:
    """批量追加（一轮的多条消息一次落盘, 减少 IO）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for obj in objs:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[Any]:
    """读 jsonl, 逐行容错: 坏行/半行（中断残留）→ 丢弃（宁缺勿错, 不 raise）。

    文件缺失 → []。
    """
    path = Path(path)
    if not path.is_file():
        return []
    out: list[Any] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue                      # 半行/坏行 → 丢弃
    return out
