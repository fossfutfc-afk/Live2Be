#!/usr/bin/env python
"""imgdesc — describe image files (PNG/JPG/...) with the LOCAL Qwen2.5-VL vision model.

A CLI so that Claude Code (or any shell tool) can "see" images:

    imgdesc photo.png
    imgdesc scene.png "Is there a cat in this image?"
    imgdesc a.png b.png --json
    imgdesc *.png --brief

Powered by the local Bionic/LM Studio server (http://localhost:1234/v1)
with Qwen2.5-VL-7B-Instruct. The server is auto-started if it is down.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

from openai import OpenAI

BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "qwen2.5-vl-7b-instruct"
LMS = r"C:\Users\johnf\.lmstudio\bin\lms.exe"

SYSTEM_PROMPT = (
    "You are an image analysis assistant for a coding AI that cannot see images. "
    "Describe the image(s) thoroughly and precisely so that another AI can fully "
    "understand the content from your text alone: main subject(s), every visible "
    "object, any readable text (quote it verbatim), colors, composition/layout, "
    "style, and notable details or anomalies. If a specific question is asked, "
    "answer it directly first, then add brief context."
)


def server_alive(timeout=3):
    try:
        req = urllib.request.Request(f"{BASE_URL}/models")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def start_server(max_wait=60):
    print("[imgdesc] local model server is down, starting it...", file=sys.stderr)
    try:
        subprocess.run([LMS, "server", "start"], capture_output=True, timeout=30)
    except Exception as e:
        print(f"[imgdesc] failed to start server: {e}", file=sys.stderr)
        return False
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if server_alive(2):
            return True
        time.sleep(2)
    return False


def main():
    ap = argparse.ArgumentParser(
        description="Describe images using the local Qwen2.5-VL vision model.")
    ap.add_argument("images", nargs="+", help="image file path(s), e.g. *.png")
    ap.add_argument("-q", "--question", help="specific question to ask about the image(s)")
    ap.add_argument("--brief", action="store_true", help="one-line summary per image only")
    ap.add_argument("--json", action="store_true", help="emit a JSON result")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"vision model key (default: {DEFAULT_MODEL})")
    ap.add_argument("--max-tokens", type=int, default=900)
    ap.add_argument("--no-autostart", action="store_true",
                    help="do not auto-start the local server")
    args = ap.parse_args()

    # Friendliness: "imgdesc a.png what is this?" — if the last positional is not
    # an existing file, treat it as the question.
    if args.question is None and len(args.images) > 1 and not os.path.isfile(args.images[-1]):
        args.question = args.images.pop()

    missing = [p for p in args.images if not os.path.isfile(p)]
    if missing:
        print(f"[imgdesc] error: file not found: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)

    if not server_alive():
        if args.no_autostart:
            print("[imgdesc] error: local model server is not running on :1234 "
                  "(run: lms server start)", file=sys.stderr)
            sys.exit(3)
        if not start_server():
            print("[imgdesc] error: could not start the local model server", file=sys.stderr)
            sys.exit(3)

    client = OpenAI(base_url=BASE_URL, api_key="lm-studio")

    content = []
    if args.question:
        content.append({"type": "text", "text": args.question})
    if args.brief:
        content.append({"type": "text",
                        "text": "Give a concise one-line summary for each image, numbered."})
    for i, p in enumerate(args.images, 1):
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        if len(args.images) > 1:
            content.append({"type": "text",
                            "text": f"[Image {i}: {os.path.basename(p)}]"})
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}})

    try:
        resp = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            max_tokens=args.max_tokens,
            temperature=0.2,
        )
    except Exception as e:
        print(f"[imgdesc] error: {e}", file=sys.stderr)
        sys.exit(4)

    text = resp.choices[0].message.content or ""

    if args.json:
        print(json.dumps({
            "tool": "imgdesc",
            "model": args.model,
            "images": [os.path.abspath(p) for p in args.images],
            "question": args.question,
            "description": text,
        }, ensure_ascii=False, indent=2))
    else:
        print(text)


if __name__ == "__main__":
    main()
