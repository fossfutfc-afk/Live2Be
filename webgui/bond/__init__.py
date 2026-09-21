# -*- coding: utf-8 -*-
"""`webgui.bond` 包**门面** —— 模块→包转换（C1b, `docs/EXEC_SPLIT.md`）。

## 这是什么

拆分前 `webgui/bond.py` 是一个 2900 行的单文件模块; C1b 起它是**包**:
原文件**逐字**搬进 `webgui/bond/_impl.py`（`git diff -M` 呈 100% 相似度的纯移动）,
本文件负责把它的对外名字**一个不少地**再导出 —— import 路径不变 ⇒
13 个引用点（`webgui/routers/*`、`webgui/chat.py`、`webgui/deps.py`、
`tests/webgui/*`、`experiments/`、`l2d-demo/`）**一个字都不用改**。

## 为什么是"逐个显式再导出"而不是 `from ._impl import *`

三件事会当场坏掉:
1. **私有名会丢** —— `_enqueue_annotate` / `_state` / `_END_ROUNDS` / `_system_note` …
   外部真的在用（`webgui/deps.py` 的懒转发、`tests/webgui/test_bond*.py` 直接 import）;
   `import *` 不带下划线名。
2. **API 面守门会误报"全丢"** —— `tests/core/test_split_safety.py` 的名字扫描按
   **字面名字**认（`from webgui.bond._impl import *` 只会被它读到一个 `*`）。
3. **静态可读** —— 想知道"这个包对外有什么", 读这一块就够, 不用去跑 `dir()`。

## 纪律

· 本文件**只做再导出**, 不放逻辑（逻辑在 `_impl.py`; C3 起按职责拆到
  `stores.py` / `lanes.py` / … , 每拆一块只改**这里的一行来源**）;
· ⚠️ **不定义 `__all__`** —— 它会被 API 面快照记成一个新名字（`webgui.bond __all__`）,
  而 C1b 的验收标准之一是**快照零 diff**（= "纯搬家"的硬证据）; 这块显式 import 列表
  本身就是白名单。
· ⚠️ **不要在这里放"可替换依赖"**（store / 生图器 / 看门狗阈值…）: 包内子模块读的是
  自己的全局, 打**包属性**会静默失效 —— 那类东西一律走 `webgui.deps`（C1a）。
· 往 `_impl.py` 加/删对外名字时同步这里; 漏了会被守门当场指出
  （`webgui.bond: 丢了 X` / `多出 X`）。
"""
from __future__ import annotations

from webgui.bond._impl import (
    BoardLifecycle,
    BondScene,
    BondState,
    BondStoryEngine,
    ChoiceCandidate,
    DEMO_SCRIPT,
    GalleryStore,
    MAX_GEN_FAILURES,
    M_MEMORIAL_IMAGE,
    M_SESSION_END,
    M_VN_ABANDON,
    M_VN_EXIT,
    SceneLoopError,
    _CLOSING_PARA,
    _CLOSING_TEXT,
    _END_ROUNDS,
    _REMIND_ROUNDS,
    _bonds,
    _build_director,
    _candidate_worker,
    _choice_pregen_enabled,
    _clear_rejects,
    _discard_boards,
    _discard_candidates,
    _ensure_memorial_img,
    _entry_already_done,
    _force_scene_ready,
    _gate_stalled,
    _generate,
    _lane_writer_alive,
    _lanes_idle,
    _log_board_deliver,
    _make_memorial_cb,
    _memorial_gen,
    _memorial_open_in_events,
    _note_reject,
    _persisted_memorial_img,
    _pregenerate,
    _ready_scene_payload,
    _role_info,
    _scene_landed,
    _spawn_candidates,
    _start_replay,
    _state,
    _system_note,
    _thread_alive,
    _trigger_title,
    _watchdog,
    _wrapup,
    _wrapup_inner,
    bond_finish,
    bond_start,
    bond_start_demo,
    bond_status,
    bond_turn,
    close_open_attempts,
    collect_ref_images,
    commit_staging,
    exclude_abandoned,
    load_brain_segment,
    logger,
    make_event,
    render_bond_scene_text,
    staging_store,
    truth_store,
    window_messages,
)

from webgui.bond.replay import (              # C5: 回放层
    _narrativize,
    replay_attempts,
    _interrupted_replay_queue,
    chapter_replay,
    _pending_in_vn,
    _title_from_events,
    _enter_title,
    _prev_chapter_quit,
)

from webgui.bond.lanes import (               # C4: 双路 lane + 就绪门控
    _memorial_no_visuals,
    _scene_emotions_ready,
    _scene_places_ready,
    _scene_visual_ready,
    _scene_obj_visual_ready,
    _scene_ready_or_busy,
    _wait_annotated,
    _ensure_lane,
    _enqueue_annotate,
    _enqueue_place_annotate,
    _anno_worker,
    _place_worker,
    _fallback_fill,
)

from webgui.bond.util import _ms_since                   # C4: 跨模块纯小工具

from webgui.bond.stores import (              # C3: 落库层
    _store,
    _flow_store,
    _stage_store,
    _last_bond_seq,
    _last_mmt_seq,
    _open_vn_seq,
    _DRAFT_FILE,
    _draft_path,
    _draft_boards,
    _draft_save,
    _draft_delete,
    _draft_load,
    _draft_pending,
    _draft_queue,
    _PREWARM_FILE,
    _prewarm_cache_path,
    _prewarm_cache_save,
    _prewarm_cache_load,
    _prewarm_cache_delete,
    _log_scene,
    _log_scene_meta,
    _close_memorial_window,
)

# 下面这些名字**定义处不在 bond 包内**（C3/C5 顺手清: `_impl.py` 里它们早就没人用了,
# 只是当年作为"bond 的对外面"一路被再导出——C5 把最后三个用点也搬进了 `replay.py`）
# —— 门面继续给, 但指向真家。
from contract import NON_PICKS                     # noqa: E402
from core.session.chapters import replayable_chapters          # noqa: E402
from core.session.events import (             # noqa: E402
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_VN_STATE,
)
from core.session.maintenance import abandoned_ranges          # noqa: E402
from llm.image_gen import image_enabled       # noqa: E402
