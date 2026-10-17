# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec —— **onedir**（启动快、杀软友好、资产在 exe 同级）。

构建别直接跑 pyinstaller, 用 `pwsh packaging/build.ps1`（它还负责把 config/ 与样张
拷到 exe 同级, 并报体积）。

目录形状（PyInstaller 6 起 onedir 会把捆绑物放 `_internal/`）::

    dist/Live2Be/
      Live2Be.exe
      _internal/          ← 代码 + 前端静态 + 三处 prompts（RESOURCE_ROOT）
      config/             ← 角色卡 / 世界观（CONFIG_ROOT；程序不写）
      assets/             ← 样张（ASSETS_ROOT；程序不写）
      data/               ← 首次运行自动创建的事件流与记忆（DATA_ROOT）
      settings.toml .env  ← 首次运行前由用户填（APP_ROOT）

`infra/paths.py` 就是按这个形状写的: 冻结后 `APP_ROOT = exe 同级`,
`RESOURCE_ROOT = sys._MEIPASS`。
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent          # 本文件在 packaging/ 下

#: 必须在**包内**（RESOURCE_ROOT）的只读件: 前端静态页 + 三处 LLM 可见文案
DATAS = [
    (str(ROOT / "webgui" / "static"), "webgui/static"),
    (str(ROOT / "contract" / "schema" / "prompts"), "contract/schema/prompts"),
    (str(ROOT / "contract" / "digest" / "prompts"), "contract/digest/prompts"),
    (str(ROOT / "llm" / "prompts"), "llm/prompts"),
]

#: 静态分析看不见的: uvicorn 按名字挑实现, 还有我们自己用字符串拼过的模块
HIDDEN = [
    "uvicorn.logging",
    "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
    "starlette.staticfiles", "starlette.responses",
    "webgui.app", "webgui.serve",
]

#: 不进包的东西: 测试/实验/开发依赖（它们不是运行时的一部分）
EXCLUDES = [
    "tests", "experiments", "tools", "archive", "l2d-demo", "packaging",
    "pytest", "networkx", "matplotlib", "pyvis", "IPython", "tkinter",
]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Live2Be",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                       # upx 压过的 exe 更容易被杀软拦
    console=True,                    # 先留控制台: 出错看得见（用户级发布可改 False）
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Live2Be",
)
