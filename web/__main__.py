"""web 包入口: python -m web → 启动 IDE agent GUI 服务。

环境变量:
    IDE_MOCK=1     用 StubLLM（无 API, 走 mock 流程）
    WEB_PORT       端口（默认 8000）
    WEB_HOST       监听地址（默认 127.0.0.1, 仅本机）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 项目根入 sys.path（web/ 下的相对 import 依赖 contract/ fetch/ ui/ 等）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    import uvicorn

    import web.app as web_app

    host = os.getenv("WEB_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_PORT", "8000"))
    mock = os.getenv("IDE_MOCK") == "1"
    print(f"Live2Be IDE GUI → http://{host}:{port}/   (mock={'ON' if mock else 'OFF'})")
    uvicorn.run(web_app.app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
