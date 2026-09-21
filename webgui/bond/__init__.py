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
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_MEMORIAL_IMAGE,
    M_SESSION_END,
    M_VN_ABANDON,
    M_VN_EXIT,
    M_VN_STATE,
    NON_PICKS,
    SceneLoopError,
    _CLOSING_PARA,
    _CLOSING_TEXT,
    _DRAFT_FILE,
    _END_ROUNDS,
    _PREWARM_FILE,
    _REMIND_ROUNDS,
    _anno_worker,
    _bonds,
    _build_director,
    _candidate_worker,
    _choice_pregen_enabled,
    _clear_rejects,
    _close_memorial_window,
    _discard_boards,
    _discard_candidates,
    _draft_boards,
    _draft_delete,
    _draft_load,
    _draft_path,
    _draft_pending,
    _draft_queue,
    _draft_save,
    _enqueue_annotate,
    _enqueue_place_annotate,
    _ensure_lane,
    _ensure_memorial_img,
    _enter_title,
    _entry_already_done,
    _fallback_fill,
    _flow_store,
    _force_scene_ready,
    _gate_stalled,
    _generate,
    _interrupted_replay_queue,
    _lane_writer_alive,
    _lanes_idle,
    _last_bond_seq,
    _last_mmt_seq,
    _log_board_deliver,
    _log_scene,
    _log_scene_meta,
    _make_memorial_cb,
    _memorial_gen,
    _memorial_no_visuals,
    _memorial_open_in_events,
    _ms_since,
    _narrativize,
    _note_reject,
    _open_vn_seq,
    _pending_in_vn,
    _persisted_memorial_img,
    _place_worker,
    _pregenerate,
    _prev_chapter_quit,
    _prewarm_cache_delete,
    _prewarm_cache_load,
    _prewarm_cache_path,
    _prewarm_cache_save,
    _ready_scene_payload,
    _role_info,
    _scene_emotions_ready,
    _scene_landed,
    _scene_obj_visual_ready,
    _scene_places_ready,
    _scene_ready_or_busy,
    _scene_visual_ready,
    _spawn_candidates,
    _stage_store,
    _start_replay,
    _state,
    _store,
    _system_note,
    _thread_alive,
    _title_from_events,
    _trigger_title,
    _wait_annotated,
    _watchdog,
    _wrapup,
    _wrapup_inner,
    abandoned_ranges,
    bond_finish,
    bond_start,
    bond_start_demo,
    bond_status,
    bond_turn,
    chapter_replay,
    close_open_attempts,
    collect_ref_images,
    commit_staging,
    exclude_abandoned,
    image_enabled,
    load_brain_segment,
    logger,
    make_event,
    render_bond_scene_text,
    replay_attempts,
    replayable_chapters,
    staging_store,
    truth_store,
    window_messages,
)
