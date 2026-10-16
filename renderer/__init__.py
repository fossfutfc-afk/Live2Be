"""renderer/ — 羁绊剧情渲染器（DESIGN_RENDERER.md）。

显示层——与引擎（BondStoryEngine）解耦的纯消费方: 输入场景数据（RenderScene,
实时 from_live / 回放 from_event 同构）, 输出渲染状态（RenderOutput——
背景/差分/特效/音频/文本）。同一渲染管线服务实时播放与回放。

公开 API:
    Renderer           渲染管线入口（render(scene) → RenderOutput）
    RenderScene        输入规范化（from_live / from_event 双用途）
    RenderOutput       平台无关输出（GUI/CLI 各自消费）
    BackgroundResult   背景解算结果（图 + 过渡）
    AudioRequest       音频指令（未来占位）

模块:
    scene.py      输入规范化
    state.py      渲染状态机（IDLE→LOADING→PLAYING→CHOICE/NEXT/END）
    background.py 背景解算（catalog 查库 + 切换/过渡）
    sprite.py     差分意图层（段落 emotion → emotion 序列, 不查图）
    effects.py    特效查表（角色表 → 全局表 → 空, 确定性）
    audio.py      AudioRequest + 音频状态（未来占位接口）
    core.py       渲染管线（scene → RenderOutput; 双用途入口）
    cli.py        CLI 输出（打字/标签/选项; 迁移自 `cli/vn_cli.py`——当时叫 `core/ui/vn_cli.py`）

播放层（独立于 renderer）: core/media/sprite_player.py（play_diff / play_spine）。
"""
from renderer.audio import AudioRequest
from renderer.background import BackgroundResolver, BackgroundResult
from renderer.core import Renderer, RenderOutput
from renderer.effects import EffectResolver
from renderer.scene import RenderScene
from renderer.sprite import SpriteResolver
from renderer.state import RenderState

__all__ = [
    "Renderer", "RenderOutput", "RenderScene", "RenderState",
    "BackgroundResolver", "BackgroundResult",
    "SpriteResolver", "EffectResolver", "AudioRequest",
]
