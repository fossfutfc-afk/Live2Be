"""冻结入口 —— PyInstaller 要一个**脚本文件**（它不支持 `-m webgui.serve`）。

开发时用 `python -m webgui.serve`（等价，且多一层 `-m` 双模块的保护）；打包时 PyInstaller
从这个文件开始做静态分析，所以 `webgui.app` 必须在某个**真实 import** 里出现
（`webgui/serve.py` 的 `from webgui.app import app` 就是为此改的 —— 字符串
`"webgui.app:app"` 冻结后找不到模块）。
"""

from webgui.serve import main

if __name__ == "__main__":
    raise SystemExit(main())
