"""RenderScene — 渲染器输入规范化（实时 + 回放双用途, DESIGN_RENDERER.md §2.1）。

实时与回放的 scene dict 字段完全一致（BondScene.to_dict() 契约）:
    paragraphs: [{text, emotion?}]   叙事段落（emotion 缺省 = 延续上一段）
    choices:    [str]                选项（空 = 无选项）
    is_end:     bool                 剧情是否结束
    background: str | None           导演层背景 scene_id（None = 纯文本模式）
    audio:      str | None           音频占位（当前恒 None, 未来）
    place:      str | None           场景级地点意图（导演已消费, 渲染器只读）
    input:      str                  回放附加: 本场触发输入（实时可为空）
    picked:     str | None           回放附加: 玩家当时的选择

构造路径:
    from_live(scene)   — 实时: 引擎 BondScene（鸭子类型: 任何有 to_dict() 的对象,
                         不 import 引擎——渲染器零引擎依赖, 防循环依赖 + 回放复用）
    from_event(payload)— 回放: 事件流 bond 事件 payload（同构 dict）

坏数据容错（宁缺勿错）: 缺失字段 → 空/None, 坏项过滤, 不 raise。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RenderScene:
    """一个待渲染场景（平台无关的输入规范化）。"""

    paragraphs: list[dict] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    is_end: bool = False
    background: str | None = None
    audio: str | None = None
    place: str | None = None
    input: str = ""
    picked: str | None = None

    # ------------------------------------------------------------------
    # 构造路径
    # ------------------------------------------------------------------

    @classmethod
    def from_live(cls, scene) -> "RenderScene":
        """实时: 引擎场景对象 → RenderScene。

        scene 是鸭子类型（BondScene 或任何有 to_dict() 的对象）——渲染器
        不 import 引擎（core/bond_story）, 只认 dict 契约。
        to_dict 失败/非 dict → 空场景（宁缺勿错, 不 raise）。
        input/picked 是回放附加字段——实时路径无此概念, 强制清空。
        """
        try:
            raw = scene.to_dict()
        except Exception:                                  # noqa: BLE001
            raw = None
        out = cls._from_dict(raw)
        out.input = ""
        out.picked = None
        return out

    @classmethod
    def from_event(cls, payload: dict | None) -> "RenderScene":
        """回放: 事件流 bond 事件 payload → RenderScene。

        事件流里 bond 事件的 payload = {**scene.to_dict(), "input": ..., "picked": ...}
        （vn_cli 落库格式）——input/picked 是回放附加信息, 实时路径没有。
        """
        if not isinstance(payload, dict):
            return cls()
        return cls._from_dict(payload)

    # ------------------------------------------------------------------
    # 内部: 统一规范化（坏数据过滤, 宁缺勿错）
    # ------------------------------------------------------------------

    @classmethod
    def _from_dict(cls, raw) -> "RenderScene":
        if not isinstance(raw, dict):
            return cls()
        paras: list[dict] = []
        for p in raw.get("paragraphs", []):
            if isinstance(p, str) and p.strip():
                paras.append({"text": p.strip()})
            elif isinstance(p, dict):
                text = p.get("text")
                if isinstance(text, str) and text.strip():
                    item: dict = {"text": text.strip()}
                    emotion = p.get("emotion")
                    if isinstance(emotion, str) and emotion.strip():
                        item["emotion"] = emotion.strip()
                    # 记录流 v2 说话人（最小形态）: speaker = 记录取值, speaker_name =
                    # 调用方映射好的显示名（CLI 直接用后者画名字行）
                    for key in ("speaker", "speaker_name"):
                        v = p.get(key)
                        if isinstance(v, str) and v.strip():
                            item[key] = v.strip()
                    paras.append(item)
        choices = [c for c in raw.get("choices", []) if isinstance(c, str)]
        background = raw.get("background")
        audio = raw.get("audio")
        place = raw.get("place")
        inp = raw.get("input", "")
        picked = raw.get("picked")
        return cls(
            paragraphs=paras,
            choices=choices,
            is_end=bool(raw.get("is_end", False)),
            background=background if isinstance(background, str) else None,
            audio=audio if isinstance(audio, str) else None,
            place=place if isinstance(place, str) else None,
            input=inp if isinstance(inp, str) else "",
            picked=picked if isinstance(picked, str) else None,
        )
