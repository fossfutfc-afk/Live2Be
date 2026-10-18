# -*- mode: python ; coding: utf-8 -*-
"""「资源配置」辅助工具 —— **onefile**（单个 exe，没有 `_internal/`）。

为什么它和主程序不一样: 主程序 onedir（启动快、资产在外部），而这个工具要**跟主程序
放在同一个目录**里（`dist/Live2Be/Live2BeSetup.exe`）—— 两个 onedir 会抢同一个
`_internal/` 目录名。onefile 没有那个目录，且它的 `APP_ROOT` = exe 所在目录，正好和
主程序共用同一份 `settings.toml` / `config` / `assets` / `data`。

构建: `pwsh packaging/build.ps1`（会顺带把它拷进 `dist/Live2Be/`）
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent          # 本文件在 packaging/ 下

#: 角色卡加载要读 llm/prompts/behavior_rules.md 这类文案（Path(__file__).parent）
#: ⇒ 这三处必须跟着进包, 否则"体检角色卡"自己先炸（真机踩到过）。
DATAS = [
    (str(ROOT / "llm" / "prompts"), "llm/prompts"),
    (str(ROOT / "contract" / "schema" / "prompts"), "contract/schema/prompts"),
    (str(ROOT / "contract" / "digest" / "prompts"), "contract/digest/prompts"),
]

a = Analysis(
    [str(ROOT / "setup_tool" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=DATAS,
    hiddenimports=["setup_tool.checks", "setup_tool.main", "setup_tool.ui"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tests", "experiments", "tools", "archive", "l2d-demo", "packaging",
        "pytest", "networkx", "matplotlib", "pyvis", "IPython",
        # 主程序的 web 栈不该被拖进来（工具只需要 infra/core 那几件）
        "fastapi", "uvicorn", "starlette", "httpx",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Live2BeSetup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # 保留控制台: `--check` 要能打报告（窗口版另有界面）
    disable_windowed_traceback=False,
    icon=None,
)
