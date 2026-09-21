# -*- coding: utf-8 -*-
"""`core.bond.bond_story` 包**门面** —— 模块→包转换 + 内部拆分（C9, `docs/EXEC_SPLIT.md`）。

## 这是什么

拆分前 `core/bond/bond_story.py` 是一个 1575 行的单文件模块（`BondStoryEngine` 占 1074）。
现在它是包:

| 模块 | 管什么 |
|---|---|
| `scene.py` | `BondScene`（一场戏的载荷 + 渲染字段）/ `SceneLoopError` —— **叶子** |
| `boards.py` | `DeliveryMode`（BLOCK/STREAM）· `_board_spans`（记录 → 板）· `_BoardAssembler`（+ 板级闸）· `MAX_BOARDS_PER_TURN` |
| `engine.py` | `BondStoryEngine`（记录流解析 + 状态机 + 历史 + 生图钩子）· `_personality_summary` · `MAX_SCENE_RETRIES` · `DEFAULT_HISTORY_ROUNDS` |

import 路径 `core.bond.bond_story` **不变** ⇒ 39 处引用（`webgui/` · `core/ui` ·
`tests/` · `experiments/` · `l2d-demo/`）**一个字都不用改**。

## 用法（原模块 docstring 的示例照旧成立）

    from core.bond.bond_story import BondStoryEngine
    vn = BondStoryEngine(characters_root, llm_client)

## 纪律

· 本文件**只做再导出**; 名字增删请同步这里与 `tests/fixtures/api_surface.txt`
  （`SPLIT_API_UPDATE=1` 刷新）—— 守门会以"丢了/多出 X"指路;
· ⚠️ **不定义 `__all__`**（它会被 API 面快照记成一个新名字）;
· 门面把 **54 个名字按"真家"分块**列出: 11 个在本包三个模块里, 其余 43 个当年只是路过
  `bond_story` 的 `contract` / `core.*` / `llm.*` 名字 —— 这里直指真家（不再借道）。
"""

from core.bond.bond_story.scene import (          # C9: 场景容器（叶子）
    BondScene,
    SceneLoopError,
)

from core.bond.bond_story.boards import (          # C9: 板派生 + 交付模式
    DeliveryMode,
    MAX_BOARDS_PER_TURN,
    _BoardAssembler,
    _board_spans,
)

from core.bond.bond_story.engine import (          # C9: 引擎（记录流 → 板 → 状态机）
    BondStoryEngine,
    DEFAULT_HISTORY_ROUNDS,
    MAX_SCENE_RETRIES,
    _personality_summary,
    logger,
)

from contract import (          # 定义处不在本包内（当年路过 → 直指真家）
    BlockStreamParser,
    CHARACTER_NARRATOR,
    Issue,
    IssueCode,
    KIND_CHARACTER,
    MAX_SENSEI_RUN,
    NON_PICKS,
    STAGE_ART,
    STAGE_END,
    STAGE_EXIT,
    STAGE_MEMORIAL,
    STAGE_SWITCH,
    VnBlock,
    VnRecord,
    build_record_schema,
    check_block,
    check_board,
    format_issues,
    sensei_groups,
    split_issues,
)

from core.bond.place_annotate import (          # 定义处不在本包内（当年路过 → 直指真家）
    annotate_places,
    resolve_place,
)

from core.bond.variant_annotate import (          # 定义处不在本包内（当年路过 → 直指真家）
    pick_image,
)

from core.common import (          # 定义处不在本包内（当年路过 → 直指真家）
    Live2BeError,
    err,
)

from core.media.emotion_lexicon import (          # 定义处不在本包内（当年路过 → 直指真家）
    assets_root,
    build_emotion_injection,
    load_emotion_lexicon,
    load_place_lexicon,
)

from core.media.place_table import (          # 定义处不在本包内（当年路过 → 直指真家）
    PlaceTable,
    load_table,
)

from core.parsing.dynamic_character_parser import (          # 定义处不在本包内（当年路过 → 直指真家）
    CharacterLoader,
    DynamicCharacter,
)

from core.promptkit import (          # 定义处不在本包内（当年路过 → 直指真家）
    BlockContext,
    build_box,
    round_messages,
    task_card,
    task_card_enabled,
)

from core.session.renderer import (          # 定义处不在本包内（当年路过 → 直指真家）
    render_bond_scene_text,
)

from llm.client import (          # 定义处不在本包内（当年路过 → 直指真家）
    LLMClient,
    feedback,
)

from llm.task_labels import (          # 定义处不在本包内（当年路过 → 直指真家）
    BOND,
)

from llm.task_levels import (          # 定义处不在本包内（当年路过 → 直指真家）
    max_tokens as task_levels_max_tokens,
)
