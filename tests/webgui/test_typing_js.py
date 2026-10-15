"""前端纯逻辑的单测入口 —— 跑 `node --test tests/webgui/js/`。

前端的自动化守门此前几乎为零；`typing.js` 是第一个能脱离 DOM 单测的模块
（节奏计算 + 顺序揭示队列，2026-10-08 那个"整批延迟恒为 0"的坑就住在这里）。

套一层 pytest 是为了让 `pytest tests/webgui` 顺手覆盖它，不必另记一条命令。
⚠️ 需要 node（本机 v24）。没有 node 就跳过——前端测试不该拖垮 Python 侧的回归。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEST_JS = ROOT / "tests" / "webgui" / "js" / "typing.test.js"


def test_typing_js_unit_tests():
    node = shutil.which("node")
    if node is None:
        pytest.skip("没装 node —— 前端单测跳过")
    try:
        r = subprocess.run([node, "--test", str(TEST_JS)],
                           cwd=ROOT, capture_output=True, text=True)
    except OSError as e:                      # 沙箱里起不了子进程（拿不到管道）
        pytest.skip(f"跑不了 node 子进程: {e}")
    if r.returncode != 0:
        print(r.stdout[-4000:])
        print(r.stderr[-2000:])
    assert r.returncode == 0, "typing.js 的 node 单测红了（见上面的输出）"
    print("    js: typing.js 的 node 单测通过")
