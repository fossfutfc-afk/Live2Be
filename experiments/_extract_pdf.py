"""提取 a-mem.pdf 文本到 txt（供 read 工具精读）。"""
import sys
from pathlib import Path

from pypdf import PdfReader

src = Path(r"C:\Users\johnf\Desktop\a-mem.pdf")
out = Path(r"C:\Users\johnf\Desktop\_a-mem.txt")
reader = PdfReader(str(src))
print("pages:", len(reader.pages))
parts = []
for i, page in enumerate(reader.pages):
    text = page.extract_text() or ""
    parts.append(f"\n\n===== PAGE {i + 1} =====\n{text}")
out.write_text("".join(parts), encoding="utf-8")
print("chars:", sum(len(p) for p in parts))
