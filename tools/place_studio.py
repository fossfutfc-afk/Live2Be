# -*- coding: utf-8 -*-
"""place_studio.py — 背景资产生体归纳工作台（docs/DESIGN_PLACE.md §4 配套工具）。

看图 → 命名（中文语义名）→ region → active（剔除）→ 进度记忆断点续做。
配合 LLM 建议（逐组"建议名"按钮——调项目 LLMClient, 输入族键/词根产出中文候选）。

数据:
    输入  assets/_place_draft.json     （tools/place_organizer.py stage1 产物: 471 族）
    进度  assets/_place_review.json    （本工具写回; 重启续做）
    产出  assets/_place_entities.json  （导出: {scene_id: {name, region, active, files}}）

用法:  python tools/place_studio.py          # http://127.0.0.1:8811
      python tools/place_studio.py --port 8811
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn
from PIL import Image

from core.media.catalog import MediaCatalog        # noqa: E402

DRAFT = ROOT / "assets" / "_place_draft.json"
REVIEW = ROOT / "assets" / "_place_review.json"
EXPORT = ROOT / "assets" / "_place_entities.json"
ASSETS_BG = ROOT / "assets" / "background"

app = FastAPI(title="place_studio")
_lock = threading.Lock()
_cat = MediaCatalog()


def _load_draft() -> dict:
    return json.loads(DRAFT.read_text(encoding="utf-8")) if DRAFT.exists() else {"items": []}


def _load_review() -> dict:
    return json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {}


def _save_review(data: dict) -> None:
    with _lock:
        REVIEW.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _thumb_path(rel: str, size: int = 480) -> Path:
    """缩略图缓存（assets/.thumbs/{rel 同名 .jpg}; 缺 → 生成）。"""
    src = ASSETS_BG / rel
    if not src.exists():
        return src
    tgt = ASSETS_BG / ".thumbs" / rel
    if tgt.exists():
        return tgt
    tgt.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(src) as im:
            im.thumbnail((size, size))
            im.convert("RGB").save(tgt, "JPEG", quality=78)
    except Exception:
        return src
    return tgt


# ---------------------------------------------------------------------------
# 数据装配: draft 族 + 审阅进度 → 工作项
# ---------------------------------------------------------------------------

def _scene_files(scene_ids: list[str]) -> list[str]:
    """族内全部文件（相对 assets/background 路径, 去重保序）。"""
    out: list[str] = []
    for sid in scene_ids:
        for e in _cat._backgrounds.get(sid, []):
            rel = str(e.path.relative_to(ASSETS_BG)).replace("\\", "/")
            if rel not in out:
                out.append(rel)
    return out


def _work_items() -> list[dict]:
    draft = _load_draft()
    review = _load_review()
    items = []
    for it in draft.get("items", []):
        key = it["key"]
        done = review.get(key)
        items.append({
            "key": key,
            "dir": it["dir"],
            "root": it["root"],
            "scenes": it["scenes"],
            "files": _scene_files(it["scenes"]),
            "suspect": it.get("suspect", False),
            "done": done,
        })
    return items


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    return _PAGE


@app.get("/api/items")
def api_items():
    items = _work_items()
    pending = [i for i in items if not i["done"]]
    done_n = len(items) - len(pending)
    return {"total": len(items), "done": done_n, "pending": pending[:1],
            "items": items}


@app.get("/api/thumb")
def api_thumb(f: str):
    p = _thumb_path(f)
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
        "active": bool(body.get("active", True)),
        "note": str(body.get("note") or "").strip(),
    }
    _save_review(data)
    return {"ok": True, "saved": len(data)}


@app.get("/api/export")
def api_export():
    """review + draft → _place_entities.json（scene_id 键, 含 files 自动归位）。"""
    review = _load_review()
    draft = _load_draft()
    entities: dict[str, dict] = {}
    for it in draft.get("items", []):
        rv = review.get(it["key"])
        if not rv or not rv.get("active", True):
            continue                                   # 未审/剔除 → 不进
        sid = it["root"].replace(" ", "_") or it["key"]
        files = _scene_files(it["scenes"])
        entities[sid] = {
            "name": rv.get("name") or it["root"],
            "region": rv.get("region", ""),
            "files": files,
        }
    with _lock:
        EXPORT.write_text(json.dumps(entities, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return {"ok": True, "path": str(EXPORT), "count": len(entities)}


# ---------------------------------------------------------------------------
# 页面
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
             background: #12151b; overflow: hidden; }
  #gallery img { max-width: 96%; max-height: 96%; object-fit: contain;
                 box-shadow: 0 8px 30px rgba(0,0,0,.5); border-radius: 4px; }
  #side { flex: 1; padding: 16px 20px; overflow-y: auto; }
  .kv { margin: 10px 0; }
  .kv label { display: block; font-size: 12px; color: #8a93ad; margin-bottom: 4px; }
  input[type=text], select { width: 100%; padding: 8px; border-radius: 6px;
        border: 1px solid #3a4356; background: #242a35; color: #dfe4ee; font-size: 15px; }
  .suggest { margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; }
  .suggest button { border: 1px solid #4a5670; background: #2d3545; color: #cfe0ff;
        padding: 5px 10px; border-radius: 6px; cursor: pointer; }
  .suggest button:hover { background: #3a465e; }
  .bar { display: flex; gap: 10px; margin-top: 18px; }
  .bar button { flex: 1; padding: 10px; font-size: 15px; border-radius: 8px;
        border: none; cursor: pointer; }
  #saveNext { background: #3d7eff; color: #fff; }
  #skip { background: #3a4356; color: #cfd6e4; }
  #imgNav { color: #8a93ad; font-size: 12px; }
  .filechip { display: inline-block; font-size: 11px; background: #2d3545;
        padding: 2px 8px; border-radius: 10px; margin: 2px; cursor: pointer;
        border: 1px solid #3a4356; }
  .filechip.on { border-color: #ffd166; background: #4a3f22; }
  #progress { font-size: 13px; color: #9aa4b8; }
  #badge { margin-left: auto; }
  #badge span { background:#2d3545; padding:3px 10px; border-radius: 12px; font-size:12px; }
  .warn { color: #ff9d8a; }
</style></head><body>
<header>
  <b>place_studio</b>
  <span id="cur"></span>
  <span id="progress"></span>
  <span id="badge"><span id="badgeText"></span></span>
</header>
<div id="stage">
  <div id="gallery"><img id="mainImg" alt=""></div>
  <div id="side">
    <div class="kv"><label>组键（目录 | 词根）</label><div id="key" style="font-size:13px;color:#9aa4b8"></div></div>
    <div class="kv"><label>成员 scenes / 文件</label>
      <div id="files"></div><div id="imgNav"></div></div>
    <div class="kv"><label>中文语义名（LLM 看到的——"杂草屋"而非路径）</label>
      <input id="name" type="text" placeholder="输入中文名">
      <div class="suggest" id="suggestRow"></div>
    </div>
    <div class="kv"><label>region（剧情地理, 可选——子集注入用）</label>
      <input id="region" type="text" list="regions" placeholder="如 gehenna / schale / oldtown…">
      <datalist id="regions"></datalist>
    </div>
    <div class="kv"><label><input id="active" type="checkbox" checked> 活跃（进入语义键表/注入候选）</label></div>
    <div class="kv"><label>备注</label><input id="note" type="text"></div>
    <div class="bar">
      <button id="saveNext">保存并下一组 (Enter)</button>
      <button id="skip">跳过 (S)</button>
    </div>
    <div style="margin-top:14px;font-size:12px;color:#6c7590">
      ←/→ 或 [ ] 翻看组内图片 · G 生成建议名 · E 导出实体表</div>
  </div>
</div>
<script>
const $ = id => document.getElementById(id);
let items = [], idx = 0, imgIdx = 0;

async function boot() {
  const r = await (await fetch("/api/items")).json();
  items = r.items;
  idx = 0;
  // 跳到第一个未审
  const first = items.findIndex(i => !i.done);
  if (first >= 0) idx = first;
  $("badgeText").textContent = `已审 ${r.done}/${r.total}`;
  render();
}
function cur() { return items[idx]; }
function render() {
  const it = cur();
  $("cur").textContent = `${idx + 1} / ${items.length}`;
  $("progress").textContent = it.done ? "（已审 — 可改后覆盖）" : "";
  $("key").textContent = it.key;
  $("files").innerHTML = "";
  it.files.forEach((f, i) => {
    const c = document.createElement("span");
    c.className = "filechip" + (i === imgIdx ? " on" : "");
    c.textContent = f.split("/").pop();
    c.onclick = () => { imgIdx = i; renderImg(); render(); };
    $("files").appendChild(c);
  });
  $("imgNav").textContent = it.done ? "" : `${it.files.length} 张（点击文件名查看）`;
  $("name").value = (it.done && it.done.name) || "";
  $("region").value = (it.done && it.done.region) || "";
  $("active").checked = it.done ? it.done.active : true;
  $("note").value = (it.done && it.done.note) || "";
  renderImg();
  renderSuggest();
  $("name").focus();
}
function renderImg() {
  const it = cur();
  imgIdx = Math.min(imgIdx, Math.max(0, it.files.length - 1));
  const f = it.files[imgIdx];
  $("mainImg").src = f ? `/api/thumb?f=${encodeURIComponent(f)}` : "";
  // 高亮当前文件 chip
  [...$("files").children].forEach((c, i) => c.classList.toggle("on", i === imgIdx));
}
async function renderSuggest() {
  const it = cur();
  $("suggestRow").innerHTML = "";
  if (it.done && it.done.name) return;
  const btn = document.createElement("button");
  btn.textContent = "⚡ 生成中文名建议";
  btn.onclick = async () => {
    btn.disabled = true; btn.textContent = "生成中…";
    try {
      const r = await (await fetch("/api/suggest", { method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({key: it.key, root: it.root, dir: it.dir}) })).json();
      (r.names || []).forEach((n, i) => {
        const b = document.createElement("button");
        b.textContent = `${i + 1}. ${n}`;
        b.onclick = () => { $("name").value = n; };
        $("suggestRow").appendChild(b);
      });
      if (!r.names || !r.names.length) btn.textContent = "无建议（服务失败?）";
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
      region: $("region").value, active: $("active").checked, note: $("note").value }) });
  it.done = { name: $("name").value, region: $("region").value,
              active: $("active").checked, note: $("note").value };
  if (idx < items.length - 1) idx++;
  imgIdx = 0; render();
}
function skip() { if (idx < items.length - 1) idx++; imgIdx = 0; render(); }
document.addEventListener("keydown", e => {
  if (e.key === "Enter" && e.target.tagName !== "BUTTON") { e.preventDefault(); saveNext(); }
  else if (e.key.toLowerCase() === "s" && e.target.tagName !== "INPUT") skip();
  else if (e.key === "ArrowRight" || e.key === "]") imgIdx++; 
  else if (e.key === "ArrowLeft" || e.key === "[") imgIdx--;
  else if (e.key.toLowerCase() === "g") document.querySelector("#suggestRow button")?.click();
  else if (e.key.toLowerCase() === "e") exportEntities();
  renderImg();
});
$("saveNext").onclick = saveNext;
$("skip").onclick = skip;
async function exportEntities() {
  const r = await (await fetch("/api/export")).json();
  alert(`实体表已导出: ${r.count} 条 → ${r.path}`);
}
boot();
</script></body></html>"""

# ---------------------------------------------------------------------------
# LLM 建议名（可选; 无 key/失败 → names: []）
# ---------------------------------------------------------------------------

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
            "给出 3 个候选（json 数组）: 如 [\"废墟走廊\", \"废弃建筑走廊\"]\n"
            "规则: 学园名用官方译名（gehenna=格黑娜, trinity=圣三一, wildhunt=狂猎美术, "
            "abydos=阿拜多斯, schale=夏莱, hyakkiyako=百鬼夜行, millennium=千年）;\n"
            "只输出 JSON 数组。"
        )
        resp = client.chat(messages=[{"role": "user", "content": prompt}],
                           temperature=0.3, max_tokens=200,
                           response_format="json_object")
        import json as _json
        if isinstance(resp, dict):
            arr = resp.get("names") or resp.get("candidates") or []
        else:
            data = _json.loads(str(resp))
            arr = data.get("names") or data.get("candidates") or []
        names = [str(x).strip() for x in arr if str(x).strip()][:3]
        return {"names": names}
    except Exception as e:                              # noqa: BLE001
        return {"names": [], "error": str(e)}


def main() -> None:
    ap = argparse.ArgumentParser(description="背景实体归纳工作台")
    ap.add_argument("--port", type=int, default=8811)
    args = ap.parse_args()
    if not DRAFT.exists():
        print("缺 draft——先跑: python tools/place_organizer.py")
        raise SystemExit(1)
    print(f"place_studio: http://127.0.0.1:{args.port}  "
          f"(draft {len(_load_draft().get('items', []))} 族; 进度 {REVIEW.name})")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
