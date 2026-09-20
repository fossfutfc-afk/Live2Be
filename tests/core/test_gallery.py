# -*- coding: utf-8 -*-
"""GalleryStore 单测 — 图 + 元数据成对落盘 / 成对列表 / 单条读取。

运行: python -m pytest tests/core/test_gallery.py
"""
from pathlib import Path

import pytest

from core.media.gallery import GalleryStore


def _fake_png(tmp_path: Path, name: str = "src.png") -> Path:
    """造一个假 png（gallery 只复制不校验内容）。"""
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\nfake-bytes")
    return p


def test_write_creates_pair(tmp_path):
    st = GalleryStore(tmp_path)
    sid = st.write("igusa_haruka", "天台上的遥香", "sess_1", _fake_png(tmp_path))
    assert sid.startswith("2026"), f"scene_id 应带时间戳: {sid}"
    assert st.png_path("igusa_haruka", sid).is_file()
    assert st.meta_path("igusa_haruka", sid).is_file()
    print(f"    write: {sid} → png + json 成对")


def test_write_attribution_fields(tmp_path):
    """可归因字段（2026-09-20 节点 C）: prompt_source / refs / model / elapsed_ms。

    **art 配对命中率**（`prompt_source == "art"` 的比例）是"画面指令质量"目前唯一
    能自动算的代理指标——它必须真的落盘。同时钉住向后兼容: 不传这些字段时
    json 形状与老档**逐字段一致**（老 json 也不能被读挂）。
    """
    st = GalleryStore(tmp_path)
    sid = st.write("igusa_haruka", "（她抬起头。）", "sess_1", _fake_png(tmp_path),
                   width=1920, height=1080,
                   prompt_source="art",
                   refs=["sprite_1.png", "style_1.png"],
                   model="gemini-3.1-flash-lite-image",
                   elapsed_ms=26400)
    meta = st.get("igusa_haruka", sid)
    assert meta["prompt_source"] == "art"
    assert meta["refs"] == ["sprite_1.png", "style_1.png"]
    assert meta["model"] == "gemini-3.1-flash-lite-image"
    assert meta["elapsed_ms"] == 26400

    # 缺省（老调用形状）→ 这些键**不出现**（老 json 形状不变）
    sid2 = st.write("igusa_haruka", "（她抬起头。）", "sess_1", _fake_png(tmp_path),
                    width=1920, height=1080)
    meta2 = st.get("igusa_haruka", sid2)
    for k in ("prompt_source", "refs", "model", "elapsed_ms"):
        assert k not in meta2, f"{k} 不该凭空出现: {meta2}"
    print("    write: 可归因字段落盘 + 缺省不写（向后兼容）")


def test_write_meta_fields(tmp_path):
    st = GalleryStore(tmp_path, world_id="world2")
    sid = st.write("igusa_haruka", "天台上的遥香", "sess_1", _fake_png(tmp_path),
                   description="晚风拂过发梢")
    meta = st.get("igusa_haruka", sid)
    assert meta is not None
    assert meta["scene_id"] == sid
    assert meta["character_id"] == "igusa_haruka"
    assert meta["source_world"] == "world2"       # 世界线内资产标识
    assert meta["prompt"] == "天台上的遥香"
    assert meta["source_session"] == "sess_1"
    assert meta["description"] == "晚风拂过发梢"
    assert meta["created_at"]
    assert Path(meta["png"]).is_file()
    # 路径: worlds/{world}/characters/{char}/gallery（2026-09-02 拍板）
    assert st.gallery_dir("igusa_haruka") == (
        tmp_path / "worlds" / "world2" / "characters" / "igusa_haruka" / "gallery")
    # 世界隔离: world1 下查不到 world2 的图
    st1 = GalleryStore(tmp_path, world_id="world1")
    assert st1.list("igusa_haruka") == []
    print("    meta: scene/char/source_world/prompt/source/description/created_at + 世界隔离")


def test_list_only_complete_pairs(tmp_path):
    st = GalleryStore(tmp_path)
    sid_ok = st.write("igusa_haruka", "prompt A", "s1", _fake_png(tmp_path, "a.png"))
    st.write("igusa_haruka", "prompt B", "s2", _fake_png(tmp_path, "b.png"))
    # 造半套: 只有 png 无 json（模拟写入中断）
    orphan = st.png_path("igusa_haruka", "20260101_000000_zzzz")
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"\x89PNG-fake")

    items = st.list("igusa_haruka")
    ids = {i["scene_id"] for i in items}
    assert len(ids) == 2 and sid_ok in ids, f"2 个成对都应入选: {ids}"
    assert "20260101_000000_zzzz" not in ids, f"半套 png 不应进列表: {ids}"
    print(f"    list: 2 成对入选, 1 半套（仅 png）跳过")


def test_get_missing_returns_none(tmp_path):
    st = GalleryStore(tmp_path)
    assert st.get("igusa_haruka", "nope") is None
    print("    get: 不存在 → None")


def test_write_empty_prompt_rejected(tmp_path):
    st = GalleryStore(tmp_path)
    with pytest.raises(ValueError):
        st.write("igusa_haruka", "   ", "s1", _fake_png(tmp_path))
    print("    write: 空 prompt → ValueError")


def test_rewrite_completes_half_pair(tmp_path):
    """中断重试: png 先落、json 缺 → 同 scene_id 重写补全 → 恢复成对。"""
    st = GalleryStore(tmp_path)
    src = _fake_png(tmp_path)
    sid = "20260101_000000_rett"
    # 模拟中断: 只复制 png, 不写 json
    st.png_path("igusa_haruka", sid).parent.mkdir(parents=True, exist_ok=True)
    st.png_path("igusa_haruka", sid).write_bytes(src.read_bytes())
    assert st.list("igusa_haruka") == [], "半套不应进列表"
    # 重试补全（同 scene_id）
    st.write("igusa_haruka", "prompt", "s1", src, scene_id=sid)
    items = st.list("igusa_haruka")
    assert len(items) == 1 and items[0]["scene_id"] == sid
    print("    write: 同 scene_id 重试 → 半套补全为成对")
