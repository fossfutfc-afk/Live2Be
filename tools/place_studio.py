# -*- coding: utf-8 -*-
"""place_studio.py — 背景资产生体归纳工作台（docs/DESIGN_PLACE.md 配套工具）。

两种用法（同一扫描分组内核）:
  A. 项目内:  python tools/place_studio.py
             —— 处理项目 assets/background（全量或 --dir 限定）
  B. 外部工作区（tempo）:  python tools/place_studio.py --bg-root D:\\myStuff\\tempo
             --dir BG_Abandoned
             —— 处理你整理中的目录; 进度/实体表写在 bg-root 下
  （tempo 下放 place_studio.py 薄启动器即可——import 本项目 tools/place_studio）

流程: 扫描 bg-root → (目录, scene 族) 分组（变体自动同族）→ 逐组看图 →
中文语义名 / region / active(剔除) / 备注 → 进度断点续做 → E 导出实体表
（导出按 scene_id 键 merge 累加——逐目录处理, 最后合成一张表）。

数据（均在 bg-root 下）:
  _place_review.json      审阅进度（断点续做）
  _place_entities.json    实体表导出（{scene_id: {name, region, files{day,night}}}）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.media.background import VARIANT_TOKENS, derive_background     # noqa: E402

#: scene_id 尾部噪声（数字/时刻后缀 → 同族自动合并; scene 已 snake 小写）
_TAIL_RE = re.compile(
    r"_(?:[0-9]+|(?:%s)(?:_[0-9]+)?)$" % "|".join(sorted(VARIANT_TOKENS)))


def root_of(scene_id: str) -> str:
    return _TAIL_RE.sub("", scene_id) or scene_id


def variant_of(stem: str) -> str:
    """文件名 → variant（derive_background 的 variant; 无 → day）。"""
    return derive_background(stem)[1] or "day"


def scan_groups(bg_root: Path, only_dir: str | None = None) -> list[dict]:
    """扫描 bg_root 下全部图片 → (目录, scene 族) 分组（含 files 按昼夜归位）。

    bg_root 结构: {bg_root}/{BG_*}/{BG_Scene[_Variant]}.jpg
    命名解析走 core.media.background.derive_background（camelCase → snake + 变体白名单）。
    """
    groups: dict[tuple[str, str], dict] = defaultdict(lambda: {"files": []})
    for d in sorted(p for p in bg_root.iterdir() if p.is_dir()):
        if only_dir and d.name != only_dir:
            continue
        if d.name.startswith("."):
            continue
        for f in sorted(d.glob("*.jpg")) + sorted(d.glob("*.png")):
            if not f.stem.startswith("BG_"):
                continue
            scene, var = derive_background(f.stem)
            key = (d.name, root_of(scene))
            groups[key]["files"].append({
                "file": f"{d.name}/{f.name}",
                "variant": var or "day",
            })
    items = []
    for (d, scene), g in sorted(groups.items()):
        files = g["files"]
        day = [x["file"] for x in files if x["variant"] == "day"]
        night = [x["file"] for x in files if x["variant"] != "day"]
        items.append({
            "key": f"{d}|{scene}",
            "dir": d,
            "root": scene,
            "files": day + night,              # 默认白天在前
            "night": night,
            "suspect": d == "BG_Other",
        })
    return items


# ---------------------------------------------------------------------------
# 服务
# ---------------------------------------------------------------------------

BG_ROOT: Path = None  # type: ignore
_lock = threading.Lock()


def _review_path() -> Path:
    return BG_ROOT / "_place_review.json"


def _export_path() -> Path:
    return BG_ROOT / "_place_entities.json"


def _load_review() -> dict:
    p = _review_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save_review(data: dict) -> None:
    with _lock:
        _review_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _thumb(rel: str, size: int = 480) -> Path:
    from PIL import Image
    src = BG_ROOT / rel
    tgt = BG_ROOT / ".thumbs" / rel
    if tgt.exists():
        return tgt
    try:
        tgt.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im.thumbnail((size, size))
            im.convert("RGB").save(tgt, "JPEG", quality=78)
    except Exception:
        return src
    return tgt


def build_app():
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    app = FastAPI(title="place_studio")
    _items: list[dict] = []

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _PAGE

    @app.get("/api/items")
    def api_items():
        review = _load_review()
        items = []
        for it in _items:
            it = dict(it)
            it["done"] = review.get(it["key"])
            items.append(it)
        pending = [i for i in items if not i["done"]]
        return {"total": len(items), "done": len(items) - len(pending),
                "pending": pending, "items": items}

    @app.get("/api/thumb")
    def api_thumb(f: str):
        p = _thumb(f)
        if not p.exists():
            return Response(status_code=404)
        return Response(p.read_bytes(), media_type="image/jpeg")

    @app.post("/api/review")
    async def api_review(body: dict):
        key = str(body.get("key", ""))
        if not key:
            return JSONResponse({"ok": False, "error": "缺 key"}, status_code=400)
        data = _load_review()
        data[key] = {
            "name": str(body.get("name") or "").strip(),
            "region": str(body.get("region") or "").strip(),
            "keywords": str(body.get("keywords") or "").strip(),
            "active": bool(body.get("active", True)),
            "note": str(body.get("note") or "").strip(),
        }
        _save_review(data)
        return {"ok": True, "saved": len(data)}

    @app.get("/api/export")
    def api_export():
        """review + 扫描组 → 实体表（merge 累加——逐目录处理后合成一张表）。"""
        review = _load_review()
        merged: dict = {}
        p = _export_path()
        if p.exists():
            try:
                merged = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                merged = {}
        added = 0
        for it in _items:
            rv = review.get(it["key"])
            if not rv or not rv.get("active", True):
                continue
            day = [f for f in it["files"] if f not in it["night"]]
            merged[it["root"]] = {
                "name": rv.get("name") or it["root"],
                "region": rv.get("region", ""),
                "keywords": [k.strip() for k in str(rv.get("keywords") or "").split(",") if k.strip()],
                "files": {"day": day, "night": list(it["night"])},
            }
            added += 1
        with _lock:
            p.write_text(json.dumps(merged, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        return {"ok": True, "path": str(p), "count": len(merged), "added": added}

    @app.post("/api/suggest")
    async def api_suggest(body: dict):
        root = str(body.get("root") or "")
        dir_ = str(body.get("dir") or "")
        try:
            from llm.client import LLMClient
            client = LLMClient()
            prompt = (
                "你是蔚蓝档案(Blue Archive)场景命名助手。把背景资产 id 翻译成"
                "简短中文语义名（角色剧情里会说的地点名, 4-12 字）。\n"
                f"目录: {dir_}\nid: {root}\n"
                "给出 3 个候选（json 对象 {\"names\": [...]}）:\n"
                "规则: 学园名用官方译名（gehenna=格黑娜, trinity=圣三一, "
                "wildhunt=狂猎美术, abydos=阿拜多斯, schale=夏莱, "
                "hyakkiyako=百鬼夜行, millennium=千年）; 剧情专属场景（人名/事件名）"
                "标注为\"剧情专属\"前缀提示作者确认;\n"
                "额外给 2-4 个同义检索词（剧情里的俗称/描述词, 如破屋/老屋）;\n"
                "只输出 JSON {\"names\": [...], \"keywords\": \"词1, 词2\"}。"
            )
            resp = client.chat(messages=[{"role": "user", "content": prompt}],
                               temperature=0.3, max_tokens=200,
                               response_format="json_object")
            arr = (resp.get("names") if isinstance(resp, dict) else [])
            names = [str(x).strip() for x in arr if str(x).strip()][:3]
            kw = str((resp.get("keywords") if isinstance(resp, dict) else "") or "")
            return {"names": names, "keywords": kw}
        except Exception as e:                              # noqa: BLE001
            return {"names": [], "error": str(e)}

    def _set_items(items: list[dict]) -> None:
        nonlocal _items
        _items = items

    app._set_items = _set_items  # type: ignore
    return app


# ---------------------------------------------------------------------------
# 页面（与组 key/文件 chip/命名一致）
# ---------------------------------------------------------------------------

_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>place_studio — 背景实体归纳</title>
<style>
  body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0;
         background: #1b1f27; color: #dfe4ee; }
  header { padding: 10px 18px; background: #242a35; display: flex; gap: 14px;
           align-items: center; position: sticky; top: 0; z-index: 5; }
  header b { color: #ffd166; }
  #stage { display: flex; height: calc(100vh - 52px); }
  #gallery { flex: 1.6; display: flex; align-items: center; justify-content: center;
             background: #12151b; }
  #gallery img { max-width: 96%; max-height: 96%; object-fit: contain;
                 box-shadow: 0 8px 30px rgba(0,0,0,.5); border-radius: 4px; }
  #side { flex: 1; padding: 16px 20px; overflow-y: auto; }
  .kv { margin: 10px 0; }
  .kv label { display: block; font-size: 12px; color: #8a93ad; margin-bottom: 4px; }
  input[type=text] { width: 100%; padding: 8px; border-radius: 6px;
        border: 1px solid #3a4356; background: #242a35; color: #dfe4ee; font-size: 15px; }
  .suggest { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }
  .suggest button { border: 1px solid #4a5670; background: #2d3545; color: #cfe0ff;
        padding: 5px 10px; border-radius: 6px; cursor: pointer; }
  .bar { display: flex; gap: 10px; margin-top: 18px; }
  .bar button { flex: 1; padding: 10px; font-size: 15px; border-radius: 8px;
        border: none; cursor: pointer; }
  #saveNext { background: #3d7eff; color: #fff; }
  #skip { background: #3a4356; color: #cfd6e4; }
  #imgNav { color: #8a93ad; font-size: 12px; }
  .filechip { display: inline-block; font-size: 11px; background: #2d3545;
        padding: 2px 8px; border-radius: 10px; margin: 2px; cursor: pointer; }
  .filechip.on { border-color: #ffd166; background: #4a3f22; }
  #progress { font-size: 13px; color: #9aa4b8; }
  #badge { margin-left: auto; }
  #badge span { background:#2d3545; padding:3px 10px; border-radius: 12px; font-size:12px; }
  .nightchip { border-style: dashed; }
</style></head><body>
<header>
  <b>place_studio</b>
  <span id="cur"></span><span id="progress"></span>
  <span id="badge"><span id="badgeText"></span></span>
</header>
<div id="stage">
  <div id="gallery"><img id="mainImg" alt=""></div>
  <div id="side">
    <div class="kv"><label>组键（目录 | 场景）</label><div id="key" style="font-size:13px;color:#9aa4b8"></div></div>
    <div class="kv"><label>文件（点击查看; 虚线 = 夜/变体）</label>
      <div id="files"></div><div id="imgNav"></div></div>
    <div class="kv"><label>中文语义名</label>
      <input id="name" type="text" placeholder="输入中文名（如 废墟走廊）">
      <div class="suggest" id="suggestRow"></div>
    </div>
    <div class="kv"><label>keyword（可选——同义检索词, 逗号分隔: 剧情俗称/描述词）</label>
      <input id="keywords" type="text" placeholder="如: 破屋, 老屋, 秘密基地（重要主场才填）"></div>
    <div class="kv"><label>region（可选: gehenna / schale / oldtown…）</label>
      <input id="region" type="text" placeholder="剧情地理（子集注入用, 可留空）"></div>
    <div class="kv"><label><input id="active" type="checkbox" checked> 活跃（进实体表）</label></div>
    <div class="kv"><label>备注</label><input id="note" type="text"></div>
    <div class="bar">
      <button id="saveNext">保存并下一组 (Enter)</button>
      <button id="skip">跳过 (S)</button>
    </div>
    <div style="margin-top:12px;font-size:12px;color:#6c7590">
      ←/→ 翻组内图 · G 生成建议 · E 导出实体表（merge）· 已审可回改</div>
  </div>
</div>
<script>
const $ = id => document.getElementById(id);
let items = [], idx = 0, imgIdx = 0;
async function boot() {
  const r = await (await fetch("/api/items")).json();
  items = r.items;
  idx = items.findIndex(i => !i.done);
  if (idx < 0) idx = 0;
  $("badgeText").textContent = `已审 ${r.done}/${r.total}`;
  render();
}
function cur() { return items[idx]; }
function render() {
  const it = cur();
  $("cur").textContent = `${idx + 1} / ${items.length}`;
  $("progress").textContent = it.done ? "已审 — 可改后覆盖" : (it.suspect ? "⚠ 杂物袋/需看图" : "");
  $("key").textContent = it.key;
  $("files").innerHTML = "";
  const nights = it.night || [];
  it.files.forEach((f, i) => {
    const c = document.createElement("span");
    c.className = "filechip" + (nights.includes(f) ? " nightchip" : "") +
                  (i === imgIdx ? " on" : "");
    c.textContent = f.split("/").pop();
    c.title = nights.includes(f) ? "夜/变体" : "白天";
    c.onclick = () => { imgIdx = i; renderImg(); };
    $("files").appendChild(c);
  });
  $("imgNav").textContent = `${it.files.length} 张（${nights.length} 夜/变体）`;
  $("name").value = (it.done && it.done.name) || "";
  $("keywords").value = (it.done && it.done.keywords) || "";
  $("region").value = (it.done && it.done.region) || "";
  $("active").checked = it.done ? it.done.active : true;
  $("note").value = (it.done && it.done.note) || "";
  renderImg(); renderSuggest(); $("name").focus();
}
function renderImg() {
  const it = cur();
  if (!it || !it.files.length) return;
  imgIdx = Math.min(imgIdx, it.files.length - 1);
  $("mainImg").src = `/api/thumb?f=${encodeURIComponent(it.files[imgIdx])}`;
  [...$("files").children].forEach((c, i) => c.classList.toggle("on", i === imgIdx));
}
async function renderSuggest() {
  const it = cur();
  $("suggestRow").innerHTML = "";
  if (it.done && it.done.name) return;
  const btn = document.createElement("button");
  btn.textContent = "⚡ LLM 建议中文名";
  btn.onclick = async () => {
    btn.disabled = true; btn.textContent = "生成中…";
    try {
      const r = await (await fetch("/api/suggest", { method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ root: it.root, dir: it.dir }) })).json();
      (r.names || []).forEach(n => {
        const b = document.createElement("button");
        b.textContent = n;
        b.onclick = () => { $("name").value = n; };
        $("suggestRow").appendChild(b);
      });
      if (r.keywords) {
        const k = document.createElement("button");
        k.textContent = "🔑 " + r.keywords;
        k.onclick = () => { $("keywords").value = r.keywords; };
        $("suggestRow").appendChild(k);
      }
      if (!r.names || !r.names.length) btn.textContent = "无建议";
    } catch (e) { btn.textContent = "建议失败"; }
    btn.style.display = "none";
  };
  $("suggestRow").appendChild(btn);
}
async function saveNext() {
  const it = cur();
  await fetch("/api/review", { method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ key: it.key, name: $("name").value,
      region: $("region").value, keywords: $("keywords").value,
      active: $("active").checked, note: $("note").value }) });
  it.done = true;
  if (idx < items.length - 1) idx++;
  imgIdx = 0; render();
}
function skip() { if (idx < items.length - 1) idx++; imgIdx = 0; render(); }
document.addEventListener("keydown", e => {
  if (e.key === "Enter" && e.target.tagName !== "BUTTON") { e.preventDefault(); saveNext(); }
  else if ((e.key === "s" || e.key === "S") && e.target.tagName !== "INPUT") skip();
  else if (e.key === "ArrowRight") imgIdx++;
  else if (e.key === "ArrowLeft") imgIdx--;
  else if (e.key === "g" || e.key === "G") document.querySelector("#suggestRow button")?.click();
  else if (e.key === "e" || e.key === "E") exportEntities();
  renderImg();
});
$("saveNext").onclick = saveNext;
$("skip").onclick = skip;
async function exportEntities() {
  const r = await (await fetch("/api/export")).json();
  alert(`实体表已导出: 累计 ${r.count} 条（本次 ${r.added}）→ ${r.path}`);
}
boot();
</script></body></html>"""


def main() -> None:
    global BG_ROOT
    ap = argparse.ArgumentParser(description="背景资产生体归纳工作台（目录模式）")
    ap.add_argument("--bg-root", default=str(PROJECT_ROOT / "assets" / "background"),
                    help="图片根（tempo 模式: D:\\myStuff\\tempo）")
    ap.add_argument("--dir", default="",
                    help="只处理指定子目录（如 BG_Abandoned）; 空 = 全部")
    ap.add_argument("--port", type=int, default=8811)
    args = ap.parse_args()

    BG_ROOT = Path(args.bg_root)
    if not BG_ROOT.is_dir():
        print(f"bg-root 不存在: {BG_ROOT}")
        raise SystemExit(1)
    items = scan_groups(BG_ROOT, only_dir=args.dir or None)
    if not items:
        print(f"未扫描到图片（{BG_ROOT}{'/' + args.dir if args.dir else ''}）——"
              f"检查目录结构与 BG_ 前缀命名")
        raise SystemExit(1)
    total_files = sum(len(i["files"]) for i in items)
    import uvicorn
    app = build_app()
    app._set_items(items)                       # type: ignore
    scope = f" --dir {args.dir}" if args.dir else "（全部目录）"
    print(f"place_studio: http://127.0.0.1:{args.port}  "
          f"组 {len(items)} / 图 {total_files}  {scope}")
    print(f"进度: {BG_ROOT / '_place_review.json'}  "
          f"导出: {BG_ROOT / '_place_entities.json'}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
