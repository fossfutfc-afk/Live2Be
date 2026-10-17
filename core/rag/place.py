"""place.py — 地点检索（RAG 跨语言）: 自由话语/意图 → **地点表键**。

## 它在地点系统里的位置（三层里的"语义层"）

    层1  `PlaceTable.resolve_exact`       纯字符串别名命中, **0 调用**, 歧义不猜
    层2  `place_annotate.resolve_place`   廉价 LLM 读整表（含 note）就近推测
    本模块                                 跨语言 embedding 检索 —— 补前两层
                                          都够不着的**自由说法**（"她们在教学楼
                                          天台上看星星" / "屋上で星を見ている"）

## PL4（2026-09-19）——语料换基座

旧版读**手维护的第二份词表** `config/settings/world/places.yml`（31 条资产 scene slug
+ 中英日别名）, 与标注层的表**互不相识**（`class_room` vs `classroom`）。
现在语料 = `config/settings/world/place_entities.json` 本身
（**168 条语义键 × 428 个别名**, 作者在 tempo 工作台维护）——与层1/层2 **同一张表**,
"别再手维护第二份"就此收口。

⚠️ **返回的 `place` 是表键, 不是资产 scene_id**（`classroom` ↔ `class_room`）。
查图请走 `PlaceTable.scene_id(key)` 或 `PlaceRetriever.asset_scene(key)`
（这一层翻译是最容易搞错的地方, 见 `docs/AI_BRIEF_PLACE.md` §2）。

⚠️ **`note` 刻意不进语料**: 它是写给人/标注 LLM 的用途说明（"engine 会处理的"这类
元话语）, 嵌进向量只会引入噪声; 别名（`keywords`）才是"这个地方能被怎么称呼"。

⚠️ **未接线**: 生产主链至今没有消费方（`get_channel(...).gather(...)` 是 C 链路,
与本模块不是一回事）。本模块是"玩家自由指定地点 / 地点既视感召回"的预留——
用户 2026-09-19: *"总之我们需要一个地点语义检索来体现既视感以增强我们的召回策略"*。
接线时机见 `TODO.md` PL4（与召回策略同批）。

宁缺勿错: 服务未起 / 表缺失 / 低分 → `[]`（上层保持上一场景, 绝不硬凑）。

用法:
    retriever = PlaceRetriever()                    # 自动发现 embedding 模型
    retriever.resolve("她们在学校天台上看星星")        # → [("school_rooftop", 0.7x), ...]
    retriever.asset_scene("school_rooftop")         # → 资产 scene_id（查图用）
"""
from __future__ import annotations

from contract.errors import Live2BeError
from core.media.place_table import PlaceTable, load_table
from core.rag.embedder import LocalEmbedder

#: 默认最低置信（低于 → 不返回, 上层保持上一场景）; 调参见 experiments/rag_test.py
DEFAULT_THRESHOLD = 0.40


class PlaceError(Live2BeError):
    """地点检索域错误（语料缺失/损坏等; 查询本身宁缺勿错不抛）。"""


# EXT: place-semantic-pl4 — 地点语义检索（语料已备, 产品侧未接线: 层1 别名 0 调用）; 勿删（docs/EXTENSION_POINTS.md）
class PlaceRetriever:
    """地点表的跨语言语义检索器（懒构建向量, 层1 精确优先; 单位 = 表键）。"""

    def __init__(
        self,
        embedder: LocalEmbedder | None = None,
        *,
        table: PlaceTable | None = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        """
        Args:
            embedder: None → `LocalEmbedder()`（走配置链 + 自动发现）
            table: 语料表; None → `load_table()`（`config/settings/world/
                place_entities.json`, 按 mtime 缓存）。空表 = 无语料（`resolve` → `[]`）
            threshold: 语义命中最低余弦; 见 `DEFAULT_THRESHOLD`
        """
        self._embedder = embedder or LocalEmbedder()
        self.threshold = threshold
        self._table = table if table is not None else load_table()
        self._aliases: dict[str, tuple[str, ...]] = {}      # 表键 → 别名（`place`+`keywords`）
        self._vectors: dict[str, list[list[float]]] | None = None   # 懒构建缓存
        self._load()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def resolve(self, text: str, k: int = 3) -> list[tuple[str, float]]:
        """文本 → [(表键, score)] 降序, k 截断, 阈值以上。空/低分 → []。

        ① **精确兜底**（= 层1, 零依赖 0 调用）: 别名**唯一**命中 → 直接 1.0。
           **歧义不猜**（`天台` 指着 3 个键）——照实下沉语义层排序, 宁可 [] 也不随手挑
           一个（层1 同一条纪律）。想拿歧义全集的调用方直接用 `PlaceTable.resolve_exact`。
        ② **语义层**: 跨语言 embedding（每键取"别名里最高的那个余弦"）。
        """
        query = (text or "").strip()
        if not query:
            return []
        hits = self._table.resolve_exact(query)
        if len(hits) == 1:
            return [(hits[0], 1.0)]
        vectors = self._ensure_vectors()
        if not vectors:
            return []
        try:
            qv = self._embedder.embed_one(query)
        except Exception:                            # noqa: BLE001 — 服务故障降级
            return []
        if not qv:
            return []
        scored: list[tuple[str, float]] = []
        for place, alias_vecs in vectors.items():
            best = max((LocalEmbedder.cosine(qv, v) for v in alias_vecs), default=0.0)
            if best >= self.threshold:
                scored.append((place, best))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

    def resolve_one(self, text: str) -> str | None:
        """便捷: 最高分表键（低于阈值 → None = 上层保持上一场景）。"""
        hits = self.resolve(text, k=1)
        return hits[0][0] if hits else None

    def scenes(self) -> list[str]:
        """语料全部**表键**（排查用; 不是资产 scene_id）。"""
        return sorted(self._aliases)

    def asset_scene(self, place: str) -> str | None:
        """表键 → 资产 scene_id（下游查图/前端 URL 用; 不一致时按文件名翻译）。"""
        return self._table.scene_id(place)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """表 → 别名表（`PlaceEntry.aliases()` = `place` + `keywords`）。

        空表/无别名 → 空语料（宁缺勿错, 不阻断; `resolve` 一律 `[]`）。
        """
        for e in self._table.all():
            aliases = e.aliases()
            if aliases:
                self._aliases[e.place] = aliases

    def _ensure_vectors(self) -> dict[str, list[list[float]]] | None:
        """懒构建: **保留每条别名的向量**, 打分时取键内最大值。

        2026-09-19（PL4）改法: 旧实现每 scene 只留"平方范数最大"的那**一条**别名
        向量当代表——在 L2 归一化的模型下范数几乎相同 ⇒ 实际等价于"**只留第一条
        别名**", 一个键的其它别名（`学校天台`/`天台`/`school_rooftop` 里的后两条）
        全白扔。428 条别名 ×1 个向量完全放得下, 没有理由省这个。

        Returns: `{表键: [别名向量…]}`; **None = 没有语义层**（无语料 / 后端不可用 /
        形状不符 —— 三种都记进缓存, 不反复重试）。
        """
        if self._vectors is not None:
            return self._vectors or None
        if not self._aliases:
            return None
        if not self._embedder.health():
            return None
        flat: list[str] = []
        for aliases in self._aliases.values():
            flat.extend(aliases)
        try:
            vecs = self._embedder.embed(flat)
        except Exception:                            # noqa: BLE001 — 服务故障: 无语义层
            self._vectors = {}
            return None
        if len(vecs) != len(flat):                   # 形状不符 → 别错位配对
            self._vectors = {}
            return None
        out: dict[str, list[list[float]]] = {}
        idx = 0
        for place, aliases in self._aliases.items():
            chunk = vecs[idx: idx + len(aliases)]
            idx += len(aliases)
            if chunk:
                out[place] = chunk
        self._vectors = out
        return out
