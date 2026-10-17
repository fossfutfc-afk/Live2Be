"""`core.bond.bond_story` 的**场景容器**。

`BondScene`（一场戏的载荷: `paragraphs` / `choices` / `branches` / `is_end` / `picked` +
`to_dict` / `from_dict` 与渲染字段）· `SceneLoopError`（场级循环失败 → 上层重试/收尾）。

本模块是**叶子**: 不 import 同包其它模块（`boards` / `engine` 都反过来看它）。
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
)

from contract import (
    NON_PICKS,
    STAGE_ART,
    STAGE_END,
    STAGE_EXIT,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
)
from contract.errors import Live2BeError


class SceneLoopError(Live2BeError):
    """单场景解析或执行任一失败超过 MAX_SCENE_RETRIES 仍未通过（循环必须终结, 宁缺勿错）。"""


@dataclass
class BondScene:
    """一个羁绊剧情场景（记录流 v2 的显示/回放载荷）——字段见下面各行的注解。

    不变量: `records` 是**真源**, `paragraphs` / `choices` 由它**派生**;
    视觉键（`place*` / `art_hint` / `emotion`）**不进 LLM 上下文**, 只进事件流供回放。
    """

    paragraphs: list[dict] = field(default_factory=list)   # [{text, emotion?, speaker?}]
    choices: list[str] = field(default_factory=list)
    # 同响应分支内容 {选项文本: [段落…]}——玩家选该选项后立即展示（零等待）; 空 = 无分支
    branches: dict[str, list] = field(default_factory=dict)
    is_end: bool = False
    background: str | None = None
    audio: str | None = None
    place: str | None = None
    title: str | None = None        # 章节标题（如"预先应对"）——开场标题面板; None = 不显示
    # 段分组边界（句平铺列表里每个自然段的终点下标）——只给引擎侧标注用, 不进序列化
    segments: list[int] | None = None
    # 本板记录（**真源**; paragraphs/choices 由它派生）+ 解析 NOTE/DROP 记账（不进 LLM）
    records: list[dict] = field(default_factory=list)     # [{"character"|"stage":…, "text":…}]
    notes: list[str] = field(default_factory=list)
    #: 换场记录原文（P1 翻译成资产键）; 与 `place_asset` / `art_hint` 同属视觉键, 不进 LLM
    place_hint: str | None = None
    #: **选图结果**（第二遍）: 这个地点的哪一张图（表 `files` 里的相对路径）。
    #: 空 = 用默认图（旧事件没这个字段 → 回放安全）; 与 `place` 同属视觉键, 不进 LLM。
    place_asset: str | None = None
    memorial: bool = False
    #: **记录级进入点**: `stage:memorial` 那条记录在 `paragraphs` 里的下标 —— 前端播到
    #: 那一段才切黑屏（隐藏立绘 + 清空普通背景 + 图淡入）; None = 退回板级（整板即窗口）。
    memorial_at: int | None = None
    #: **板级纪念窗口快照**: 这块板在不在纪念窗口里（窗口 = 本块的 memorial 记录 → 块尾）。
    #: 由组装器造板那一刻算好 —— 不直接问引擎的 `_in_memorial`: 那是"解析到哪了"的活标志,
    #: 预热会提前解析后面的块 ⇒ 交付纪念板时它早翻回 False, 前端就不点亮纪念层。
    #: 与 `memorial` 的分工: 它 = "本板**含**触发记录"; 本字段 = "本板在窗口里"。
    in_memorial: bool = False
    art_hint: str = ""
    #: 已裁决的选项原文: 只作**展示标记**（回放/续看时前端据它把选项组画出来并高亮所选）;
    #: 绝不进 paragraphs —— 玩家的话语永远只体现为选项。
    picked: str = ""
    #: 运行时标记: 该板已在**流式**过程中交付（勿重复落地）——不进序列化
    _streamed: bool = False
    #: 运行时标记: place lane 已对这块板试过（判完即置, 含判不出）——**不进序列化**。
    #: 置它 = "视觉键这条路对这块板已经走完", 所以推进门控才肯放行; 回放 / 分支 / 候选
    #: 这些"键已定格"的板直接置 True, 不占 lane（读侧一律 `getattr(scene, "_place_done", False)`）。
    _place_done: bool = False
    #: 运行时标记: 这块板由**哪一次生成调用**写出（短 id, 台账/草稿旁路读它）——不进序列化。
    #: 空串 = 不知道（0 LLM 领出来的板沿用产出它那一次调用的 id）。
    _call_id: str = ""
    #: 运行时标记: 这块板是从**草稿旁路**灌回来的（交付台账据此打 `src=draft`）——不进序列化。
    _from_draft: bool = False

    @classmethod
    def from_board(cls, records: tuple, group: tuple[int, ...] = (), *,
                   notes: list[str] | None = None,
                   in_memorial: bool = False) -> BondScene:
        """一块记录（板切片）→ BondScene。

        `paragraphs` 由记录派生（一记录 = 一判定/显示单元）: `switch` / `art` / `exit` 是
        引擎信号（不显示）, 群内候选（老师的话）变成 `choices`, 其余照常显示。
        `records` 留真源; `in_memorial` = 板级窗口快照（由组装器在造板那一刻给定）。
        """
        paras: list[dict] = []
        memorial_at: int | None = None
        for i, rec in enumerate(records):
            if i in group:
                continue
            if rec.is_stage and rec.stage in (STAGE_SWITCH, STAGE_ART, STAGE_EXIT):
                continue
            if rec.text:
                if rec.is_stage and rec.stage == STAGE_MEMORIAL:
                    # 记录级进入点: 记住它落在 paragraphs 的第几段
                    memorial_at = len(paras)
                item: dict = {"text": rec.text}
                if not rec.is_stage:
                    item["speaker"] = rec.value        # 最小说话人形态（UI 样式留 P0-7）
                paras.append(item)
        is_memorial = any(r.stage == STAGE_MEMORIAL for r in records)
        if is_memorial and memorial_at is None:
            # 触发记录没带 text ⇒ 屏上没有属于它的那一句 → 退回板级（整板即窗口）
            memorial_at = 0
        scene = cls(
            paragraphs=paras,
            choices=[records[i].text for i in group],
            is_end=any(r.stage in (STAGE_END, STAGE_EXIT) for r in records),
            memorial=is_memorial,
            memorial_at=memorial_at,
            in_memorial=bool(in_memorial),
            place_hint=(records[0].text if records and records[0].stage == STAGE_SWITCH
                        else None),
            records=[r.to_dict() for r in records],
            notes=list(notes or ()),
        )
        return scene

    def to_dict(self) -> dict:
        """序列化为存档/契约同构 dict。

        空值（None / 空列表）省略, 不污染存档; 记录流板额外带 `records`（真源）+ `notes`。
        """
        d = {
            "paragraphs": [dict(p) if isinstance(p, dict) else {"text": p}
                           for p in self.paragraphs],
            "choices": list(self.choices),
            "is_end": bool(self.is_end),
        }
        if self.records:
            d["records"] = [dict(r) for r in self.records]
        if self.notes:
            d["notes"] = list(self.notes)
        if self.place_hint:
            d["place_hint"] = self.place_hint
        if self.memorial:
            d["memorial"] = True
        if self.in_memorial:
            d["in_memorial"] = True
        if self.memorial_at is not None:
            d["memorial_at"] = int(self.memorial_at)
        if self.art_hint:
            d["art_hint"] = self.art_hint
        if self.picked:
            d["picked"] = self.picked
        if self.branches:
            d["branches"] = {
                k: [dict(p) if isinstance(p, dict) else {"text": p} for p in v]
                for k, v in self.branches.items()}
        if self.background is not None:
            d["background"] = self.background
        if self.audio is not None:
            d["audio"] = self.audio
        if self.place is not None:
            d["place"] = self.place
        if self.place_asset:
            d["place_asset"] = self.place_asset
        if self.title:
            d["title"] = self.title
        return d

    @classmethod
    def from_dict(cls, raw: dict | None) -> BondScene:
        """宽松解析 dict → BondScene（运行时契约解析与回放读档同一条路径）。

        逐字段 .get 容错 + 过滤坏项 + is_end 缺省 False——宁缺勿错,
        坏数据不 raise, 只降级为空场景。paragraphs 兼容 str（旧档）与 {text, emotion?}。
        """
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
                    speaker = p.get("speaker")          # 记录流 v2: 最小说话人形态透传
                    if isinstance(speaker, str) and speaker.strip():
                        item["speaker"] = speaker.strip()
                    emotion = p.get("emotion")
                    if isinstance(emotion, str) and emotion.strip():
                        item["emotion"] = emotion.strip()
                    # 视觉键透传（P3b-2）: place 锚点（句级）随回放场景保留——
                    # 事件流 append-only 已定格, 回放渲染时间轴依赖它。
                    # `place_asset`（第二遍选的图）同理, 只是**段落级**。
                    pid = p.get("place")
                    if isinstance(pid, str) and pid.strip():
                        item["place"] = pid.strip()
                    passet = p.get("place_asset")
                    if isinstance(passet, str) and passet.strip():
                        item["place_asset"] = passet.strip()
                    paras.append(item)
        choices = [c for c in raw.get("choices", []) if isinstance(c, str)]
        branches: dict[str, list] = {}
        for k, v in (raw.get("branches") or {}).items():
            if not isinstance(k, str):
                continue
            branch_paras: list[dict] = []      # 独立变量名——不能复用 paras
            for p in v if isinstance(v, list) else []:
                if isinstance(p, str) and p.strip():
                    branch_paras.append({"text": p.strip()})
                elif isinstance(p, dict):
                    text = p.get("text")
                    if isinstance(text, str) and text.strip():
                        item: dict = {"text": text.strip()}
                        emo = p.get("emotion")
                        if isinstance(emo, str) and emo.strip():
                            item["emotion"] = emo.strip()
                        branch_paras.append(item)
            if branch_paras:
                branches[k] = branch_paras
        background = raw.get("background")
        audio = raw.get("audio")
        place = raw.get("place")
        title = raw.get("title")
        records = [dict(r) for r in raw.get("records", []) if isinstance(r, dict)]
        notes = [str(x) for x in raw.get("notes", []) if isinstance(x, str)]
        place_hint = raw.get("place_hint")
        place_asset = raw.get("place_asset")
        art_hint = raw.get("art_hint")
        picked_raw = raw.get("picked")
        picked = (picked_raw.strip()
                  if isinstance(picked_raw, str) and picked_raw.strip() not in NON_PICKS
                  else "")
        # **不把裁决句物化进 paragraphs**（决策 #37: 玩家的话语永远只体现为选项）。
        # 它一旦当正文上屏, 配上角色的名字牌就会被读成"角色说了玩家的话"
        # （真机报障）。`picked` 随场景带着走, 供回放 UI 把**选项组**画出来并高亮
        # 所选（见 webgui `showInteraction` 的 resolved 分支）。
        return cls(
            paragraphs=paras,
            choices=choices,
            branches=branches,
            is_end=bool(raw.get("is_end", False)),
            background=background if isinstance(background, str) else None,
            audio=audio if isinstance(audio, str) else None,
            place=place if isinstance(place, str) else None,
            title=title if isinstance(title, str) and title.strip() else None,
            records=records,
            notes=notes,
            place_hint=place_hint if isinstance(place_hint, str) and place_hint else None,
            place_asset=(place_asset.strip()
                         if isinstance(place_asset, str) and place_asset.strip() else None),
            memorial=bool(raw.get("memorial", False)),
            in_memorial=bool(raw.get("in_memorial", False)),
            memorial_at=(raw.get("memorial_at")
                         if isinstance(raw.get("memorial_at"), int)
                         and raw.get("memorial_at") >= 0 else None),
            art_hint=art_hint if isinstance(art_hint, str) else "",
            picked=picked,
        )
