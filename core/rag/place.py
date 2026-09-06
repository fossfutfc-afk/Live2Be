# -*- coding: utf-8 -*-
"""place.py — 地点检索（RAG 跨语言）: LLM 话语/意图 → scene_id（调背景用）。

背景管线的检索升级（DESIGN_VISUAL_PROTOCOL.md §5/§6 现状: place 必须**精确**
命中 scene_id 否则静默保持——RAG 让"自由话语"也能映射到正确背景）:
    query = 主 LLM 的 place 意图（词表内 id）或自由话语（"她们在天台看星星"）
    → 精确兜底（id/别名子串, 零依赖）→ embedding 语义匹配（跨语言中英日）→
    top-k 带分 → 阈值以下不返回（宁缺勿错: 上层保持上一场景）。

语料 = config/settings/world/places.yml（scene_id 对齐导演词表 common_scenes,
别名中英日混排）。embedding 派生不落盘（别名改动零漂移——与 wiki recall 同哲学）;
首次 resolve 时懒构建缓存。

用法:
    retriever = PlaceRetriever()                    # 自动发现 embedding 模型
    retriever.resolve("她们在学校天台上看星星")        # → [("school_rooftop", 0.7x), ...]
    retriever.resolve_one("ラーメン屋で待ち合わせ")     # → "ramen_ya" 或 None(低分)
"""
from __future__ import annotations

from pathlib import Path

import yaml

from core.common.errors import Live2BeError
from core.rag.embedder import LocalEmbedder

#: 语料默认路径（config/settings/world/places.yml）
_DEFAULT_PLACES = (
    Path(__file__).resolve().parent.parent.parent
    / "config" / "settings" / "world" / "places.yml"
)

#: 默认最低置信（低于 → 不返回, 上层保持上一场景）; 调参见 experiments/rag_test.py
DEFAULT_THRESHOLD = 0.40

#: scene id 拆词分隔（class_room → "class room"; 驼峰已由目录派生归一为 snake）
_SPLIT = str.maketrans({"_": " "})


class PlaceError(Live2BeError):
    """地点检索域错误（语料缺失/损坏等; 查询本身宁缺勿错不抛）。"""


class PlaceRetriever:
    """scene 词表跨语言检索器（懒构建向量, 精确兜底优先）。"""

    def __init__(
        self,
        embedder: LocalEmbedder | None = None,
        *,
        places_path: str | Path | None = None,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._embedder = embedder or LocalEmbedder()
        self.threshold = threshold
        self._places_path = Path(places_path) if places_path else _DEFAULT_PLACES
        self._aliases: dict[str, list[str]] = {}      # scene_id → 别名
        self._id2alias: dict[str, str] = {}           # 别名 → scene_id（精确兜底）
        self._vectors: dict[str, list[float]] | None = None   # 懒构建缓存
        self._load()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def resolve(self, text: str, k: int = 3) -> list[tuple[str, float]]:
        """文本 → [(scene_id, score)] 降序, k 截断, 阈值以上。空/低分 → []。"""
        query = (text or "").strip()
        if not query:
            return []
        # 1) 精确兜底（零依赖, 词表 id / 别名子串命中直接 1.0）
        exact = self._exact(query)
        if exact is not None:
            return [(exact, 1.0)]
        # 2) embedding 语义匹配（跨语言）
        if not self._ensure_vectors():
            return []
        try:
            qv = self._embedder.embed_one(query)
        except Exception:                            # noqa: BLE001 — 服务故障降级
            return []
        if not qv:
            return []
        scored: list[tuple[str, float]] = []
        for scene_id, v in self._vectors.items():
            s = LocalEmbedder.cosine(qv, v)
            if s >= self.threshold:
                scored.append((scene_id, s))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]

    def resolve_one(self, text: str) -> str | None:
        """便捷: 最高分 scene_id（低于阈值 → None = 上层保持上一场景）。"""
        hits = self.resolve(text, k=1)
        return hits[0][0] if hits else None

    def scenes(self) -> list[str]:
        """语料全部 scene_id（与导演词表对齐; 排查用）。"""
        return sorted(self._aliases)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """读 places.yml → 别名表。缺失/损坏 → 空语料（宁缺勿错, 不阻断）。"""
        try:
            data = yaml.safe_load(self._places_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return
        raw = data.get("places") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return
        for scene_id, aliases in raw.items():
            if not isinstance(scene_id, str) or not isinstance(aliases, list):
                continue
            clean = [a for a in aliases if isinstance(a, str) and a.strip()]
            if not clean:
                continue
            self._aliases[scene_id] = clean
            for a in clean:
                self._id2alias.setdefault(a, scene_id)

    def _exact(self, query: str) -> str | None:
        """词表 id / 别名整串或子串命中 → scene_id（精确优先, 服务无关）。"""
        q = query.lower()
        # 整串命中（id 或别名）
        if q in self._id2alias:
            return self._id2alias[q]
        if q in self._aliases:
            return q
        # 词表 id 原样在文本里出现（LLM 直接输出 place id 的情况）
        for scene_id in self._aliases:
            if scene_id in q:
                return scene_id
        return None

    def _ensure_vectors(self) -> bool:
        """懒构建: 每 scene 取别名向量最大值（合并成一个代表向量）。失败 → False。"""
        if self._vectors is not None:
            return True
        if not self._aliases:
            return False
        if not self._embedder.health():
            return False
        try:
            # 一次性批出全部别名向量, 再按 scene 取 max
            flat: list[str] = []
            for aliases in self._aliases.values():
                flat.extend(aliases)
            vecs = self._embedder.embed(flat)
        except Exception:                            # noqa: BLE001 — 服务故障: 无语义层
            self._vectors = {}
            return False
        out: dict[str, list[float]] = {}
        idx = 0
        for scene_id, aliases in self._aliases.items():
            best: list[float] | None = None
            best_s = -1.0
            for _ in aliases:
                v = vecs[idx]
                idx += 1
                s = sum(x * x for x in v)
                if s > best_s:
                    best_s = s
                    best = v
            if best is not None:
                out[scene_id] = best
        self._vectors = out
        return True
