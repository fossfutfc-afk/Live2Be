"""`webgui.bond` 包**门面** —— 模块→包转换 + 内部拆分（C1b–C8, `docs/EXEC_SPLIT.md`）。

## 这是什么

拆分前 `webgui/bond.py` 是一个 2900 行的单文件模块。现在它是包:

| 模块 | 管什么 |
|---|---|
| `state.py` | 状态模型: `BondState` / `BoardLifecycle` / `ChoiceCandidate` / 注册表 |
| `stores.py` | 落库层（事件流读写唯一出口 / 草稿旁路 / 预热缓存） |
| `lanes.py` | 双路标注 lane + 就绪门控 |
| `replay.py` | 回放层（resume 型回放 / 只读回放 / 认章定位） |
| `memorial.py` | 纪念生图 |
| `pregen.py` | 生成 / 预生成 / 候选支 / 丢弃 + 每轮系统注记 |
| `watchdog.py` | 看门狗（忙态 / 视觉门 / 预生成消费门 → 降级放行） |
| `entry.py` | 开场与场景载荷: `bond_start` / `bond_start_demo` / `DEMO_SCRIPT` / `_start_replay` / `_entry_already_done` / `_ready_scene_payload` / `_role_info`（**○C8b**）|
| `api.py` | 轮次 / 查询 / 收尾: `bond_turn` / `bond_status` / `bond_finish` + `_wrapup*` + 被拒诊断（方向 **api → entry**）|
| `util.py` | 跨模块纯小工具（`_ms_since`） |
| `deps.py`（**包外**） | 显式接缝: store / 生图器 / 看门狗阈值 / choice 开关 / 标注钩子 |

本文件把这 10 个模块的对外名字**一个不少地**再导出 —— import 路径 `webgui.bond` 不变 ⇒
13 个引用点（routers / chat / deps / tests / experiments / l2d-demo）**一个字都不用改**。

## 为什么是"逐个显式再导出"而不是 `from .api import *`

三件事会当场坏掉:
1. **私有名会丢** —— `_enqueue_annotate` / `_state` / `_END_ROUNDS` / `_system_note` …
   外部真的在用（`webgui/deps.py` 的懒转发、测试直接 import）; `import *` 不带下划线名。
2. **API 面守门会误报"全丢"** —— `tests/core/test_split_safety.py` 的名字扫描按
   **字面名字**认（`import *` 只会被它读到一个 `*`）。
3. **静态可读** —— 想知道"这个包对外有什么、住在哪", 读这一块就够。

## 纪律

· 本文件**只做再导出**, 不放逻辑;
· ⚠️ **不定义 `__all__`** —— 它会被 API 面快照记成一个新名字, 而"夹具零 diff"是 C1b–C8
  每个节点的验收之一; 这块显式 import 列表本身就是白名单;
· ⚠️ **不要在这里放"可替换依赖"**（store / 生图器 / 看门狗阈值…）: 包内子模块读的是
  自己的全局, 打**包属性**会静默失效 —— 那类东西一律走 `webgui/deps`（C1a）;
· 名字增删请同步这里与 `tests/fixtures/api_surface.txt`（`SPLIT_API_UPDATE=1` 刷新）,
  漏了会被守门当场指出（`webgui.bond: 丢了 X` / `多出 X`）。
"""

from contract import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    NON_PICKS,
)
from core.bond.bond_story import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    BondScene,
    BondStoryEngine,
    SceneLoopError,
)
from core.director.wiring import (  # 定义处不在 bond 包内（C11 起真家=接线层; 不再借道 CLI）
    _build_director,
    _trigger_title,
)
from core.media.gallery import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    GalleryStore,
)
from core.mmt.engine import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    load_brain_segment,
)
from core.session.chapters import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    replayable_chapters,
)
from core.session.events import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_MEMORIAL_IMAGE,
    M_SESSION_END,
    M_VN_ABANDON,
    M_VN_EXIT,
    M_VN_STATE,
    make_event,
)
from core.session.maintenance import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    abandoned_ranges,
    exclude_abandoned,
)
from core.session.renderer import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    render_bond_scene_text,
    window_messages,
)
from core.session.staging import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    close_open_attempts,
    commit_staging,
    staging_store,
    truth_store,
)
from llm.image_gen import (  # 定义处不在 bond 包内（当年作为「对外面」一路被再导出 → 直指真家）
    collect_ref_images,
    image_enabled,
)
from webgui.bond.api import (  # C8: 轮次 / 查询 / 收尾
    _clear_rejects,
    _note_reject,
    _wrapup,
    _wrapup_inner,
    bond_finish,
    bond_status,
    bond_turn,
    logger,
)
from webgui.bond.entry import (  # ○C8b: 开场与场景载荷
    DEMO_SCRIPT,
    _entry_already_done,
    _ready_scene_payload,
    _role_info,
    _start_replay,
    bond_start,
    bond_start_demo,
)
from webgui.bond.lanes import (  # C4: 双路 lane + 就绪门控
    _anno_worker,
    _enqueue_annotate,
    _enqueue_place_annotate,
    _ensure_lane,
    _fallback_fill,
    _memorial_no_visuals,
    _place_worker,
    _scene_emotions_ready,
    _scene_obj_visual_ready,
    _scene_places_ready,
    _scene_ready_or_busy,
    _scene_visual_ready,
    _wait_annotated,
)
from webgui.bond.memorial import (  # C6: 纪念生图
    _ensure_memorial_img,
    _make_memorial_cb,
    _memorial_gen,
    _persisted_memorial_img,
)
from webgui.bond.pregen import (  # C7: 生成/预生成/候选/丢弃
    _CLOSING_PARA,
    _CLOSING_TEXT,
    _END_ROUNDS,
    _REMIND_ROUNDS,
    MAX_GEN_FAILURES,
    _candidate_worker,
    _choice_pregen_enabled,
    _discard_boards,
    _discard_candidates,
    _generate,
    _log_board_deliver,
    _pregenerate,
    _scene_landed,
    _spawn_candidates,
    _system_note,
)
from webgui.bond.replay import (  # C5: 回放层
    _enter_title,
    _interrupted_replay_queue,
    _narrativize,
    _pending_in_vn,
    _prev_chapter_quit,
    _title_from_events,
    chapter_replay,
    replay_attempts,
)
from webgui.bond.state import (  # C2: 状态模型
    BoardLifecycle,
    BondState,
    ChoiceCandidate,
    _bonds,
    _memorial_open_in_events,
    _state,
)
from webgui.bond.stores import (  # C3: 落库层
    _DRAFT_FILE,
    _PREWARM_FILE,
    _close_memorial_window,
    _draft_boards,
    _draft_delete,
    _draft_load,
    _draft_path,
    _draft_pending,
    _draft_queue,
    _draft_save,
    _flow_store,
    _last_bond_seq,
    _last_mmt_seq,
    _log_pick,
    _log_scene,
    _log_scene_meta,
    _open_chapter_board_seq,
    _open_vn_seq,
    _prewarm_cache_delete,
    _prewarm_cache_load,
    _prewarm_cache_path,
    _prewarm_cache_save,
    _stage_store,
    _store,
)
from webgui.bond.util import (  # C4: 跨模块纯小工具
    _ms_since,
)
from webgui.bond.watchdog import (  # C8: 看门狗
    _force_scene_ready,
    _gate_stalled,
    _lane_writer_alive,
    _lanes_idle,
    _thread_alive,
    _watchdog,
)
