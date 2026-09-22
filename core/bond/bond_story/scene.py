# -*- coding: utf-8 -*-
"""`core.bond.bond_story` 的**场景容器**（C9, `docs/EXEC_SPLIT.md`）。

`BondScene`（一场戏的载荷: `paragraphs` / `choices` / `branches` / `is_end` / `picked` +
`to_dict` / `from_dict` 与渲染用字段）· `SceneLoopError`（场级循环失败 → 上层重试/收尾）。

## 纪律

· 本模块是**叶子**: 不 import 同包其它模块（`boards` / `engine` 都反过来往下看它）;
· 搬进来的代码**逐字未改**。
"""

from __future__ import annotations

from contract import (
    NON_PICKS,
    STAGE_ART,
    STAGE_END,
    STAGE_EXIT,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
)
from core.common import Live2BeError
from dataclasses import (
    dataclass,
    field,
)


class SceneLoopError(Live2BeError):
    """单场景解析或执行任一失败超过 MAX_SCENE_RETRIES 仍未通过（循环必须终结, 宁缺勿错）。"""


@dataclass
class BondScene:
    """一个羁绊剧情场景（story_scene 契约解析后的程序侧结构）。

    paragraphs — 叙事段落（每项 {text, emotion?}: text=段落文本, emotion=可选表情词表键;
                  2026-08-23 架构定稿: 情绪内联进段落, 删 beats——emotion 缺省 = 延续上一段）
    choices    — 选项列表（空 = 无选项; 有选项时玩家选一个, 喂回下一场景）
    is_end     — 是否剧情结束（契约 is_end=true）
    background — 导演层视觉字段（背景 scene_id; None = 纯文本模式）
    audio      — 导演层音频字段（占位; 当前恒 None, 未来背景/音乐仲裁填）
    place      — 主 LLM 意图字段（场景级地点 scene_id, 协议 §5; None = 未标注/保持）
    """

    paragraphs: list[dict] = field(default_factory=list)   # [{text, emotion?}]
    choices: list[str] = field(default_factory=list)
    # 板块契约（2026-08-30）: 同响应分支内容 {选项文本: [段落…]}——玩家选该选项后
    # 立即展示（零等待, Storyloom <choice>+<branch> 模式）; 空 = 无分支
    branches: dict[str, list] = field(default_factory=dict)
    is_end: bool = False
    background: str | None = None
    audio: str | None = None
    place: str | None = None
    title: str | None = None        # 章节标题（如"预先应对"）——开场标题面板; None = 不显示
    # SceneStream P1（2026-09-08）: 段分组边界（句平铺列表里每个自然段的终点下标）。
    # 仅引擎侧标注流水消费——**不进 to_dict/from_dict**（事件/回放不携带）
    segments: list[int] | None = None
    # 记录流 v2（2026-09-10, P0-4b）: 本板记录（真源）+ 解析记账。
    # paragraphs/choices 由记录**派生**（过渡期：老 renderer/前端照旧吃派生字段,
    # 消费者迁移见 §11 P0-7）；空 = 本场景来自旧动作路径（回放旧档/开发通道）。
    records: list[dict] = field(default_factory=list)     # [{"character"|"stage":…, "text":…}]
    notes: list[str] = field(default_factory=list)        # 解析 NOTE/DROP（可观测, 不进 LLM）
    # 记录流 v2 额外信号: 换场记录原文（P1 翻译成资产键）+ 本板是否含纪念触发 +
    # 块级画面意向（`art` 声明——本块含纪念时提前开画, §10.4）。
    # 三者都**不进 LLM 上下文**（历史渲染只出叙事/switch 文本）。
    place_hint: str | None = None
    #: **选图结果**（第二遍, 2026-09-19）: 这个地点的**哪一张图**（表 `files` 里的
    #: 相对路径, 如 `SDIR_Outer/…/BG_SchoolRooftop2_Night.jpg`）。空 = 用默认图
    #: （旧事件没有这个字段 → 回放安全, 落回第一条）。与 `place` 同属视觉键,
    #: **不进 LLM 上下文**。
    place_asset: str | None = None
    memorial: bool = False
    #: **记录级进入点**（2026-09-20, docs/DESIGN_MEMORIAL.md M3）: `stage:memorial`
    #: 那条记录在 **`paragraphs` 里的下标**——前端据此在"播到那一段时"才切黑屏
    #: （隐藏立绘 + 清空普通背景 + 图淡入）。语义见 `syncMemorial`:
    #: **这句 text 本身就是黑屏期里唯一的内容**，所以黑屏必须从它开始。
    #: None = 没有纪念记录（旧档/普通板）→ 前端按板级处理（整板即窗口）。
    memorial_at: int | None = None
    #: ⭐ **板级纪念窗口快照**（2026-09-23, 真机报障结案）: 这块板**在不在纪念窗口里**。
    #: 窗口 = 本块的 `memorial` 记录之后 → 本块块尾（同块后续板都还在窗口里）。
    #: 由组装器**造板那一刻**算好（`boards._BoardAssembler`）——那一刻它必然知道。
    #: ⚠️ 为什么不直接问引擎的 `_in_memorial`: 那是"**解析**到哪了"的活标志, 而
    #: 预热/预生成会**提前解析后面的块** ⇒ 纪念板真正交付时它早被翻回 False, 前端于是
    #: 不点亮纪念层（不黑屏、不淡入图）。快照到板上就与解析/交付顺序彻底解耦。
    #: 与 `memorial` 的分工: `memorial` = "**本板含**触发记录"; 本字段 = "本板在窗口里"。
    in_memorial: bool = False
    art_hint: str = ""
    #: 已裁决的选项原文（决策 #37）: 只作**展示标记**——回放/续看时前端据此把选项组
    #: 画出来（锁定 + 高亮所选）; 绝不进 paragraphs（玩家的话语只体现为选项）。
    picked: str = ""
    #: 运行时标记: 该板已在**流式**过程中交付给调用方（勿重复落地）——不进序列化
    _streamed: bool = False

    @classmethod
    def from_board(cls, records: tuple, group: tuple[int, ...] = (), *,
                   notes: list[str] | None = None,
                   in_memorial: bool = False) -> "BondScene":
        """一块记录（板切片）→ BondScene（记录流 v2, P0-4b）。

        - `paragraphs` **由记录派生**（一记录 = 一判定/显示单元）:
          `switch`/`art`/`exit` 是引擎信号（不显示）; 群内候选（老师的话）不显示
          ——它们变成 `choices`; 其余（角色/narrator/sensei 之外的正文）照常显示;
        - `choices` = 本板群内候选台词（run=1 也弹, 拍板 18）;
        - `is_end` = 本板含 `stage:end`/`exit`（记录是块尾, 故只可能落在末板）;
        - `records` = **真源**（含全部记录, 落库/回放用）。
        - `in_memorial` = **板级窗口快照**（2026-09-23）: "这块板在不在纪念窗口里"。
          由组装器在**造板那一刻**给定（窗口 = 本块 memoir 记录之后到块尾）——
          ⚠️ **不是**引擎那个"解析到哪了"的活标志: 预热会提前解析后面的块, 交付纪念板时
          它早被翻回 False ⇒ 前端不点亮纪念层（真机报障）。见 `boards._BoardAssembler`。
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
                    # 记录级进入点（2026-09-20）: 记住它落在 paragraphs 的第几段
                    memorial_at = len(paras)
                item: dict = {"text": rec.text}
                if not rec.is_stage:
                    item["speaker"] = rec.value        # 最小说话人形态（UI 样式留 P0-7）
                paras.append(item)
        is_memorial = any(r.stage == STAGE_MEMORIAL for r in records)
        if is_memorial and memorial_at is None:
            # 触发记录没带 text（空串）⇒ 屏上没有属于它的那一句 → 退回板级
            # （整板即窗口, 与 2026-09-20 之前的行为一致; 宁缺勿错）
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
        """序列化为存档/契约同构 dict（回放读档的反向）。

        视觉/意图字段空值（None / 空列表）→ 省略, 不污染存档（旧档兼容）。
        记录流板额外带 `records`（**唯一真源**）+ `notes`（可观测）。
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
    def from_dict(cls, raw: dict | None) -> "BondScene":
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
