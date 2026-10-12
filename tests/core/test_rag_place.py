"""`PlaceRetriever` 单测（PL4, 2026-09-19）——语料换基座后的行为。

PL4 做的事: `core/rag/place.py` 的语料从**手维护的第二份词表** `places.yml`
（31 条资产 scene slug + 中英日别名）换成**地点表本身**
（`place_entities.json`: 168 键 × 428 别名, 与标注层层1/层2 同一张表）。

本文件钉四件事（都用**桩 embedder**, 不碰本机服务）:

  ① **语料 = 表, 单位 = 表键**: 旧 `places.yml` 的资产 slug（`class_room`/`ramen_ya`/
     `onsen`）**不在**语料里; 表键（`classroom`/`school_rooftop`）在。
  ② **层1 独占不猜**: 别名唯一命中 → 1.0 **且 0 次 embedding**; 歧义（`天台` 指 3 个键）
     → **下沉语义层**, 服务不可用就返回 `[]`, 绝不随手挑一个。
  ③ **每个别名都进语料**: 旧实现每键只留"范数最大"的那一条别名向量（L2 归一化下
     ≈"只留第一条"）; 现在保留全部、打分取键内最大值 —— 有哨兵用例。
  ④ **表键 ≠ 资产 scene_id**: 翻译只走 `asset_scene()`（`classroom` → `class_room`）。
"""
import sys
from pathlib import Path


from core import paths                                              # noqa: E402
from core.media.place_table import PlaceEntry, PlaceTable, load_table  # noqa: E402
from core.rag.place import PlaceRetriever                            # noqa: E402



class StubEmbedder:
    """按字典给向量（表外文本 → 零向量）; 记下被问了什么。

    `rule` 给"按内容判"的场景用（如"文本里有没有『天台』"）——二分向量便于断言候选集。
    """

    def __init__(self, vectors: dict[str, list[float]] | None = None, *,
                 healthy: bool = True, rule=None) -> None:
        self.vectors = dict(vectors or {})
        self.healthy = healthy
        self.rule = rule
        self.batch_calls: list[list[str]] = []
        self.one_calls: list[str] = []

    def _vec(self, text: str) -> list[float]:
        if self.rule is not None:
            return self.rule(text)
        return self.vectors.get(text, [0.0, 0.0])

    def health(self) -> bool:
        return self.healthy

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [self._vec(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        self.one_calls.append(text)
        return self._vec(text)


def _roof_table() -> PlaceTable:
    """一条键 + 三条别名（`aliases()` = place + keywords）的迷你表。"""
    return PlaceTable(entries={
        "roof": PlaceEntry(place="roof", keywords=("学校天台", "天台")),
    }, ok=True)


# ---------------------------------------------------------------------------
# ① 语料换基座
# ---------------------------------------------------------------------------

def test_corpus_is_the_table_not_the_old_places_yml():
    t = load_table()
    assert t.ok, f"真表读不出来: {t.error}"
    r = PlaceRetriever(StubEmbedder(healthy=False), table=t)
    keys = r.scenes()
    assert len(keys) == len(t) >= 150, (len(keys), len(t))
    assert "school_rooftop" in keys and "classroom" in keys
    for old_slug in ("class_room", "ramen_ya", "onsen"):
        assert old_slug not in keys, f"旧 places.yml 的资产 slug 还在语料里: {old_slug}"
    print(f"    语料: {len(keys)} 个表键（旧 places.yml 的资产 slug 已不在其中）")


def test_places_yml_artifact_is_gone():
    """★ 旧语料文件与它的路径宏一起删掉——第二份词表不许回来。"""
    assert not hasattr(paths, "PLACES_PATH"), "paths.PLACES_PATH 还在（语料已换基座）"
    assert not (paths.WORLD_DIR / "places.yml").exists(), "places.yml 还在磁盘上"
    print("    places.yml: 文件与 paths.PLACES_PATH 都已删")


def test_every_alias_goes_into_the_corpus():
    """★ 哨兵: 428 个别名**全部**进 embedding（不是每键只留一条）。"""
    t = load_table()
    stub = StubEmbedder()
    r = PlaceRetriever(stub, table=t)
    r.resolve("夜里在屋顶吹风")                       # 层1 不命中 → 触发懒构建
    assert len(stub.batch_calls) == 1, "向量构建应该只有一次批量调用"
    flat = stub.batch_calls[0]
    assert len(flat) == sum(len(e.aliases()) for e in t.all()) >= 400, len(flat)
    assert "天台" in flat and "学校天台" in flat       # 同一键的多条别名都在
    print(f"    语料向量: {len(flat)} 条别名一次批量（含同键的多条别名）")


# ---------------------------------------------------------------------------
# ② 层1 独占不猜 / 歧义下沉
# ---------------------------------------------------------------------------

def test_exact_unique_hit_is_zero_call():
    t = load_table()
    stub = StubEmbedder()
    r = PlaceRetriever(stub, table=t)
    assert r.resolve("学校天台") == [("school_rooftop", 1.0)]
    assert stub.batch_calls == [] and stub.one_calls == [], "唯一命中不该碰 embedding"
    print("    层1: 唯一别名命中 → 1.0（0 次 embedding）")


def test_ambiguous_exact_falls_to_semantic():
    """歧义（`天台` → 3 键）**不猜**: 下沉语义层排序, 候选集就是那 3 个键。"""
    t = load_table()
    stub = StubEmbedder(rule=lambda x: [1.0, 0.0] if "天台" in x else [0.0, 1.0])
    r = PlaceRetriever(stub, table=t)
    hits = r.resolve("放学后的天台", k=3)
    assert stub.one_calls == ["放学后的天台"], "歧义没下沉到语义层（层1 猜了？）"
    keys = sorted(k for k, _ in hits)
    assert keys == ["building_roof_top", "rooftop", "school_rooftop"], keys
    assert all(0.0 < s <= 1.0 for _, s in hits)
    print(f"    层1 歧义 → 语义层: {keys}")


def test_ambiguous_exact_without_service_returns_empty():
    """★ 宁缺勿错: 歧义 + 语义层不可用 → `[]`（**绝不随手挑一个键**）。"""
    t = load_table()
    r = PlaceRetriever(StubEmbedder(healthy=False), table=t)
    assert r.resolve("放学后的天台") == []
    assert r.resolve_one("放学后的天台") is None
    print("    层1 歧义 + 无 embedding → []（不猜）")


def test_best_alias_wins_not_the_first_one():
    """★ 哨兵: 打分取"键内**任意**别名的最大余弦", 不是第一条别名。

    旧实现每键只留"平方范数最大"的一条向量（两条单位向量时 = 第一条 `roof`）
    ⇒ 本例会因 0 分落到阈值下返回 `[]`。改成保留全部别名后 → 命中 `roof`。
    """
    stub = StubEmbedder({"夜里在屋顶吹风": [1.0, 0.0],     # query
                         "roof": [0.0, 1.0],              # 第一条别名（不相关）
                         "学校天台": [1.0, 0.0],           # 第二条别名（该赢）
                         "天台": [0.0, 1.0]})
    r = PlaceRetriever(stub, table=_roof_table())
    assert r.resolve_one("夜里在屋顶吹风") == "roof"
    print("    打分: 取键内最大余弦（不是第一条别名）")


def test_empty_table_degrades():
    """空表（缺/坏）→ 无语料: 不抛、不调服务、一律 []。"""
    stub = StubEmbedder()
    r = PlaceRetriever(stub, table=PlaceTable())
    assert r.scenes() == []
    assert r.resolve("学校天台") == []
    assert r.resolve_one("学校天台") is None
    assert stub.batch_calls == [] and stub.one_calls == []
    print("    空表: 无异常、无调用、[]（宁缺勿错）")


# ---------------------------------------------------------------------------
# ④ 表键 ≠ 资产 scene_id
# ---------------------------------------------------------------------------

def test_asset_scene_translates_key_to_scene_id():
    t = load_table()
    r = PlaceRetriever(StubEmbedder(healthy=False), table=t)
    assert r.asset_scene("classroom") == "class_room", "表键 → 资产 scene_id 的翻译断了"
    assert r.asset_scene("school_rooftop") == "school_rooftop"    # slug 型键两者相同
    assert r.asset_scene("") is None
    print("    asset_scene: classroom → class_room（表键不是 scene_id）")


if __name__ == "__main__":
    test_corpus_is_the_table_not_the_old_places_yml()
    test_places_yml_artifact_is_gone()
    test_every_alias_goes_into_the_corpus()
    test_exact_unique_hit_is_zero_call()
    test_ambiguous_exact_falls_to_semantic()
    test_ambiguous_exact_without_service_returns_empty()
    test_best_alias_wins_not_the_first_one()
    test_empty_table_degrades()
    test_asset_scene_translates_key_to_scene_id()
