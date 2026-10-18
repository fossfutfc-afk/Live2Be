"""素材包：切（`packaging/make_packs.py`）+ 读/下/校验/落地（`infra/packs.py`）。

钉五件事：

  ① 端到端：切出来的清单能被运行时读回，走 `file://` 真下载真解压，装完 `local_state`
     变 `installed`，字节与原文件一致
  ② sha256 不符 → 拒绝落地：目标目录一个文件都不写，`.part` 也不留
  ③ zip 里的 `../` 越界 → 拒绝（清单与解压两侧都挡）
  ④ 装没装只看磁盘：删一个文件 → `partial`（没有状态文件可以骗人）
  ⑤ 取消 → 停在当前包，后面的包不动

`packaging/make_packs.py` 用 `importlib` 按路径加载：仓根的 `packaging/` 与 PyPI 的同名
包会撞名，`import packaging` 拿到的是后者。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

from infra import packs

REPO = Path(__file__).resolve().parents[2]
PLACE_TABLE = {
    "classroom": {
        "place": "classroom",
        "sdir": "SDIR_Schools",
        "dir": "DIR_Class",
        "files": {"day": ["SDIR_Schools/DIR_Class/BG_ClassRoom.jpg"], "night": []},
    }
}


def _load_make_packs():
    spec = importlib.util.spec_from_file_location(
        "make_packs_under_test", REPO / "packaging" / "make_packs.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # 必须先进 sys.modules：数据类的字符串注解要靠 `cls.__module__` 反查命名空间，
    # 不在 sys.modules 里会在 exec 期就 AttributeError。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo(tmp_path):
    """一个最小仓库：一个角色 + 一张背景 + 一张轮播图。"""
    root = tmp_path / "repo"
    assets = root / "assets"
    illus = assets / "illustration" / "igusa_haruka"
    (illus / "default" / "diff").mkdir(parents=True)
    (illus / "default" / "emotions.yml").write_text("nomal: 1\n", encoding="utf-8")
    (illus / "default" / "diff" / "a.png").write_bytes(b"PNG-A")
    (illus / "default" / "diff" / "b.png").write_bytes(b"PNG-B")
    (illus / "ref").mkdir()
    (illus / "ref" / "halo.png").write_bytes(b"HALO")
    (assets / "background" / "SDIR_Schools" / "DIR_Class").mkdir(parents=True)
    (assets / "background" / "SDIR_Schools" / "DIR_Class" / "BG_ClassRoom.jpg").write_bytes(b"JPG")
    (assets / "menu" / "vol2.0").mkdir(parents=True)
    (assets / "menu" / "vol2.0" / "x.jpg").write_bytes(b"MENU")

    config = root / "config"
    (config / "characters" / "igusa_haruka").mkdir(parents=True)
    (config / "characters" / "igusa_haruka" / "profile.yml").write_text(
        "REQ~most_called_name: 伊草 遥香\n", encoding="utf-8")
    (config / "settings" / "world").mkdir(parents=True)
    (config / "settings" / "world" / "place_entities.json").write_text(
        json.dumps(PLACE_TABLE, ensure_ascii=False), encoding="utf-8")
    return root


def _build(repo: Path, dst: Path) -> int:
    return _load_make_packs().main([
        "--src", str(repo / "assets"),
        "--config", str(repo / "config"),
        "--dst", str(dst),
    ])


def test_roundtrip_build_read_install(repo, tmp_path):
    dst = tmp_path / "packs"
    assert _build(repo, dst) == 0

    manifest = packs.read_manifest((dst / "manifest.json").as_uri())
    ids = {p.id for p in manifest.packs}
    assert ids == {"char.igusa_haruka", "char.igusa_haruka.ref", "bg.place_table", "menu.vol2"}

    target = tmp_path / "installed"
    target.mkdir()
    spec = manifest.get("char.igusa_haruka")
    assert spec is not None
    assert packs.local_state(spec, target) == ("missing", 0, 3)

    work = tmp_path / "work"
    outcomes = packs.install(manifest, [p.id for p in manifest.packs], target, work)
    assert [(o.pack_id, o.ok) for o in outcomes] == [(i, True) for i in
                                                     [p.id for p in manifest.packs]]
    assert packs.local_state(spec, target) == ("installed", 3, 3)
    assert (target / "illustration/igusa_haruka/default/diff/a.png").read_bytes() == b"PNG-A"
    assert (target / "background/SDIR_Schools/DIR_Class/BG_ClassRoom.jpg").read_bytes() == b"JPG"
    assert not list(work.glob("*.zip")), "下完的 zip 不该留在工作目录"


def test_build_is_reproducible(repo, tmp_path):
    """同一份输入切两次 → 同一个 sha256（清单才敢被缓存/比对）。"""
    first, second = tmp_path / "a", tmp_path / "b"
    assert _build(repo, first) == 0
    assert _build(repo, second) == 0
    a = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    b = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    assert [(p["id"], p["zip_sha256"]) for p in a["packs"]] == \
           [(p["id"], p["zip_sha256"]) for p in b["packs"]]


def test_bad_sha256_is_rejected_and_leaves_nothing(repo, tmp_path):
    dst = tmp_path / "packs"
    assert _build(repo, dst) == 0
    raw = json.loads((dst / "manifest.json").read_text(encoding="utf-8"))
    for pack in raw["packs"]:
        pack["zip_sha256"] = "0" * 64
    (dst / "manifest.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    manifest = packs.parse_manifest(raw, source=(dst / "manifest.json").as_uri())
    target = tmp_path / "installed"
    target.mkdir()
    work = tmp_path / "work"
    outcomes = packs.install(manifest, ["char.igusa_haruka"], target, work)

    assert [o.ok for o in outcomes] == [False]
    assert "sha256" in outcomes[0].error
    assert not list(target.rglob("*")), "校验没过就不该落地任何文件"
    assert not list(work.rglob("*")), "失败时 .part 要清掉"


def test_zip_slip_is_rejected(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../escaped.txt", b"nope")
    assets = tmp_path / "assets"
    assets.mkdir()
    with pytest.raises(packs.PackError):
        packs.extract(evil, assets)
    assert not (tmp_path / "escaped.txt").exists()


def test_manifest_rejects_dotdot_paths():
    raw = {
        "schema": 1,
        "generated": "",
        "packs": [{
            "id": "x", "zip": "x.zip", "zip_bytes": 1, "zip_sha256": "", "bytes": 1,
            "file_count": 1, "files": [["../etc/passwd", 1]],
        }],
    }
    with pytest.raises(packs.PackError):
        packs.parse_manifest(raw)


def test_manifest_rejects_unknown_schema():
    with pytest.raises(packs.PackError):
        packs.parse_manifest({"schema": 99, "packs": []})


def test_state_follows_the_disk(repo, tmp_path):
    dst = tmp_path / "packs"
    assert _build(repo, dst) == 0
    manifest = packs.read_manifest((dst / "manifest.json").as_uri())
    target = tmp_path / "installed"
    target.mkdir()
    packs.install(manifest, ["char.igusa_haruka"], target, tmp_path / "work")

    spec = manifest.get("char.igusa_haruka")
    assert spec is not None
    assert packs.local_state(spec, target)[0] == "installed"
    (target / "illustration/igusa_haruka/default/diff/a.png").unlink()
    assert packs.local_state(spec, target) == ("partial", 2, 3)


def test_cancel_stops_before_anything_lands(repo, tmp_path):
    import threading

    dst = tmp_path / "packs"
    assert _build(repo, dst) == 0
    manifest = packs.read_manifest((dst / "manifest.json").as_uri())
    target = tmp_path / "installed"
    target.mkdir()
    cancel = threading.Event()
    cancel.set()
    outcomes = packs.install(manifest, ["char.igusa_haruka", "bg.place_table"], target,
                             tmp_path / "work", cancel=cancel)

    assert [o.error for o in outcomes] == ["已取消"]
    assert not list(target.rglob("*"))
