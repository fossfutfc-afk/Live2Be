"""tkinter 界面 —— 只负责"显示 + 选目录 + 调 checks"，**不放判断**。

为什么是 tkinter 而不是复用 webgui: 这个工具要在"主程序还没配好"的时候用, 不能依赖
HTTP 服务、也不该再背一遍浏览器/WebView2/pythonnet 那套（见 PROCEED §5b 22/23）。
tkinter 是 stdlib, PyInstaller 支持最成熟。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from infra import settings
from setup_tool import checks

_COLORS = {checks.OK: "#1b7f3b", checks.WARN: "#a8690b", checks.BAD: "#b3261e",
           checks.INFO: "#4a5568"}


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Live2Be 配置助手")
        self.root.geometry("980x620")
        self.root.minsize(760, 480)

        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="重新体检", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(bar, text="选素材目录…", command=self.pick_assets).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="选角色卡目录…", command=self.pick_config).pack(side=tk.LEFT)
        ttk.Button(bar, text="选数据目录…", command=self.pick_data).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="打开数据目录", command=lambda: self.open_folder("data")).pack(side=tk.LEFT)
        ttk.Button(bar, text="清空 [paths] 覆盖", command=self.clear_paths).pack(side=tk.LEFT, padx=6)

        self.text = tk.Text(self.root, wrap="word", padx=12, pady=10,
                            font=("Consolas", 10), borderwidth=0)
        self.text.pack(fill=tk.BOTH, expand=True)
        for level, color in _COLORS.items():
            self.text.tag_configure(level, foreground=color)
        self.text.configure(state=tk.DISABLED)

        self.status = ttk.Label(self.root, padding=(12, 6), text="")
        self.status.pack(fill=tk.X)
        self.refresh()

    # -- 显示 --------------------------------------------------------------
    def _write(self, checks_: list[checks.Check]) -> None:
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        group = ""
        for c in checks_:
            if c.group != group:
                group = c.group
                self.text.insert(tk.END, f"\n{group}\n", ("info",))
            self.text.insert(tk.END, "  " + c.line() + "\n", (c.level,))
        self.text.configure(state=tk.DISABLED)
        s = checks.summary(checks_)
        msg = f"共 {len(checks_)} 项：正常 {s['ok']} · 注意 {s['warn']} · 问题 {s['bad']}"
        if s["bad"] or s["warn"]:
            msg += "　—— 有问题的那几行会说明它会导致什么降级"
        self.status.configure(text=msg)

    def refresh(self) -> None:
        self._write(checks.run_all())

    # -- 改配置 ------------------------------------------------------------
    def _write_paths(self, **roots: str) -> None:
        try:
            path = checks.write_paths(**roots)
        except Exception as e:                   # noqa: BLE001 — 写不进去要让用户看见
            messagebox.showerror("写配置失败", f"{type(e).__name__}: {e}")
            return
        messagebox.showinfo(
            "已保存",
            f"已写入 {path}\n\n注意：[paths] 是启动时读取的 —— "
            "**要重启 Live2Be 才生效**。")
        self.refresh()

    def pick_assets(self) -> None:
        d = filedialog.askdirectory(title="选素材目录（立绘 / 背景 / menu）")
        if d:
            self._write_paths(assets=d)

    def pick_config(self) -> None:
        d = filedialog.askdirectory(title="选角色卡目录（characters/ 的父目录）")
        if d:
            self._write_paths(config=d)

    def pick_data(self) -> None:
        d = filedialog.askdirectory(title="选数据目录（事件流 / 记忆 / 日志）")
        if d:
            self._write_paths(data=d)

    def clear_paths(self) -> None:
        if not messagebox.askyesno("确认", "清空 settings.toml 里的 [paths] 覆盖？\n"
                                          "（之后都用默认位置；要重启才生效）"):
            return
        raw = settings.raw()
        raw.pop("paths", None)
        try:
            settings.write(raw)
        except Exception as e:                   # noqa: BLE001
            messagebox.showerror("写配置失败", f"{type(e).__name__}: {e}")
            return
        self.refresh()

    def open_folder(self, which: str) -> None:
        from infra import paths

        target = {"data": paths.DATA_ROOT, "assets": paths.ASSETS_ROOT,
                  "config": paths.CONFIG_ROOT}.get(which)
        if target is None:
            return
        target.mkdir(parents=True, exist_ok=True)
        from webgui import serve

        serve.open_folder(str(Path(target)))

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:
    App().run()
