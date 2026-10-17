"""样张清单守门 —— `packaging/collect_samples.py` 只算不改盘。

为什么值得钉: 打包时"包里有没有图"由这份清单决定，而它一旦变成随机 / 依赖机器上的文件
顺序，同一个提交在两台机器上打出来的包就不一样 —— 那类差异事后解释不清。

⚠️ 为什么按**文件路径**加载而不是 `import packaging.collect_samples`: 仓库根的
`packaging/` 和 PyPI 上的 `packaging`（setuptools / pip 在用）同名，而**普通包优先于
命名空间包** ⇒ `import packaging` 拿到的是 PyPI 那个。这里显式从文件加载，不依赖 sys.path。

跑法: python -m pytest tests/core/test_packaging_samples.py
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_MOD_PATH = ROOT / "packaging" / "collect_samples.py"

_spec = importlib.util.spec_from_file_location("live2be_collect_samples", _MOD_PATH)
assert _spec and _spec.loader, f"加载不到 {_MOD_PATH}"
samples = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(samples)

BACKGROUND_DIRS = samples.BACKGROUND_DIRS
BACKGROUND_SAMPLE = samples.BACKGROUND_SAMPLE
ILLUSTRATIONS = samples.ILLUSTRATIONS


def _fake_assets(tmp_path):
    """造一棵最小 assets 树（menu / 一个角色 / 两个背景分类 + 一个抽样分类）。"""
    src = tmp_path / "assets"

    def touch(rel: str, size: int = 10) -> None:
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * size)

    touch("menu/default/a.jpg")
    touch("menu/logo/logo.png")
    for char in ILLUSTRATIONS:
        touch(f"illustration/{char}/default/face_1.png")
        touch(f"illustration/{char}/ref/ref_1.png")
    for d in BACKGROUND_DIRS:
        touch(f"background/{d}/bg_1.jpg")
        touch(f"background/{d}/bg_2.jpg")
    name, count = next(iter(BACKGROUND_SAMPLE.items()))
    for i in range(count + 15):                       # 故意多给: 只该取前 count 张
        touch(f"background/{name}/bg_{i:03d}.jpg")
    return src


def test_plan_covers_menu_and_the_chosen_character(tmp_path):
    src = _fake_assets(tmp_path)
    rels = {rel.as_posix() for _, rel in samples.plan(src)}
    assert "menu/default/a.jpg" in rels and "menu/logo/logo.png" in rels
    char = ILLUSTRATIONS[0]
    assert f"illustration/{char}/default/face_1.png" in rels
    assert f"illustration/{char}/ref/ref_1.png" in rels, "ref 要带: 纪念生图用参考图"


def test_background_sampling_is_capped_and_stable(tmp_path):
    src = _fake_assets(tmp_path)
    name, count = next(iter(BACKGROUND_SAMPLE.items()))
    sample = sorted(rel.as_posix() for _, rel in samples.plan(src)
                    if rel.as_posix().startswith(f"background/{name}/"))
    assert len(sample) == count, f"抽样该恰好 {count} 张, 实得 {len(sample)}"
    assert sample == sorted(sample), "清单必须有序（可复现）"
    assert sample[0].endswith("bg_000.jpg"), "按文件名取前 N（不许随机）"


def test_whole_background_dirs_are_not_sampled(tmp_path):
    src = _fake_assets(tmp_path)
    for d in BACKGROUND_DIRS:
        got = [rel for _, rel in samples.plan(src)
               if rel.as_posix().startswith(f"background/{d}/")]
        assert len(got) == 2, f"{d} 是整目录带, 实得 {len(got)}"


def test_run_copies_exactly_the_plan(tmp_path):
    """真拷一遍（小文件）: 目标树 = 清单。"""
    src = _fake_assets(tmp_path)
    items = samples.plan(src)
    dst = tmp_path / "out"
    n, total = samples.run(items, dst)
    assert n == len(items) and total > 0
    copied = {p.relative_to(dst).as_posix() for p in dst.rglob("*") if p.is_file()}
    assert copied == {rel.as_posix() for _, rel in items}
