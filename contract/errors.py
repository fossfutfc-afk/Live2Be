"""统一错误格式 — [xxx.py][errtype][errinfo]

全项目错误消息统一携带来源文件与错误类型，报错即知来自哪个文件（追溯/调试）。

⚠️ **位置**（C10, `docs/EXEC_SPLIT.md`）: 本模块是**错误原语的唯一真家**，住在
`contract/`（最底层）——`contract/{model,registry,spec}.py` 用它不再需要反向依赖
`core`。`core/common/errors.py` 只剩一个**薄再导出**壳（保旧路径）。

两种用法（不改动现有异常捕获语义）:
    1. 域异常 —— 定义 Live2BeError 子类（类留在各自域文件里，分散定义、统一继承）。
       __str__ 自动产出 [file.py][ClassName][info]：file 从类所在模块推导
       （contract.model → model.py），errtype 默认类名。
    2. 标准异常 —— raise ValueError(err("NotFound", "档案不存在"))：
       保持原异常类型（except ValueError 照常命中），err() 只格式化消息字符串，
       file 从调用帧自动取（err() 在 raise 表达式里直接调用）。

约定: 全项目 raise 的错误消息必须符合该格式——域异常继承 Live2BeError，
标准异常用 err() 包装。这是项目追溯性的地基，勿绕开。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _module_file(cls: type) -> str:
    """从异常类所在模块推导文件名（contract.model → model.py）。"""
    module = cls.__module__.rsplit(".", 1)[-1]
    return f"{module}.py" if module else "???.py"


class Live2BeError(Exception):
    """统一错误基类：__str__ 自动产出 [xxx.py][errtype][errinfo]。

    errtype 默认 = 类名（如 ExecError / ContractError / NotInSessionError）。
    """

    def __str__(self) -> str:
        info = self.args[0] if self.args else ""
        return f"[{_module_file(type(self))}][{type(self).__name__}][{info}]"


def err(errtype: str, info: str) -> str:
    """标准异常场合：生成 [xxx.py][errtype][errinfo] 格式消息（不改异常类型）。

    file 从调用帧自动取——err() 必须在 raise 表达式里直接调用，勿包进中间函数。
    """
    frame = sys._getframe(1)
    fname = Path(frame.f_code.co_filename).name
    return f"[{fname}][{errtype}][{info}]"
