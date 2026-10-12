"""RenderState — 渲染状态机（DESIGN_RENDERER.md §2.2 / §十）。

状态流:
    IDLE → SCENE_LOADING（背景/差分预解析）→ SCENE_PLAYING（段落逐条显示）
         → CHOICE（有选项: 等玩家）| NEXT（无选项: 自动下一场）| END（is_end）
    回放模式: PLAYING 自动推进（定时器）; 实时模式: CHOICE 等玩家输入。

状态字段（平台无关——GUI 据此做动画/布局, CLI 据此打标签）:
    background        当前背景（scene_id）
    background_transition  切换过渡时长（秒, 0 = 立即）
    sprite            当前角色差分 emotion（null = 无/保持）
    sprite_stack      逐段 emotion 序列（段落级表情变化）
    effects           逐段特效序列（每段落一个特效列表）
    paragraph_index   当前段落索引（-1 = 尚未开始）
    audio             当前音频请求（未来）
    choices           待选择项（CHOICE 态）
    is_end            剧情是否结束
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 状态常量
IDLE = "idle"
SCENE_LOADING = "scene_loading"
SCENE_PLAYING = "scene_playing"
CHOICE = "choice"
NEXT = "next"
END = "end"


@dataclass
class RenderState:
    """渲染状态（渲染器维护; 平台按状态字段渲染）。"""

    phase: str = IDLE
    background: str | None = None
    background_transition: float = 0.0
    sprite: str | None = None
    sprite_stack: list[str] = field(default_factory=list)
    effects: list[list[str]] = field(default_factory=list)
    paragraph_index: int = -1
    audio: "AudioRequest | None" = None       # noqa: F821 — 未来字段, audio.py 定义
    choices: list[str] = field(default_factory=list)
    is_end: bool = False

    # ------------------------------------------------------------------
    # 状态推进（纯数据——平台渲染循环调用; 决策在渲染器/引擎, 这里只记账）
    # ------------------------------------------------------------------

    def begin_scene(self, *, background: str | None,
                    transition: float, sprite_stack: list[str],
                    effects: list[list[str]], choices: list[str],
                    is_end: bool, audio=None) -> None:
        """进入 SCENE_LOADING → 预解析完成即 SCENE_PLAYING（数据已备, 无异步）。"""
        self.phase = SCENE_LOADING
        self.background = background
        self.background_transition = transition
        self.sprite_stack = list(sprite_stack)
        self.effects = [list(fx) for fx in effects]
        self.paragraph_index = -1
        self.audio = audio
        self.choices = list(choices)
        self.is_end = is_end
        self.sprite = None
        self.phase = SCENE_PLAYING

    def advance_paragraph(self) -> None:
        """推进到下一段落（渲染完当前段落后调用）。末尾段落后进入 CHOICE/NEXT/END。"""
        if self.paragraph_index + 1 < len(self.sprite_stack):
            self.paragraph_index += 1
            self.sprite = self.sprite_stack[self.paragraph_index]
        else:
            self._finish()

    def _finish(self) -> None:
        """段落全部显示完 → 根据选项/结束标记进入 CHOICE/NEXT/END。"""
        if self.is_end:
            self.phase = END
        elif self.choices:
            self.phase = CHOICE
        else:
            self.phase = NEXT

    def resolve_choice(self) -> None:
        """玩家选择后 → NEXT（等引擎下一场; 回放模式自动取 picked）。"""
        if self.phase == CHOICE:
            self.phase = NEXT
