"""媒体查库 — assets/ 纯数据索引（差分/背景/spine → 路径）+ 情绪词表注入。

查询面（宁缺勿错, 查不到返回 None）:
    MediaCatalog.background(scene_id, variant=None)  → 背景（命名派生, 零 manifest）
    MediaCatalog.sprite(char_id, emotion)            → 差分（manifest 映射 + 可选 spine 导出）
    sprite_emotions / background_scenes              → 白名单（喂 ② 导演/播放协议）
    emotion_lexicon                                  → emotions.yml 逐行解析（词表+示范+eg → 主 LLM 注入）
    place_table                                      → 地点语义键表（**标注层**语料: 层1 别名 0 调用
                                                       + 层2 整表含 note; 动态读入/mtime 缓存）
    load_place_lexicon                               → 旧白名单 common_scenes（**只剩降级兜底**:
                                                       表读不出来时当 place_keys 用）

架构见 docs/DESIGN_VISUAL.md §5-① + docs/DESIGN_VISUAL_PROTOCOL.md。
"""
from core.media.background import BackgroundMedia, derive_background
from core.media.catalog import MediaCatalog, MediaError
from core.media.emotion_lexicon import (
    assets_root,
    build_emotion_injection,
    load_emotion_lexicon,
    load_place_lexicon,
    render_emotion_scale,
)
from core.media.place_table import (
    DEFAULT_TABLE_PATH,
    PlaceEntry,
    PlaceTable,
    load_table,
)
from core.media.place_table import (
    reset_cache as reset_place_cache,
)
from core.media.sprites import SpinePack, SpriteMedia

__all__ = [
    "MediaCatalog", "MediaError",
    "BackgroundMedia", "derive_background",
    "SpinePack", "SpriteMedia",
    "load_emotion_lexicon", "build_emotion_injection",
    "load_place_lexicon",
    "assets_root", "render_emotion_scale",
    # 地点语义键表（C1, 2026-09-19）——标注层的语料
    # （旧 `build_place_injection` 已于 PL4 删除: 生产零调用, 且它宣传的
    #  "主 LLM 只从词表里选 place" 早已被记录流 v2 + 零内容词表裁决废掉）
    "PlaceTable", "PlaceEntry", "load_table", "DEFAULT_TABLE_PATH",
    "reset_place_cache",
]
