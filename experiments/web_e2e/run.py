# -*- coding: utf-8 -*-
"""web E2E 冒烟驱动器 — 桩世界（真 app） + Playwright（真浏览器） + 留档。

一步跑完:
    python experiments/web_e2e/run.py            # 默认本机 Chrome, headless
    python experiments/web_e2e/run.py --headed   # 看见窗口（调试用）
    python experiments/web_e2e/run.py --edge     # 用 Edge 而非 Chrome

产物（默认 .testtmp/webtest/<时间戳>/）:
    result.json      结论（每步 info + console 错误 + 失败请求 + 非 2xx）
    *.png            逐步截图（人/模型都能直接看）

依赖: Playwright 的 Node 包。**不需要下载浏览器**——用本机已装的
Chrome/Edge（channel=chrome|msedge）。缺包时自动 `npm i`（跳过浏览器下载）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

HERE = Path(__file__).resolve().parent
PW_VERSION = "1.63.0"


def _npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def find_playwright() -> Path | None:
    """找可用的 playwright node 包 → 其 node_modules 目录（供 NODE_PATH）。

    先看本仓库旁的一次性安装（.testtmp/webtest/node_modules）, 再扫 npx 缓存。
    """
    local = ROOT / ".testtmp" / "webtest" / "node_modules" / "playwright"
    if local.is_dir():
        return local.parent
    cache = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "npm-cache" / "_npx"
    if cache.is_dir():
        for pkg in cache.glob("*/node_modules/playwright"):
            return pkg.parent
    return None


def install_playwright() -> Path:
    """装到 .testtmp（不污染仓库; 跳过浏览器下载——我们用系统 Chrome/Edge）。"""
    dest = ROOT / ".testtmp" / "webtest"
    dest.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"}
    print(f"[e2e] 安装 playwright@{PW_VERSION} → {dest}（跳过浏览器下载）")
    subprocess.run([_npm_cmd(), "i", "--no-save", "--prefix", str(dest),
                    f"playwright@{PW_VERSION}"],
                   check=True, env=env, cwd=str(ROOT))
    return dest / "node_modules"


def main() -> int:
    ap = argparse.ArgumentParser(description="Live2Be web E2E 冒烟")
    ap.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    ap.add_argument("--edge", action="store_true", help="用 Edge 而不是 Chrome")
    ap.add_argument("--out", default="", help="产物目录（默认 .testtmp/webtest/<ts>）")
    ap.add_argument("--port", type=int, default=0, help="桩世界端口（0=随机）")
    args = ap.parse_args()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    art = Path(args.out) if args.out else (ROOT / ".testtmp" / "webtest" / stamp)
    art.mkdir(parents=True, exist_ok=True)

    node_modules = find_playwright()
    if node_modules is None:
        node_modules = install_playwright()
    print(f"[e2e] playwright: {node_modules}")

    from experiments.web_e2e.stub_world import serve

    url, server, sid, llm = serve(port=args.port, data_root=art / "data")
    print(f"[e2e] 桩世界就绪: {url}  session={sid}")

    env = {**os.environ, "NODE_PATH": str(node_modules), "LIVE2BE_IMAGE": "off"}
    node = shutil.which("node") or "node"
    cmd = [node, str(HERE / "smoke.mjs"), url, str(art)]
    if args.headed:
        cmd.append("--headed")
    if args.edge:
        cmd.append("--edge")
    print(f"[e2e] 浏览器冒烟: {' '.join(cmd[1:])}")
    try:
        proc = subprocess.run(cmd, env=env, cwd=str(ROOT))
        code = proc.returncode
    finally:
        server.should_exit = True
        time.sleep(0.3)

    result_file = art / "result.json"
    if result_file.is_file():
        data = json.loads(result_file.read_text(encoding="utf-8"))
        print("\n=== 冒烟结论 ===")
        for s in data.get("steps", []):
            print(f"  · {s['name']}: {s.get('info', '')}")
        print(f"  console 错误: {len(data.get('consoleErrors', []))}")
        for e in data.get("consoleErrors", [])[:5]:
            print(f"      - {e}")
        print(f"  资源加载噪音: {len(data.get('resourceConsole', []))}（非 2xx 见下）")
        print(f"  失败请求: {len(data.get('failedRequests', []))}")
        for e in data.get("failedRequests", [])[:5]:
            print(f"      - {e}")
        print(f"  非 2xx 响应: {len(data.get('badResponses', []))}")
        for e in data.get("badResponses", [])[:5]:
            print(f"      - {e}")
        for e in data.get("allowedNotices", [])[:3]:
            print(f"      （白名单）{e}")
        print(f"  LLM 调用: {llm.calls}")
        print(f"  结论: {'PASS' if data.get('ok') else 'FAIL'}"
              + (f"（{data.get('error')}）" if data.get("error") else ""))
    print(f"[e2e] 产物目录: {art}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
