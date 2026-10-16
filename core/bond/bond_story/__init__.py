"""`core.bond.bond_story` 包**门面** —— 只做再导出, 不放逻辑。

| 模块 | 管什么 |
|---|---|
| `scene.py` | `BondScene`（一场戏的载荷 + 渲染字段）/ `SceneLoopError` —— 叶子 |
| `boards.py` | `DeliveryMode` · `_board_spans`（记录 → 板）· `_BoardAssembler`（+ 板级闸）· `MAX_BOARDS_PER_TURN` |
| `engine.py` | `BondStoryEngine`（记录流解析 + 状态机 + 历史 + 生图钩子）· `MAX_SCENE_RETRIES` · `DEFAULT_HISTORY_ROUNDS` |

用法: `from core.bond.bond_story import BondStoryEngine`。

纪律: 名字增删同步 `tests/fixtures/api_surface.txt`（`SPLIT_API_UPDATE=1` 刷新）;
**不定义 `__all__`**（它会被 API 面快照记成一个新名字）; 下面按"真家"分块 —— 只有 11 个
名字真住在本包, 其余是当年路过 `bond_story.py` 的 `contract` / `core.*` / `llm.*` 名字。
"""

from contract import (  # 定义处不在本包内（当年路过 → 直指真家）
    CHARACTER_NARRATOR,
    KIND_CHARACTER,
    MAX_SENSEI_RUN,
    NON_PICKS,
    STAGE_ART,
    STAGE_END,
    STAGE_EXIT,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
    BlockStreamParser,
    Issue,
    IssueCode,
    VnBlock,
    VnRecord,
    build_record_schema,
    check_block,
    check_board,
    format_issues,
    sensei_groups,
    split_issues,
)
from contract.errors import (  # 定义处不在本包内（当年路过 → 直指真家）
    Live2BeError,
    err,
)
from core.bond.bond_story.boards import (  # C9: 板派生 + 交付模式
    MAX_BOARDS_PER_TURN,
    DeliveryMode,
    _board_spans,
    _BoardAssembler,
)
from core.bond.bond_story.engine import (  # C9: 引擎（记录流 → 板 → 状态机）
    DEFAULT_HISTORY_ROUNDS,
    MAX_SCENE_RETRIES,
    BondStoryEngine,
    _personality_summary,
    logger,
)
from core.bond.bond_story.scene import (  # C9: 场景容器（叶子）
    BondScene,
    SceneLoopError,
)
from core.bond.place_annotate import (  # 定义处不在本包内（当年路过 → 直指真家）
    annotate_places,
    resolve_place,
)
from core.bond.variant_annotate import (  # 定义处不在本包内（当年路过 → 直指真家）
    pick_image,
)
from core.media.emotion_lexicon import (  # 定义处不在本包内（当年路过 → 直指真家）
    assets_root,
    build_emotion_injection,
    load_emotion_lexicon,
    load_place_lexicon,
)
from core.media.place_table import (  # 定义处不在本包内（当年路过 → 直指真家）
    PlaceTable,
    load_table,
)
from core.parsing.dynamic_character_parser import (  # 定义处不在本包内（当年路过 → 直指真家）
    CharacterLoader,
    DynamicCharacter,
)
from core.promptkit import (  # 定义处不在本包内（当年路过 → 直指真家）
    BlockContext,
    build_box,
    round_messages,
    task_card,
    task_card_enabled,
)
from core.session.renderer import (  # 定义处不在本包内（当年路过 → 直指真家）
    render_bond_scene_text,
)
from llm.client import (  # 定义处不在本包内（当年路过 → 直指真家）
    LLMClient,
    feedback,
)
from llm.task_labels import (  # 定义处不在本包内（当年路过 → 直指真家）
    BOND,
)
from llm.task_levels import (  # 定义处不在本包内（当年路过 → 直指真家）
    max_tokens as task_levels_max_tokens,
)
