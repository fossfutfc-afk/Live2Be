"""
MomoTalk 对话引擎 — **行协议** agent loop（一行一条 JSON; ⑥-2e 起）。

每轮对话（agent_turn）:
    用户输入 → LLM 输出**行流**（裸文本, 每行一个 JSON 对象）:
        {"text": "话1"}                               # 消息行 = 说话（一条行 = 一个气泡）
        {"action": "mmt_send_media", "payload": …}    # 操作行 = 需要引擎执行的操作
        {"text": "话2"}                               # 任意交错（话→图→话 微信节奏）
    → 行解析（`mmt_lines`；坏行丢行 + 记账）→ **四阶段办理**（自愈 → 组合校验 →
      parse+执行 → **保持行序**交付）→ 逐行落事件/历史 + 轮数 +1
      → 触发羁绊剧情（trigger 行）才切换模式。
    契约与设计: `docs/DESIGN_STREAM_CONTRACT.md`（§1 六条 / §4 兜底分级 / §10.3 三个注入点）。

历史格式（每行一条, 可追溯 agent 干了什么）:
    user:      用户说的话
    assistant: "[mmt_chat] 话1" / "[mmt_send_media] …"（消息行记为 [mmt_chat],
               事件流同款, 渲染零改动）

五层认知（与 mmt_actions / mmt_executor 一致）:
    L0 自我层   build_prompt("momotalk") + 世界观（common+system 档）→ 常驻
    L1 人际层   interperson 自表条目注入（self_entry_to_prompt）→ 常驻
    L2 硬知识   LLM 世界知识 + 知识库（规划中）
    L3 深挖层   mmt_inspect_character（静默推理轮, 权重分级）→ 仅此入口

MomoTalk 与羁绊剧情的区别:
    - MomoTalk = 手机聊天, 无动作描写, 短消息, 逐行输出（…打字指示 + 气泡）
    - 羁绊剧情 = 视觉小说, 允许动作描写（括号）, 长对白（BondStoryEngine）

用法:
    engine = MomoTalkEngine("config/characters", llm_client)
    engine.start_session("haruka")
    result = engine.agent_turn("我们去天台吧？")
    for step in result.steps:   # …打字指示 + 气泡, 依序渲染
        ...
    engine.save_session()
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.common import Live2BeError, err
from llm.client import LLMClient, feedback
from llm.task_labels import MMT
from llm.task_levels import max_tokens as task_levels_max_tokens
from contract import APPROVAL_AUTO, DOMAIN_MMT, AgentAction, build_line_schema
from contract.issues import format_issues, split_issues
from core.bond.bond_progress import BondProgress
from core.mmt.mmt_actions import build_mmt_registry
from core.mmt.mmt_check import (
    ACTION_INSPECT,
    ACTION_TRIGGER,
    DROPPABLE_ACTIONS,
    WHOLE_TURN_ACTIONS,
    check_turn,
)
from core.mmt.mmt_lines import MmtLine, MmtStream, parse_lines, to_action_raw
from core.mmt.mmt_repair import build_candidates, repair_line
from core.mmt.mmt_executor import (
    MmtExecError,
    MmtExecutor,
    load_interperson,
)
from core.parsing.dynamic_character_parser import (
    CharacterLoader,
    DynamicCharacter,
    yaml_to_prompt,
)
from core.parsing.names import char_names, names_of   # 名字接口（N1: 别名/显示名的唯一实现）
from core.parsing.player_profile import player_names   # 玩家档案（config/player/profile.yml）
from core.promptkit import (
    BlockContext,
    build_box,
    round_messages,
    task_card,
    task_card_enabled,
)
from core.session import SessionStore
from core.session.events import TYPE_NOTICED, is_content_event, make_event
from core.session.renderer import session_status, window_messages
from core.brain.digest import digest_segment
from core.brain.entities import ensure_entities
from core.affection import Affection, load_affection_from_events
from core.brain.address import find_episode
from core.brain.recall import recall_episodes
from core.brain.render import (
    render_background_experience,
    render_character_view,
    render_recall_block,
)
from core.brain.store import WikiStoreV2
from core.rag.brain import make_embed_fn
from core.rag.embedder import LocalEmbedder
from core.tui.display import MomoTalkOutput
from core.tui.streaming import DisplayStep
# ⚠️ `split_reply_chunks` 不再进引擎（⑥-2e 起一行 = 一个气泡, 不再切句）——
# 切句器本体与单测按用户裁决**保留**（`core/tui/text_processors.py`; 见
# DESIGN_STREAM_CONTRACT §6: 将来真要用, 回退位置是"行内二次切分"）。
from core.tui.text_processors import _process_for_momotalk, _strip_action_brackets

logger = logging.getLogger(__name__)

#: RAG 语义召回后端（digest 联想, 2026-09-xx 接线 core/rag）——embed_fn 传给
#: digest_segment → recall_subgraph 通道1 用 embedding 相似度召回旧记忆。
#: **embed_fn 只在本机真的加载了 embedding 模型时才给出**（健康判定见 `_get_embed_fn`）。
_EMBED_FN = None

#: 最近一次上报过的 embed_fn 状态（None = 还没上报过）。
#: 只用于**状态跳变时才打日志**——附注记语义（INFO 级, 可 grep）, 不逐次刷屏。
_EMBED_REPORTED: bool | None = None


def _get_embed_fn():
    """懒构造 RAG embed_fn——**模型未就绪 → 返回 None**（调用方走关键词降级）。

    2026-09-13 修正（审计拆分点 A: 降级不可观测）: 原实现无条件
    `make_embed_fn(LocalEmbedder())`。而 `LocalEmbedder` 在服务未起/无 embedding
    模型时 `model == ""`、`embed()` 每次抛 `RagError`, 该异常又被 recall 侧
    `except Exception` 静默吞掉 → **每一轮 digest 都悄悄跑在词面关键词降级上,
    零日志**。后果不是崩溃而是**记忆质量静默损失**: Round B 的
    `recommend_candidates` 因此失去语义近似能力 → 引擎抬不出候选提示 →
    LLM 只能凭自己判断该并入还是新建, 判据少了一半。
    （旧口径下这里还会连带失效"候选 ≥ 阈值禁 add"的结构强制——**那条已在
    2026-09-15 T17 删除**, 候选现在只是提示, 所以降级的后果轻得多, 但依然要报。）
    更早的失效形态: 新经历一路 `add`, wiki 图退化成"一条经历配一个 belief"
    （现网 haruka 实测 4 episode → 4 belief, evolution 全 add）。

    现在: ① 先查 `health()`（= 真的发现了 embedding 模型）, 未就绪 → 返回 None
    （语义等价于原降级路径, 但**从源头**不给出注定抛错的 embed_fn）;
    ② 状态跳变时打一条可 grep 的日志, "在跑语义召回"还是"在跑词面兜底"一眼可判。
    未就绪**不永久缓存**（服务可能是后起的）: 每次 digest 重探一次
    （构造时一次 `GET /v1/models`; digest 是 ~分钟级低频路径, 可接受）。
    """
    global _EMBED_FN, _EMBED_REPORTED
    if _EMBED_FN is not None:                        # 已构造 → 直接复用
        return _EMBED_FN
    # 服务可能是后起的 → **不永久缓存"未就绪"**, 每次 digest 重探一次
    # （构造时一次 GET /v1/models, 10s 超时; digest 是分钟级低频路径）
    try:
        emb = LocalEmbedder()
        model = emb.model if emb.health() else ""
    except Exception as e:                           # noqa: BLE001 — 探测失败按未就绪
        emb, model, reason = None, "", f"probe_error({e})"
    else:
        reason = "" if model else "model_missing"
    if not model:                                    # 未就绪 → 上报跳变后交出 None
        if _EMBED_REPORTED is not False:
            logger.info(
                "digest_embed fn=none reason=%s fallback=keyword_candidates"
                "（语义召回不可用: 本机未加载 embedding 模型 → Round B 拿不到"
                "候选提示, 只能凭 LLM 自己判断）", reason)
            _EMBED_REPORTED = False
        return None
    _EMBED_FN = make_embed_fn(emb)
    if _EMBED_REPORTED is not True:
        # 带 base= : 配置面接通后"在跑哪个服务"不再靠猜（Qwen3 在 1235 / nomic 在 1234）
        logger.info("digest_embed fn=ok model=%s base=%s fallback=-",
                    model, emb.base_url)
        _EMBED_REPORTED = True
    return _EMBED_FN


def _interact_max(events: list, digested_seq: int) -> int:
    """本段互动 max seq（好感事件幂等键——affection 事件自身的 seq 会漂移,
    不能作键; 重复 digest 同区间时 interact_max 不变, 同 legacy 语义）。

    ⚠️ 判据 = `events.is_content_event`（非 marker / 非账目）—— 与 digest 的
    `new_events` **同一个谓词**。别在这里单独写 `type != ...`: `note` 那种账目
    一旦漏进来, 幂等键会被顶到一条没有内容的操作上。
    """
    return max(
        (e.seq for e in events
         if e.seq > digested_seq and is_content_event(e)),
        default=0)


def _name_aliases(profile: dict) -> tuple[str, ...]:
    """角色称喟别名（第一人称化用）—— **薄壳**: 真家搬去 `core/parsing/names.py`（N1）。

    保留本函数只为不改调用点签名; 新代码请直接用 `names.names_of(char).aliases`
    （或 `char_names(profile)`）。
    """
    return char_names(profile).aliases


def _ensure_char_entities(wstore: WikiStoreV2, char, character_id: str) -> None:
    """把 `self`(x0000) + `sensei`(x0001) 两个 entity 建出来（§3.0; §9-7 的落地）。

    **建的时刻**（用户 2026-09-23 裁决）: **第一次 digest 开始前** —— 也就是
    bond `vn_finish` 之后、digest 的 LLM 调用之前。接在 `_inject_brain(digest=True)`
    里（不是接在 `bond/api.py`）是为了**两个触发点都覆盖**: bond 闭环 **与** mmt 每 25 轮
    —— 只接 bond 的话, 第一次 digest 若是 mmt 触发的, entity 就还不存在。

    ⚠️ **必须在任何"自动建 entity"之前**（这就是"初始化"的含义）: 表里一个 entity 都没有时
    `store.next_id("x")` 返回的是 **x0001** —— 正是 sensei 的保留号（扫不到同前缀就从 1 起）。
    让它先占坑, 否则第 3 轮 `new_entity` 建的第一个人会**顶掉 sensei**（此后
    `ensure_entities` 按 id 判幂等 ⇒ sensei 永远不会被建）。

    ⚠️ 失败**只降级**（打一行 warning 继续 digest）。别让一次 entity 初始化把整轮消化带走:
    本函数被 `_inject_brain` 那个宽 except 罩着, 而它会直接 `return`。

    ⚠️ **只有真建了才写盘**（幂等 ⇒ 平时零写盘）。不写的话 entity 只活在内存里, 下一次
    digest 再建一遍 —— 盘上永远没有, 看起来"建了又没了"。

    ## 名字从哪来（2026-09-23 用户裁决: 玩家也走 config, 与角色对称）

    | entity | 主名 / 别名 | 谁写 |
    |---|---|---|
    | `self`(x0000) | `config/characters/{id}/profile.yml` | 作者（进 git） |
    | `sensei`(x0001) | `config/player/profile.yml` + `data/basic/player.json` | 作者 + 玩家自己 |

    ⚠️ **玩家档案读失败 = 报错, 不兜底**（用户 2026-09-23: *"静默兜底有点不负责任"*）:
    打一条 ERROR 再抛出去 ⇒ 本轮 digest 中止。代价是"config 坏一天就一天不消化",
    但那正是要的 —— 否则一个坏文件会永远不被人发现（水位不推进 ⇒ 修好即恢复;
    聊天/剧情/回放全不受影响, 它们不读这个文件）。
    """
    try:
        player = player_names()
    except Exception as e:                            # noqa: BLE001 — 记录后原样抛
        logger.error("[%s] 玩家档案读取失败 → 本轮 digest 中止（修好 config/player/"
                     "profile.yml 即恢复）: %s", character_id, e)
        raise
    try:
        # 延迟导入: `mmt_preset` 反向 import 本模块（它在顶层 `from core.mmt.engine import
        # MomoTalkEngine`）⇒ 模块级导入会成环。玩家名的唯一真源就是它（读写都在那儿,
        # webgui 的 `routers/name.py` 也走它）—— 注意它是**玩家自取名**, 只作别名。
        from core.mmt.mmt_preset import load_player_name
        n = names_of(char)
        made = ensure_entities(wstore, char_name=n.display, aliases=n.aliases,
                               sensei_name=player.display, sensei_aliases=player.aliases,
                               player_name=load_player_name())
        if made:
            wstore.save()
            logger.info("[%s] entity 初始化: %s（sensei=%s）", character_id,
                        ", ".join(made), player.display)
    except Exception as e:                            # noqa: BLE001 — 建/写盘失败才降级
        logger.warning("[%s] entity 初始化失败（照常 digest）: %s", character_id, e)


def load_note_segment(store: SessionStore, char_id: str, *,
                      wstore: WikiStoreV2 | None = None,
                      events: list | None = None) -> str:
    """随身笔记注入块（DESIGN_GRAPH_V4 §3.2; 0 LLM）—— **常驻层**, 每轮都在。

    它是**当前值不是事件**: 固定标题（"这是你自己记的, 不是别人给你的任务"）+
    固定顺序（约定 → 最近在想）, ⚠️ **不进按时间排序的记忆流**
    （`render_character_view` 那些带"（3 周前）"的条目是另一块）。

    与 wiki 视图**同源同频**（都在 digest / 开场这两处重建）, 所以两处调用点
    （`load_brain_segment` 给 bond 开场 · `_inject_brain` 给 MMT）拼的顺序一致:
    **出厂背景 → wiki 视图 → 笔记块**（放最后 —— 最贴近本轮对话的是"此刻"）。

    失败/空 → `""`（零注入不阻断, 宁缺勿错）; `wstore`/`events` 给了就复用
    （省一次读盘 —— 调用方手上本来就有）。
    """
    try:
        from core.brain.notes import render_note_block   # 局部导入（同 time_notes 那处）
        if wstore is None:
            wstore = WikiStoreV2(store.data_root, world_id=store.world_id,
                                 char_id=char_id)
        evs = store.events(char_id) if events is None else events
        # ⭐ N4a: refs 印**名字**不印编号 —— 名字要从图上取（渲染层纯函数零 IO）。
        titles = {n.id: n.title for n in wstore.all() if n.id and n.title}
        return render_note_block(wstore.notes_state(evs), now=datetime.now(),
                                 titles=titles)
    except Exception as e:                            # noqa: BLE001 — 注入绝不阻断
        logger.warning("笔记注入失败（不注）: %s", e)
        return ""


def load_brain_segment(store: SessionStore, char_id: str, char_name: str = "",
                       characters_root: str | Path | None = None) -> str:
    """角色注入段（0 LLM）——bond 开场/剧情引擎共用（webgui.bond/vn_cli）。

    2026-09-05 解耦定稿: 出厂记忆**不进 wiki**——注入段 = 出厂背景（experience.yml
    原文直注, render_background_experience, 与 personality 同为作者人设描述）+ 运行时
    wiki 记忆（render_character_view, digest 产物——空库为 ""）。wiki 只存玩家参与后
    的事; 背景经历是她的底色, LLM 扮演时自然内化。失败/空 → ""（零注入不阻断）。

    2026-09-13（T13 收口）: **VN 侧也接时间** ——
      ① 传 `story_now` 给 `render_character_view`（否则 VN 的记忆条目**没有"3 周前"**，
         而 MMT 有 —— 同一个大脑两套口径）
      ② 在段尾拼**时间注记**（剧情时间 + 现实间隔；**不给手机日期**——
         VN 无自由打字通道, 选项由 LLM 生成, 问不出"今天几号"）。
    """
    try:
        seg_parts: list[str] = []
        aliases: tuple[str, ...] = ()
        if characters_root is not None:
            try:
                ch = CharacterLoader(characters_root).load(char_id, strict=False)
                aliases = _name_aliases(ch.profile)
                seg_parts.append(render_background_experience(ch.experience))
            except Exception:                          # noqa: BLE001 — 背景取不到静默
                pass
        wstore = WikiStoreV2(store.data_root, world_id=store.world_id,
                             char_id=char_id)
        wiki_seg = render_character_view(wstore.all(), char_name=char_name,
                                         char_aliases=aliases,
                                         now=datetime.now(),
                                         graph=wstore.graph()) or ""
        _log_read_ledger(char_id)
        if wiki_seg:
            seg_parts.append(wiki_seg)
        # 随身笔记（§3.2）: 常驻层, 放在 wiki 视图**之后**（当前值比事件流更贴近此刻）
        note_seg = load_note_segment(store, char_id, wstore=wstore)
        if note_seg:
            seg_parts.append(note_seg)
        # 时间注记（VN: 不含手机日期）
        try:
            from core.worldtime import time_notes
            last_ts = ""
            evs = store.events(char_id)
            for e in reversed(evs):
                if getattr(e, "type", None) in ("mmt", "bond") and e.ts:
                    last_ts = e.ts
                    break
            seg_parts.extend(time_notes(last_ts=last_ts, include_phone=False))
        except Exception as e:                         # noqa: BLE001 — 注记绝不阻断
            logger.warning("VN 时间注记失败（不注）: %s", e)
        return "\n\n".join(p for p in seg_parts if p.strip())
    except Exception:                                # noqa: BLE001 — 宁缺勿错
        return ""


def _log_read_ledger(char_id: str) -> None:
    """读路径召回台账（V3-0, DESIGN_WIKI_V3 §3.5）——取走 render 层记下的桶统计。

    `render_character_view` 是纯渲染函数、不知道自己在为谁渲染, 所以由调用方
    （这里/`_inject_brain`）消费台账并补上 char_id。取走即清空, 不重复打点。
    渲染函数没被调用过（异常路径）→ 无声返回。
    """
    try:
        from core.brain import recall_ledger
        from core.brain.render import take_last_view_account
        acct = take_last_view_account()
        if not acct:
            return
        picked = sum(acct["buckets"].values())
        recall_ledger.log_read(
            char_id=char_id, total=acct["total"], picked=picked,
            buckets={k: str(n) for k, n in acct["buckets"].items()},
            # v2 的角色视图是静态分桶（不依赖向量）, 故 mode 如实标 off
            mode="off", surface="chara")
    except Exception as e:                           # noqa: BLE001 — 台账不阻断注入
        logger.debug("读路径台账失败: %s", e)

#: 滑动窗口默认轮数（每轮 = user+assistant 2 条消息; 40 轮 = 80 条消息）。
#: 玩家可配（引擎构造参数 history_rounds 传入; 设置页接入见 docs/DESIGN_MEMORY.md Step 1）
DEFAULT_HISTORY_ROUNDS = 40
# 会话存档走角色根目录（docs/archive/DESIGN_SAVE.md §三）: data/{char_id}/sessions/

# agent loop 参数
MAX_STEPS = 6          # 单轮动作步数上限（含 inspect 静默轮）
# 行协议（⑥-2d）的重试预算 —— 用户 2026-09-25 裁决"行级 1 次 + 形状级 2 次"
# （旧路径原来是 6 次**整轮**重发 = 最坏 6×4096 token 还什么都给不出）
LINE_REASK_MAX = 1     # ② 行级续写（只补缺失的操作行）
SHAPE_RETRY_MAX = 2    # ③ 形状级整轮重发（整段不是 JSONL）
TEMP = 0.8             # 与旧 send_message 一致
# max_tokens 真源 = llm/task_levels.py 形态 "mmt"（4096——动作 JSON + 对白,
# 推理模型需大 max_tokens, 勿改小; 2026-09-02 集中管理——本别名随真源联动）
MMT_MAX_TOKENS = task_levels_max_tokens("mmt")


@dataclass
class _LineOutcome:
    """行协议一轮办理的结果（`_run_lines` 内部用）。"""

    need_more: bool = False      # inspect 查完 → 这一轮还要再问一次（带着资料说话）
    fatal: str = ""              # 办不了 ⇒ 未交付时：行级续写（回灌）; 已交付时：只记账（⑥-3a）
    dropped: str = ""            # 丢了软操作行 ⇒ 记账 + 下一轮注记


#: 行办不了的原因文案 —— **唯一出处**（⑥-3a: 流式与批式两条路共用, 免得措辞漂;
#: 2026-09-27 之前批式的软/硬两处措辞不同: `X: note` / `X 这一行修不了 —— note`）。
_LINE_FAIL_PHASES = {
    "repair": "这一行修不了",
    "parse": "不合法",
    "exec-reject": "执行被拒",
    "exec-fail": "执行失败",
}


def _line_failure(action: str, phase: str, detail: str) -> str:
    """`f"{action} {阶段} —— {detail}"`（阶段表见 `_LINE_FAIL_PHASES`）。"""
    return f"{action} {_LINE_FAIL_PHASES[phase]} —— {detail}"


@dataclass
class _Planned:
    """**单行办理**的结果（`_plan_line`）：要么给出可交付的动作，要么给出原因。"""

    action: AgentAction | None = None
    why: str = ""                # 办不了的原因（`_line_failure` 统一措辞）
    message: str = ""            # 执行回执（inspect 的资料回灌要读它 —— AUDIT §B9）
# 羁绊剧情时机建议线（2026-09-02 v2 用户拍板: 引擎建议不拦截）: 距上次完整剧情
# ≥ SUGGEST_BOND_ROUNDS 轮 → 每轮注记主动建议发起剧情; 不足 → 只报事实+沉淀,
# 不拦（紧急场面 LLM 自行判断随时可触发, 见 momotalk_rules 触发专段）
SUGGEST_BOND_ROUNDS = 6

#: mmt 会话窗口 digest 间隔（蓝图 §3.1: 2026-09-02 用户拍板 N=25——纯 MMT 长聊
#: 每 N 轮后台消化一次, 节流而非精确窗口; bond 剧情闭环触发不变）
MMT_DIGEST_INTERVAL = 25

#: ⭐ N5（2026-09-29）: 每轮"你想起的事"的**查询文本长度上限**。
#: 只拿玩家这一句（多余的部分对相似度是噪声——真机一段闲聊 200 字里
#: 通常只有一句在说事）; 召回**不看**她的上一句, 因为"想起"是由**老师这句话**
#: 触发的那一下（她自己的回应还在生成中, 那时还不存在）。
RECALL_QUERY_CHARS = 200

#: digest 单次 LLM 调用的超时覆盖（per-call; 共享客户端的 60s 主对话超时会掐掉
#: high 档长考——digest 是后台任务, 放宽到 5min, 快速失败由 digest deadline 兜底）
DIGEST_LLM_TIMEOUT = 300.0


class MmtLoopError(Live2BeError):
    """MomoTalk agent loop 错误（步数耗尽等）。message 供调用方展示/重试。

    __str__ 自动产出 [engine.py][MmtLoopError][message]（C12a: 模块从 core/momotalk.py 搬到 core/mmt/engine.py）。
    """


# ============================================================================
# 会话数据结构辅助类
# ============================================================================


@dataclass
class Session:
    """对话会话的完整状态（可序列化）。"""
    character_id: str
    character_name: str
    history: list[dict[str, str]] = field(default_factory=list)
    created_at: str = ""

    def to_json(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({
                "character_id": self.character_id,
                "character_name": self.character_name,
                "created_at": self.created_at or datetime.now().isoformat(),
                "messages": self.history,
            }, fh, ensure_ascii=False, indent=2)


@dataclass
class TurnResult:
    """一轮 agent 对话的结果。

    steps      — 显示步骤序列（…打字指示 + 气泡）, 由 UI 依序渲染
    reply      — 完整对白（不含名字前缀, 历史存档用; 可能为空）
    action     — 最后一个动作名（mmt_chat / mmt_send_media / mmt_trigger_bond_story）
    payload    — 最后一个动作的干净 payload（GUI 可渲染媒体等）
    actions    — 动作列表视图 [{action, reply, payload}]（GUI 依序渲染媒体/切换, 2026-08-23）
    bond_story — True = 触发羁绊剧情成功, 调用方应切换到羁绊剧情模式
    error      — ok=False 时的原因（预留; 当前异常走 MmtLoopError）
    """
    ok: bool = True
    steps: list[DisplayStep] = field(default_factory=list)
    reply: str = ""
    action: str = ""
    payload: dict = field(default_factory=dict)
    actions: list[dict] = field(default_factory=list)
    bond_story: bool = False
    error: str = ""


# ============================================================================
# 引擎
# ============================================================================


class MomoTalkEngine:
    """MomoTalk 对话引擎 — 会话生命周期 + 全 JSON 动作 agent loop。"""

    def __init__(
        self,
        characters_root: str | Path,
        llm_client: LLMClient,
        interperson_path: str | Path | None = None,
        bond_progress: BondProgress | None = None,
        store: SessionStore | None = None,
        character_names: list[str] | None = None,
        history_rounds: int = DEFAULT_HISTORY_ROUNDS,
        task_card: bool | None = None,   # None = settings [promptkit].task_card（默认 true）
        embed_fn: Callable[[], Any] | None = None,
        #  ↑ ⭐ N5 接缝: "取语义后端"的**可换入口**（缺省 = 模块级 `_get_embed_fn`）。
        #    为什么要一个构造参数而不是让测试 patch 模块属性: `core.mmt.engine` 在
        #    `tests/core/test_split_safety.py` 的 TARGETS 里（将来可能被拆成包），
        #    那时 patch 模块属性会**静默失效**——那正是那条守门要拦的事。
        #    与 `digest_segment(embed_fn=…)` 同一个姿势: 后端由调用方给, 引擎不自选。
    ):
        self.char_loader = CharacterLoader(characters_root)
        self.llm = llm_client
        self.registry = build_mmt_registry()
        # 滑动窗口（轮数, 每轮 2 条消息）——玩家可配（docs/DESIGN_MEMORY.md Step 1）
        self._history_rounds = max(1, int(history_rounds))
        # 称呼名单（分饰多角预留）: None = 单人（默认当前角色 display_name）;
        # 未来一个 LLM 扮演多角色时注入多个名字（"你好，A / B / C——以下是行为规则…"）
        self._character_names = list(character_names) if character_names else None
        # 全局累计轮数统计（record_turn, 供外部偏好统计/注记——2026-09-02 v2:
        # 不再参与触发节奏, 节奏建议看 _bond_gap）
        # 2026-09-11 隔离修复（同 webgui 决策 #31 的同类问题）: 注入了 store 就
        # **跟着 store 的数据根**走——否则测试/CLI/多世界用临时 store 时, 轮数仍写
        # 真实 data/basic/bond_progress.json（真机上把 haruka 刷到 4550 轮）。
        self.bond_progress = bond_progress or BondProgress(
            getattr(store, "data_root", None))
        self.executor = MmtExecutor(characters_root, interperson_path)
        # 语义召回后端入口（N5）: 缺省 = 模块级探测（服务没起 → None → 词面降级）。
        # 存成**实例属性**（不是模块全局）——测试/实验可以整只换掉，不用碰模块。
        self.embed_fn: Callable[[], Any] = embed_fn or _get_embed_fn
        # 事件流存档（docs/archive/DESIGN_SAVE.md §4）: store 注入 + attach_session 后,
        # 每轮 agent_turn 落 mmt 事件 + 会话内轮数; None = 不记录（向后兼容）
        self._store = store
        self._session_id: str = ""
        self._session_rounds: int = 0
        # 距上次完整 bond 剧情的 MMT 轮数（2026-09-02 决策字段）:
        # 持久化在 worlds/{world}/characters/{char}/progress.json（rounds_since_bond,
        # 断线/重启继续累计）——供**时机建议注记**（v2: 不再是硬门槛, 见
        # SUGGEST_BOND_ROUNDS / _bond_progress_note）; 完整剧情结束清零。
        # 无 store → 镜像会话轮数（不持久）。
        self._bond_gap: int = 0

        self._current_char: DynamicCharacter | None = None
        self._system_prompt: str = ""
        self._brain_injection: str = ""   # 角色记忆注入段（动态拼装; digest 后台原子替换）
        self._history: list[dict[str, str]] = []
        self._trace: list[dict] = []      # 最近一轮的完整动作轨迹（追溯/调试）
        self._random_cooldowns: dict = {}  # 随机事件冷却状态（per 引擎实例, 不跨会话串）
        self._digest_lock = threading.Lock()  # 同引擎 digest 串行（async_digest 后台线程）
        # 本回合任务卡（DESIGN_PROMPTKIT §4）: 构造参数 > settings [promptkit].task_card
        # （默认 true; false = 现网无卡行为, A/B 对照用）——start_session 时定值
        self._task_card_override: bool | None = task_card
        self._task_on = True

        # 行协议丢掉软操作行（如"图没发出去"）→ **下一轮**注记念一次（自清）
        self._line_notes: list[str] = []

    # ------------------------------------------------------------------
    # 公共 API — 会话生命周期
    # ------------------------------------------------------------------

    def start_session(self, character_id: str) -> str:
        char = self.char_loader.load(character_id)

        # 盒A v2（DESIGN_PROMPTKIT §4.1）: 命名块清单装配——称呼行归位盒顶
        # （身份先行; 此前夹在 environment 与 rules 之间, 2026-09-07 用户拍板）。
        # 玩家名不注入——学生不会直呼玩家自定义名（一直称呼"老师"）; 名字只做
        # 系统显示（终端提示符 / 菜单 / 存档标识）, 见 mmt_preset 玩家名系统。
        sp = build_box("mmt", BlockContext(
            char=char,
            names=self._character_names or [char.display_name],
            greeting_suffix="——以下是你的行为规则，请严格遵守：",
            # ⑥-2e: 行流契约（`一行一条 JSON`）——取代 2026-09-02 的 messages 消息流。
            # 动作表由 registry **运行时**渲染（新增动作自动进 prompt）。
            schema=build_line_schema(self.registry),
            interperson_path=self.executor.interperson_path,
        ))

        self._current_char = char
        self._system_prompt = sp
        self._history = []
        self._trace = []
        self.executor.set_current_character(char)   # inspect/trigger 依赖会话角色
        if self._task_card_override is None:        # 卡开关定值（会话内不变）
            self._task_on = task_card_enabled()
        else:
            self._task_on = bool(self._task_card_override)

        logger.info("新会话: %s (%s)", character_id, char.display_name)
        return char.display_name

    def save_session(self, path: str | Path | None = None) -> Path:
        if path is None:
            # 角色根目录（docs/archive/DESIGN_SAVE.md §三）: data/{char_id}/sessions/{char}_{ts}.json
            char_dir = Path("data") / self._char_id / "sessions"
            char_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            path = char_dir / f"{self._char_id}_{ts}.json"
        Session(
            character_id=self._char_id,
            character_name=self._current_char.display_name if self._current_char else "",
            history=list(self._history),
            created_at=datetime.now().isoformat(),
        ).to_json(Path(path))
        logger.info("会话已保存: %s (%d 条消息)", path, len(self._history))
        return Path(path)

    def attach_session(self, session_id: str) -> None:
        """绑定事件流会话（docs/archive/DESIGN_SAVE.md §4）: main 层 store.create 后调用。

        绑定后每轮 agent_turn 落 mmt 事件 + 会话内轮数（store 已注入）。
        2026-09-02: 触发门槛计数（_bond_gap）从持久 progress.json 恢复
        （rounds_since_bond——断线/重启继续累计, 不从 0 开始; 完整 bond
        剧情结束才清零, 见 bond_completed）。

        **2026-09-13（审计 E11）**: `_session_rounds` 同样**从事件流恢复**, 不再
        无条件归零。它有两个身份: ① mmt 窗口 digest 的触发计数
        （`_maybe_mmt_digest`: `>= 25` 且 `% 25 == 0`）; ② `want_to_speak` 的
        冷却键（`core/random_events` 的 `_cooldowns` 用它当"当前轮号"）。
        原先每次 `attach_session` 归零 → **前端每次刷新/切页（`open_session`）
        都让 25 轮窗口从头再数一遍**, 页面常刷新时 digest 几乎永不触发; 冷却键
        同样失效（"冷却 6 轮"变成"冷却 >=6 次刷新"）。现在按**本会话已落库的
        mmt 轮数**恢复, 与 `_bond_gap` 的持久化口径一致。
        """
        self._session_id = session_id
        char_id = self._current_char.character_id if self._current_char else ""
        self._session_rounds = self._count_session_turns(char_id)
        if self._store is not None and char_id:
            try:
                self._bond_gap = self._store.read_bond_gap(char_id)
            except Exception as e:               # noqa: BLE001 — 读失败降级 0
                logger.warning("progress 读取失败（门槛计数从 0 起）: %s", e)
                self._bond_gap = 0
        else:
            self._bond_gap = 0

    def _count_session_turns(self, char_id: str) -> int:
        """本会话已落库的 mmt 轮数（`_session_rounds` 的重启恢复值）。

        每成功一轮落一条 `mmt_chat` 事件（`_deliver_line` 逐行写）,
        故"条数"即"轮数"（invariant 有单测钉住）。无 store / 无会话 / 读失败
        → 0（宁缺勿错: 从 0 起只是窗口晚一点, 不阻断对话）。
        """
        if self._store is None or not char_id or not self._session_id:
            return 0
        try:
            return sum(
                1 for e in self._store.events(char_id, self._session_id)
                if not getattr(e, "is_marker", False)
                and getattr(e, "type", "") == "mmt"
                and getattr(e, "subtype", "") == "mmt_chat")
        except Exception as e:                   # noqa: BLE001 — 读失败降级 0
            logger.warning("mmt 轮数恢复失败（从 0 起）: %s", e)
            return 0

    def bond_completed(self) -> None:
        """完整 bond 剧情结束回调（vn_exit completed=True 收尾链调用, 2026-09-02
        用户拍板: vn_exit 才清零——只有完整演过的剧情才重新计时）:

        距上次剧情计数清零（供时机建议注记重新数; v2 起不是门槛——只是建议线
        的基准: 演完后注记重新报"沉淀中", 防止 LLM 无节奏连开剧情）。
        """
        if self._current_char is None:
            return
        char_id = self._current_char.character_id
        self._bond_gap = 0
        if self._store is not None:
            try:
                self._store.write_bond_gap(char_id, 0)
            except Exception as e:               # noqa: BLE001 — 写失败降级（内存已清）
                logger.warning("progress 清零写失败: %s", e)

    def _inject_brain(self, character_id: str, session_id: str = "", *,
                      digest: bool = False) -> None:
        """Brain 接线（brain, 2026-09-02 切换; 2026-09-05 解耦）: 注入角色 wiki → 注入段。

        角色记忆 = per-char 单库（soul/wiki.jsonl——SessionStore session_id 不参与
        路径）; 注入段动态拼装（_brain_injection 原子替换）——digest 后台完成后
        **下一轮自动生效**, 不追加防重复注入, 跨线程零锁。

        2026-09-05 解耦: 出厂记忆不进 wiki——注入段 = 出厂背景（experience.yml
        原文直注, render_background_experience）+ 运行时 wiki（digest 产物）;
        **主进程不再调用 seed_from_config**（出厂改编链模块化, 可选调用）。

        digest=False（resume）: 只读注入。
        digest=True（async_digest 后台线程, _digest_lock 串行）: digest_segment
        （Round A 记录 + Round B 组织）→ 好感结算（affection 事件, 幂等键
        interact_max）→ 注入刷新。（⚠️ 全景轮已于 2026-09-29 / N4a 退役 —— note 的
        写者收成一个: `promise` 归 R4、`on_mind` 归 L1。）
        失败静默降级——wiki 是派生视图, events.jsonl 唯一真源, 可重算。
        """
        store = self._store
        if store is None or self._current_char is None:
            return
        char = self._current_char
        anchor = yaml_to_prompt(
            {**char.personality, **char.knowledge}, "角色人设（锚点）")
        try:
            seg_parts: list[str] = []
            bg = render_background_experience(char.experience)
            if bg:
                seg_parts.append(bg)
            wstore = WikiStoreV2(store.data_root, world_id=store.world_id,
                                 char_id=character_id)
            # 本段事件（digest 与笔记注入共用 —— 提到 if 之前, 两条路都要）
            events = store.events(character_id)
            if digest:
                # entity 初始化（§3.0 / §9-7）: **第一次 digest 开始前** —— 必须在下面
                # 任何"新建 entity"之前跑, 见 `_ensure_char_entities` 的撞号警告。
                _ensure_char_entities(wstore, char, character_id)
                interact_max = _interact_max(events, wstore.digested_seq)
                # 编码时好感快照（§3.3.3）: 本段**开始之前**的累计好感标量。
                # 按 digested_seq 过滤（不是 interact_max）——只算**已消化**的部分,
                # 即"写这些记忆的那一刻她对玩家多少好感"。
                # None = 本段前没有任何 affection 事件 → 字段不落库（与 0.0 区分）。
                aff_prior_d = load_affection_from_events(
                    events, up_to_seq=wstore.digested_seq)
                aff_prior = (Affection(exp=int(aff_prior_d.get("exp", 0) or 0))
                             .to_scalar()) if aff_prior_d else None
                # 角色情绪标尺（§3.3.2）: 作者手写的 per 键强度语义。
                # 由调用方给而不是 brain 层自己找——资产布局是 media 的事。
                try:
                    from core.media import assets_root, load_emotion_lexicon
                    _lex_dir = (assets_root() / "illustration"
                                / (char.character_id or character_id) / "default")
                    emotion_lex = load_emotion_lexicon(_lex_dir)
                except Exception as e:                    # noqa: BLE001 — 宁缺勿错
                    logger.warning("情绪词表加载失败（本轮不注标尺）: %s", e)
                    emotion_lex = {}
                res = digest_segment(wstore, self.llm, events,
                                     character_prompt=anchor,
                                     embed_fn=_get_embed_fn(),
                                     llm_timeout=DIGEST_LLM_TIMEOUT,
                                     aff_at_encoding=aff_prior,
                                     emotion_lexicon=emotion_lex)
                if not res.ok:
                    logger.warning("digest 未完成 (%s): %s", character_id,
                                   " | ".join(res.errors))
                else:
                    if res.affection_delta != 0 and interact_max:
                        # 2026-09-13: 判据由 `> 0` 改为 `!= 0`——负 delta（关系恶化）
                        # 同样要落事件, 否则"能变坏"只存在于数值层、进不了真源。
                        self._write_affection_event(store, character_id, events,
                                                    interact_max, res.affection_delta)
                    if res.notes_ops:
                        # R4 收口的 note 操作（§8）: **整批 ok 之后**才 append ——
                        # 事件不可撤销, 提前写就把"整批回滚"变成了半截状态。
                        events = self._write_note_ops(store, wstore, character_id,
                                                      events, res.notes_ops)
            wiki_seg = render_character_view(
                wstore.all(),
                char_name=char.display_name or "",
                char_aliases=_name_aliases(char.profile),
                # 防失忆注记（T3）: 给"现在" → 每条 episode 前置"（3 周前）"。
                # 2026-09-17（ESSAY §10）: 年龄按**现实日期**算（node.ts），
                # 不再读剧情游标 —— 故这里给的是壁钟，不是 `wstore.clock()`。
                now=datetime.now(),
                # 边表（G3）: experience 的 count = supports 入边数, 不再走节点字段
                graph=wstore.graph())
            _log_read_ledger(character_id)               # V3-0 读路径台账
            if wiki_seg:
                seg_parts.append(wiki_seg)
            # 随身笔记（§3.2）: 常驻层, 放在 wiki 视图**之后**（当前值比事件流更贴近此刻）。
            # ⚠️ 写完一条 note 之后要**重建这一段**（`_brain_injection` 是缓存的串）。
            note_seg = load_note_segment(store, character_id,
                                         wstore=wstore, events=events)
            if note_seg:
                seg_parts.append(note_seg)
            self._brain_injection = "\n\n".join(seg_parts)
        except Exception as e:                       # noqa: BLE001 — 宁缺勿错
            logger.warning("brain 注入失败 (%s): %s", character_id, e)

    def _write_note_ops(self, session_store: SessionStore, wstore: WikiStoreV2,
                        character_id: str, events: list, ops: list[dict]) -> list:
        """把 note 操作写进真源 + 刷缓存（**先真源后缓存**）—— 返回重读后的事件流。

        两个写者共用这一处（R4 的收口操作 / 全景轮的那条 `rewrite`）:
        顺序是**正确性**而不是风格 —— `notes.json` 只是派生缓存,
        **事件流才是真源**; 反过来写会出现"本子上有、事件流没有", 而那条笔记
        没有人能重建它（§3.2）。

        失败静默降级（宁缺勿错）: 写不进去 = 这次没记上, 本子留旧版, 绝不阻断消化;
        返回值保持调用方原先的那份 `events`（没变就别假装变了）。
        """
        try:
            from core.brain.notes import note_event   # 局部导入（同笔记注入那处）
            for op in ops:
                session_store.append_event(character_id, "", note_event(op))
        except Exception as e:                       # noqa: BLE001 — 写失败 = 这次没记上
            logger.warning("note 操作写入失败（%s; 本子留旧版）: %s", character_id, e)
            return events
        events = session_store.events(character_id)  # 真源已变 → 重读（注入块要用新的）
        try:
            wstore.save_notes(wstore.notes_state(events))
        except Exception as e:                       # noqa: BLE001 — 只是缓存, 真源是事件流
            logger.warning("笔记缓存写入失败（事件流已是真源, 下次现折）: %s", e)
        return events

    def _last_seen_ts(self) -> str:
        """她上次与老师互动的**壁钟时间**（`§4.11` 的"现实间隔"数据源）。

        取事件流里最后一条**互动**事件（mmt/bond）的 `ts` —— 数据现成, 不新增存储。
        没有 → `""`（注记整行跳过, 不编一个"很久没见"）。

        ⚠️ 刻意用 **③ 壁钟**（不是 ① 剧情时间）: 这里要回答的是
        "**玩家**隔了多久才回来", 那是现实世界的事。两条时钟各答各的。
        """
        if self._store is None or not self._current_char:
            return ""
        try:
            evs = self._store.events(self._current_char.character_id)
        except Exception:                            # noqa: BLE001 — 注记绝不阻断
            return ""
        for e in reversed(evs):
            if getattr(e, "type", None) in ("mmt", "bond") and e.ts:
                return e.ts
        return ""

    @staticmethod
    def _write_affection_event(store: SessionStore, character_id: str,
                               events: list, interact_max: int, delta: int) -> None:
        """好感事件写（真源 events.jsonl; 幂等键 interact_max——同 legacy 语义:
        重复 digest 同区间 → digested_seq 相同 → 已存在则跳过）。"""
        already = any(
            e.type == "affection"
            and int((e.payload or {}).get("digested_seq", 0) or 0) >= interact_max
            for e in events)
        if already:
            return
        try:
            store.append_event(character_id, "", make_event(
                "affection", "digest",
                {"delta": delta, "digested_seq": interact_max}))
        except Exception as e:                       # noqa: BLE001 — 写失败降级
            logger.warning("affection 事件写入失败: %s", e)

    def async_digest(self) -> None:
        """异步消化本角色线未消化事件（后台线程, 不阻塞对话/UI）。

        触发点: ① bond 剧情闭环后（语义完整段, story_end 收尾）;
        ② mmt 会话每 N=25 轮（蓝图 §3.1, 纯 MMT 长聊窗口消化——节流非精确窗口,
        剧情中 in_vn/in_memorial 不触发, 由 _maybe_mmt_digest 保护）。
        digest 增量幂等（digested_seq 推进）——失败/跳过零损失; resume 只注入不消化。
        """
        if self._store is None or not self._session_id:
            return
        char_id = self._current_char.character_id if self._current_char else ""
        if not char_id:
            return
        threading.Thread(
            target=self._run_digest, args=(char_id, self._session_id), daemon=True,
        ).start()

    def _maybe_mmt_digest(self) -> None:
        """mmt 窗口触发检查（每轮落盘后调用; 蓝图 §3.1 N=25）:

        未到窗口 / 剧情中（in_vn/in_memorial——bond 闭环自会消化）→ 不触发。
        触发 → async_digest（后台; digest 增量, 无新增 0 调用, 撞车锁内空跑无害）。
        """
        if self._session_rounds < MMT_DIGEST_INTERVAL:
            return
        if self._session_rounds % MMT_DIGEST_INTERVAL != 0:
            return
        store = self._store
        char = self._current_char
        if store is None or char is None or not self._session_id:
            return
        try:
            st = session_status(store.events(char.character_id))
        except Exception:                            # noqa: BLE001 — 读失败不触发
            return
        if st.get("in_vn") or st.get("in_memorial"):
            return                                   # 剧情中: bond 闭环自会消化
        self.async_digest()

    def _run_digest(self, char_id: str, session_id: str) -> None:
        """后台线程: digest（同引擎串行锁）→ 提炼 + 好感结算（写 affection 事件）。"""
        try:
            with self._digest_lock:
                self._inject_brain(char_id, session_id, digest=True)
        except Exception as e:                           # noqa: BLE001
            logger.warning("异步 digest 失败 (%s/%s): %s", char_id, session_id, e)

    def resume_session(self, character_id: str, session_id: str) -> dict:
        """从事件流恢复会话（docs/archive/DESIGN_SAVE.md §4.2/§六）: 重建 system + history, 继续 MMT。

        store.resume → events → render_events（mmt 事件 → user/assistant 对,
        与引擎 history 同格式 `[动作名] 回复`）→ 灌入 _history → attach_session。
        ended 会话拒绝恢复（宁缺勿错）; in_vn/in_memorial 中断 → 仍恢复 MMT 上下文
        （VN/纪念中断的现场恢复后续支持, 玩家可重新触发 bond）。

        Returns: {"status": dict, "history_len": int, "display_name": str}
        """
        if self._store is None:
            raise RuntimeError(err("NotBound", "未绑定事件流存储, 无法恢复会话"))
        data = self._store.resume(character_id, session_id)
        status = data["status"]
        if status["ended"]:
            raise RuntimeError(err("ResumeRejected", "会话已结束, 不能恢复"))
        self.start_session(character_id)                  # 重建 system（人设/世界观/schema）
        if self._store is not None:                       # Brain 接线（brain）:
            self._inject_brain(character_id, session_id)  # 恢复时只注入已有 wiki（不消化——
                                                          # digest 由 async_digest 触发: bond 闭环 / mmt N=25 轮）
        # 统一上下文窗口（2026-09-05, DESIGN_CONTEXT_WINDOW）: window_messages 按
        # 叙事单元数装填（bond 句段按行占窗, 长场景自然挤旧）; 预算 = rounds × 3
        # （默认 40 轮 → 120 单元, 与板块定稿一致; history_rounds 保留为可配语义）;
        # 废弃段过滤（2026-09-07, maintenance）: 被新章压掉的中断段不进上下文
        from core.session.maintenance import exclude_abandoned
        self._history = window_messages(
            exclude_abandoned(data["events"]),
            max_units=self._history_rounds * 3)
        self.attach_session(session_id)
        return {
            "status": status,
            "history_len": len(self._history),
            "display_name": self._current_char.display_name if self._current_char else "",
        }

    def clear(self) -> None:
        self._current_char = None
        self._system_prompt = ""
        self._history = []
        self._trace = []
        self.executor.set_current_character(None)
        self._session_id = ""
        self._session_rounds = 0

    # ------------------------------------------------------------------
    # 公共 API — 对话（全 JSON 动作 loop）
    # ------------------------------------------------------------------

    def agent_turn(
        self,
        user_input: str,
        *,
        system_note: str | None = None,
        record_input: bool = True,
        task_kind: str = "",          # 本回合任务卡 kind（"" → 域默认 chat）; 收尾轮传 "wrapup"
        now: datetime | None = None,  # 本轮"现在"（None → 读壁钟）; 时间注记**共用**它
    ) -> TurnResult:
        """一轮 agent 对话：LLM 输出**行流**, 逐行办理, 直到用户可见输出。

        行协议（⑥-2e 起）: 一行一条 JSON, 任意交错——
            {"text": "话1"}                              # 消息行（一条行 = 一个气泡）
            {"action": "mmt_send_media", "payload": …}   # 操作行（不上屏）
            {"text": "话2"}
        消息行 → 隐含 `mmt_chat`（事件流/历史/渲染零改动）; 操作行只承载需要引擎
        介入的事（send_media / inspect / trigger）。

        轮内（`_turn_lines`, 上限 MAX_STEPS 步）:
            LLM 决策（**裸文本**）→ 行解析（坏行丢行记账）→ 四阶段办理
            （① 自愈 ② 组合校验 ③ parse+执行 ④ **保持行序**交付）
            → 逐行落事件 + 记历史 → 全部办完 → 轮数 +1（一次 agent_turn = 一轮）
        兜底三段: ① 引擎自愈（零 LLM）② 行级续写（只收控制行; ≤LINE_REASK_MAX）
        ③ 形状级整轮重发（≤SHAPE_RETRY_MAX）; 耗尽 → MmtLoopError。

        system_note: 本轮额外系统注记（只进 LLM context, 不入历史）。
        record_input: False 时不把 user_input 记入历史（自动收尾等系统触发轮）。
        """
        if self._current_char is None:
            raise RuntimeError(err("NotInSession", "尚未开始会话"))

        self._trace = []
        # 每轮动态尾（DESIGN_PROMPTKIT §2）: 唯一装配入口 round_messages——
        # system(盒A+brain段) → history → 注记们（P16 进度 / P17 system_note /
        # P18 随机）→ task 卡 → user。注记/卡只进 LLM context, 不入历史。
        brain = (self._brain_injection or "").strip()
        notes: list[str] = [self._bond_progress_note()]    # P16 羁绊进度参考（软门槛）
        # P17 时间注记（§4.11）—— 剧情时间 + 现实间隔 + 手机日期。
        # ★ 三行**互不参与判定**（不进 det/age/召回），只给 LLM 写作与答题的素材。
        # ★ "手机上的日期"给归因（她是掏手机看, 不是知道现实世界）+ 使用边界
        #   （问起才引用）—— 否则模型会主动提日期、破第四面墙。
        # 位置: P16 之后、P18/task 卡之前（时间事实比随机事件更基础）。
        # ⚠️ `wstore` 提到 try 外面: 下面 P19 的召回要**复用它**（同一个"这一轮的 wiki
        #    视图"）—— 每轮多读一遍 wiki.jsonl 是白花的钱, 而且两份快照可能不同源。
        #    `WikiStoreV2` 定义了 `__len__`（节点数）⇒ **空库是假值**,
        #    所以判空一律 `is not None`, 绝不能写 `if wstore`（真机踩到过）。
        wstore: WikiStoreV2 | None = None
        try:
            from core.worldtime import realtime_notes, time_notes
            # ★ **一次取一个"现在", 三条注记共用**（2026-09-17 接线时踩到）:
            #   若让 `time_notes` 与 `realtime_notes` 各自读壁钟, 它们会落在两个
            #   时刻上 —— 探针里就出现过"【手机上的日期】9月19日"与
            #   "（手机日历上标着：圣诞节）"同轮并存的画面。同一个 prompt 里
            #   两条时间事实不同源, 正是 `ESSAY §5.2` 记的那个坑的形状。
            #   `now` 形参是这条纪律的出口（同 `age_days(*, now)` 不留默认值）:
            #   生产传 None（读壁钟）, 测试传一个钉死的时刻。
            _now = now or datetime.now()
            if self._store is not None:
                wstore = WikiStoreV2(self._store.data_root,
                                     world_id=self._store.world_id,
                                     char_id=self._current_char.character_id)
            # ⚠️ `include_phone` 必须跟着 **store 有无**走 —— 它是壁钟派生的
            # （不需要游标, 所以写死 True 会让"无 store 的用例"也注入手机日期,
            #  与"无 store 不注时间"的纪律矛盾。真机/测试都踩到过。）
            for _n in time_notes(last_ts=self._last_seen_ts(), now=_now,
                                 include_phone=wstore is not None):
                notes.append(_n)
            # ★ 特殊日期（现实日历②, 2026-09-17 接入）—— 同一个纪律: 跟着 store 走。
            # 只在少数日子产注记（其余轮返回 []）; 调用即记账（台账写了 `fired`,
            # 所以"LLM 调用失败也不重复注"——这正是"调用即记账"要买的东西）。
            # ⚠️ 它是**动态注记**不是**盒块**: 盒在 start_session 一次拼死、每轮
            #   逐字节复用, 而这条只在那一天出现 —— 进盒就会破前缀稳定。
            # ⚠️ char_id 必须是 **slug**（台账按它分桶）, 不是 display_name。
            if self._store is not None:
                for _n in realtime_notes(self._current_char.character_id,
                                         self._store.world_dir(), now=_now):
                    notes.append(_n)
        except Exception as e:                       # noqa: BLE001 — 注记绝不阻断
            logger.warning("时间注记失败（本轮不注）: %s", e)
        # ⭐ P19「你想起的事」（**N5**, 2026-09-29）—— 引擎每轮摆 1~2 条旧 episode。
        # 两个"为什么"（别改回去）:
        #  ① **为什么进 notes 不进 brain**: 这一段的查询是**玩家这一句** ⇒ 每轮都不同;
        #     拼进 system（盒 + brain 的稳定前缀）就逐轮破上下文缓存 —— 而"稳定前缀"
        #     是 §9 体感主线的地基。notes 全部落在 history **之后**（tail.py 的不变式）。
        #  ② **它排在时间注记之后、task 卡之前**: 时间事实（"现在几点/今天几号"）
        #     比"我想起了什么"更基础; 而 task 卡是目标层, 恒定压在所有材料之后。
        # 宁缺勿错: 召回失败/空库/没有一条像 ⇒ 不注（少一段上下文, 剧情照走）。
        try:
            _recall = self._recall_note(user_input, _now, wstore=wstore)
            if _recall:
                notes.append(_recall)
        except Exception as e:                       # noqa: BLE001 — 召回绝不阻断对话
            logger.warning("每轮召回失败（本轮不注）: %s", e)
        if system_note:                                     # P17 本轮系统注记
            notes.append(system_note)
        if self._store is not None:          # P18 随机事件（概率性, soft——低频惊喜）
            from core.random_events import fire_event
            rand_note = fire_event(
                "want_to_speak",
                {"round": self._session_rounds, "_cooldowns": self._random_cooldowns})
            if rand_note:
                notes.append(rand_note)
        if self._task_on:                    # task 卡（目标层, 末位——离生成最近）:
            # kind = 调用方显式（wrapup 收尾轮）或域默认 chat; 模板缺失静默跳过
            card = task_card(
                "mmt", task_kind,
                char=self._current_char.display_name if self._current_char else "")
            if card:
                notes.append(card)
        notes.extend(self._take_line_notes())     # 行协议：上一轮丢掉的软操作行（自清）
        messages = round_messages(
            system=self._system_prompt, history=self._history,
            notes=notes, brain=brain, user=user_input)

        # 行协议（⑥-2e 起唯一路径）: 一行一条 JSON → 逐行交付 + 逐行落库 + 三段式兜底
        return self._turn_lines(messages, user_input, record_input=record_input)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 行协议（唯一路径）—— 一行一条 JSON: 逐行交付 / 逐行落库 / 三段式兜底
    #
    # 契约: `docs/DESIGN_STREAM_CONTRACT.md` §1（六条）/ §2（两域对照）/ §4（兜底分级）/
    # §10.3（三个注入点）。要点:
    # · 交付单元 = **行**：text 行 = 一个气泡，解析出来就落事件（C4"行交付即 append"）；
    # · 操作行**先自愈再校验**（自愈必须早于 `registry.parse` —— §10.2 B5 发现②）；
    # · **没交付之前，有硬问题就不交付**（`inspect` 混排时绝不先把话放出去）；
    # · ⭐ **inspect 查到的资料回灌后继续这一轮**（AUDIT §B9 的洞：旧路径把它丢了）；
    # · 重试三段：① 自愈（零 LLM 成本）② 行级续写（只收控制行）③ 形状级整轮重发。
    # · **⑥-3a 流式交付**：`chat_full(on_chunk=…)` 边收边解析，内容行**一行前瞻**交付
    #   （下一行到达时上屏），独占行攒到块尾——见 `_turn_lines` 的表格。
    # ------------------------------------------------------------------

    def _take_line_notes(self) -> list[str]:
        """取走（并清空）上一轮行协议留下的软注记——只念一次（同 VN 的 `_pending_feedback`）。"""
        notes, self._line_notes = self._line_notes, []
        return notes

    def _recall_note(self, user_input: str, now: datetime,
                     *, wstore: WikiStoreV2 | None = None) -> str:
        """本轮的「你想起的事」段（**N5**）—— 空串 = 不注入（宁缺勿错）。

        ⭐ **为什么候选必须由引擎摆**（`DESIGN_MMT_NEW_ACTION §3.7`）:
        她是"想起来"的那一方, 但**摆哪几条**是引擎的活 —— 否则她要么凭印象瞎指
        （引用了不存在的事 ⇒ 锚点校验直接丢）, 要么每轮多花一次调用去查
        （那是 `look` 的活, 固有成本 2 次主调用, 只该在她"必须知道才能说下一句"时用）。

        ⭐ **这一步今天还多干一件事: 把标题送到她眼前**（`_memory_line` 的 `【…】`）。
        在 N5 之前 `episode.title` **从来没进过任何注入面** —— 而引擎与她的唯一
        地址空间就是标题（编号退回引擎内部）。她要做的动作是"指一下是哪条"
        （`{"noticed": "苔藓的约定"}`）, 指不到看不见的名字。

        ⚠️ **embed_fn 走 `self.embed_fn`**（构造参数优先, 缺省 = 模块级探测;
        与 digest 同一个后端、同一个降级）: 服务没起 ⇒ 自动退词面（tags/Dice）,
        **不是不召回**; 代价是命中率下降（真机实测: 8 句里 3 句的命中依赖语义）,
        真机数字出来再定要不要补"最近 N 条"兜底（`docs/TODO.md` N12）。

        `wstore`: 调用方手里这一轮的 wiki 视图（复用 —— 每轮重读一遍是白花的钱）。
        """
        if self._store is None or self._current_char is None:
            return ""
        query = (user_input or "").strip()[:RECALL_QUERY_CHARS]
        if not query:
            return ""
        char = self._current_char
        if wstore is None:
            wstore = WikiStoreV2(self._store.data_root, world_id=self._store.world_id,
                                 char_id=char.character_id)
        mode: list[str] = []
        nodes = recall_episodes(wstore, query=query, embed_fn=self.embed_fn(),
                                mode_out=mode)
        if not nodes:
            return ""
        seg = render_recall_block(nodes, char_name=char.display_name or "",
                                  char_aliases=_name_aliases(char.profile), now=now)
        # 台账（可 grep）: 摆了几条 / 多少字 / 走的哪条通道 / 摆了谁（**标题**——
        # 编号是她看不到的东西, 排查时要看的是她看到的那个串）。
        logger.info("mmt_recall %s/%s eps=%d chars=%d mode=%s titles=%s",
                    char.character_id, self._session_id, len(nodes), len(seg),
                    mode[-1] if mode else "-",
                    " / ".join(n.title or n.id for n in nodes))
        return seg

    def _line_candidates(self) -> dict[str, tuple[str, ...]]:
        """自愈用的角色候选表：角色注册表（id + 显示名）+ 关系记录（interperson）的键。

        读失败一律降级（少几个候选 = 少救回几个写歪的 id, 不影响主链）。
        """
        ids: list[str] = []
        try:
            ids = list(self.char_loader.list_characters())
        except Exception as e:                       # noqa: BLE001 — 候选表读不到就少救几个
            logger.warning("角色注册表读取失败（归一化候选减少）: %s", e)
        names: dict[str, list[str]] = {}
        for cid in ids:
            try:
                names[cid] = [self.char_loader.load(cid).display_name]
            except Exception:                        # noqa: BLE001 — 单个角色坏了不拖累别人
                continue
        try:
            ids.extend(load_interperson(self.executor.interperson_path))
        except Exception as e:                       # noqa: BLE001 — 关系记录可缺
            logger.warning("关系记录读取失败（归一化候选减少）: %s", e)
        return build_candidates(dict.fromkeys(ids), names)

    def _turn_lines(self, messages: list[dict], user_input: str, *,
                    record_input: bool) -> TurnResult:
        """行协议一轮（**⑥-3a 流式交付**）：`一行一条 JSON` → **边收边判边发** + 三段式兜底。

        | 行的类别 | 办理时机 | 为什么是这个时机 |
        |---|---|---|
        | 内容行（消息行 / `send_media`） | **一行前瞻**：下一行到达时交付 | 有前瞻才收得回"下一行其实是 `inspect`"（见下） |
        | 独占行（`WHOLE_TURN_ACTIONS`） | **块尾**（整轮写完） | 合法性取决于"同一轮还有没有别的行"，早判必错判 |
        | ⭐ 想起行（`{"noticed": …}`） | **收在手里, 轮末统一落账** | 它是**账目不是内容**（不上屏/不独占/不调 LLM）——见 `_log_notices` |
        | 坏行 / 空轮 / 形状 | 块尾 | 同理：形状要整段才看得出来 |

        ⭐ **一行前瞻**（与 VN 切板同款手法）: 内容行**不立刻**交付，压到**下一行**解析
        出来再交付——因为下一行可能是 `inspect`（静默推理轮），而那一轮**一句话都不该
        上屏**（"没查到就先答"）。是 `inspect` ⇒ 手里那行丢掉、本轮内容行一律不交付
        （与批式逐字相同）；是别的行（含 `trigger`——见面的话本来就写在它前面）⇒ 照常
        交付。块尾再冲掉手里最后一行。

        ⚠️ **已经交付的东西收不回**（用户 2026-09-25 裁决"折中方案"）: 块尾判出的硬问题
        **不回滚** —— 独占行不执行 + 行级续写 ≤1 次；续写也失败 ⇒ 记账 + 下一轮注记，
        **不抛 `MmtLoopError`**（玩家已经看见话，把整轮标成"发送失败"是错的）。
        什么都没交付时（形状全坏 / 空轮 / `inspect` 混排）语义与批式逐字相同。
        """
        candidates = self._line_candidates()
        delivered: list[AgentAction] = []      # 已交付（顺序 = 行序）
        notices: list[MmtLine] = []            # ⭐ 本轮已并入的想起行（N5b）
        reask = False                          # 下一轮是"行级续写"轮（只收控制行）
        reask_note = ""                        # 上一轮为什么没成（模型改口说话时记进注记）
        line_reask = 0
        shape_retry = 0
        t0 = time.monotonic()
        first_at: list[float] = []             # 首行交付时刻（埋点: 流式收益可量化）
        rows_total = 0

        for step in range(MAX_STEPS):
            stream = MmtStream()
            dropped: list[str] = []            # 本步丢掉的软行（记账）
            deferred: list[MmtLine] = []       # 独占行（块尾判）
            held: list[MmtLine] = []           # 一行前瞻压着的行（0~1 条）
            void: list[bool] = [False]         # 本步已作废（inspect 混排 ⇒ 内容行一句不交）
            step_notices: list[MmtLine] = []   # ⭐ 本步的想起行（账目, 块尾并入本轮）

            def _finish() -> TurnResult:
                """**本轮唯一的成功出口**（两条 return 都走它）——账目在这里并入。

                ⚠️ 为什么收成一个出口（陷阱 **48**: "同一状态的记账散在多支分支 ⇒
                少一支就是静默丢数据路径"）: `_turn_lines` 有两个成功 return
                （正常完成 / 已交付后仍有办不了的行），账目若各写一遍,
                加第三个分支时必漏。这里把"并入"收在一处, 两个 return 都调它。
                """
                return self._finish_turn_lines(
                    delivered, user_input, record_input=record_input,
                    notices=[*notices, *step_notices])

            def _plan_row(ln: MmtLine) -> None:
                """**真正办理**压着的行（自愈 → parse → 执行 → 交付）。"""
                planned = self._plan_line(ln, step=step, candidates=candidates)
                if planned.action is None:
                    dropped.append(planned.why)
                    logger.info("行协议: 丢掉办不了的行（下一轮注记）: %s", planned.why)
                    return
                self._deliver_line(planned.action, user_input=user_input,
                                   record_input=record_input, first=not delivered)
                delivered.append(planned.action)
                if not first_at:
                    first_at.append(time.monotonic())
                    logger.info("mmt_stream_first %s/%s step=%d ms=%d",
                                self._char_id, self._session_id, step,
                                int((first_at[0] - t0) * 1000))

            def _flush() -> None:
                while held:
                    _plan_row(held.pop(0))

            def _accept_row(ln: MmtLine) -> None:
                """**一行解析出来**（⑥-3a 的分流口）——只在这里决定时机，不在这里判。"""
                # ⭐ 想起行（N5b）: **不进前瞻机制、不占 held/deferred** —— 它是账目,
                # 与"哪一行什么时候上屏"无关。收在手里, 轮末统一落账（`_log_notices`）。
                # ⚠️ 放在 `reask` 判断**之前**: 续写轮也照样收（账目与续写规则无关）。
                if ln.is_noticed:
                    if not void[0]:            # 本步已作废（inspect 混排）⇒ 账也不落
                        step_notices.append(ln)
                    return
                if reask:
                    return                     # 续写轮按批式办理（"只收控制行"要整轮可见）
                if ln.is_action and ln.action == ACTION_INSPECT and not void[0]:
                    # 静默推理轮：本轮**一句话都不该上屏** ⇒ 收回手里那行, 后面的也不交。
                    if held:
                        self._trace.append({
                            "step": step, "action": "-", "summary": "", "reply": "",
                            "payload": None, "parse_valid": True,
                            "parse_errors": ["inspect 混排: 本轮内容行不交付（整轮回灌）"]})
                        held.clear()
                    step_notices.clear()       # 整轮作废 ⇒ 顺手记的那一笔也不算数
                    void[0] = True
                if void[0]:                    # 本步作废：只有独占行还值得留给块尾判
                    if ln.is_action and ln.action in WHOLE_TURN_ACTIONS:
                        deferred.append(ln)
                    return
                _flush()                       # 下一行不是 inspect ⇒ 手里那行可以出去了
                if ln.is_action and ln.action in WHOLE_TURN_ACTIONS:
                    deferred.append(ln)        # 独占行：块尾（整轮可见）再判 + 执行
                else:
                    held.append(ln)            # 一行前瞻

            def _feed(chunk: str) -> None:
                stream.feed(chunk or "")
                for ln in stream.pop_ready():
                    _accept_row(ln)

            try:
                chat_full = getattr(self.llm, "chat_full", None)
                if chat_full is not None:
                    raw = chat_full(
                        messages, temperature=TEMP, max_tokens=MMT_MAX_TOKENS,
                        # 裸文本：JSONL 整段**不是**合法单对象 ⇒ 不能走 json_object
                        # （那条路会触发 `_extract_json_with_llm_correction` 再调 3 次 LLM）
                        response_format="text",
                        on_chunk=_feed,        # ⑥-3a: chunk 一到就解析、行一到就分流
                        task=MMT,
                    )
                else:                          # 旧桩（只有 chat）→ 批式喂**同一个**解析器
                    raw = self.llm.chat(
                        messages, temperature=TEMP, max_tokens=MMT_MAX_TOKENS,
                        response_format="text",
                        task=MMT,
                    )
                    _feed(raw if isinstance(raw, str) else str(raw))
            except Exception as e:
                logger.warning("LLM 调用失败（行协议 step %d）: %s", step, e)
                feedback(messages, f"LLM 调用失败: {e}\n请重试。")
                continue
            text = raw if isinstance(raw, str) else str(raw)
            messages.append({"role": "assistant", "content": text})
            stream.finish()
            for ln in stream.pop_ready():      # 残余行（末尾没有换行的那条）
                _accept_row(ln)

            all_rows = list(stream.records)
            rows_total += len(all_rows)
            diags = list(stream.diags)
            # ⭐ 想起行**不进办理流水线**（它是账目）——但 `check_turn` 仍要看**整轮**
            # （含它）：否则"整轮只有一笔账"会被判成 `mmt.empty-turn`（硬）,
            # 而真相是"她什么都没说"（走下面那条更准的可见内容判定）。
            lines = [ln for ln in all_rows if not ln.is_noticed]

            if reask:
                # 续写轮**优先只收控制行**（消息行会重复上屏）；但模型若改口"不补那一行、
                # 直接说话"，就**收下它的话**（兜底优先——比整轮失败好），同时记一条
                # "那个操作没执行"的注记，别让它以为做过了（下一轮念一次）。
                # ⚠️ 这一轮**不即时交付**（`_accept_row` 已整批让路）——"只收控制行"这条
                #    规则本身就要整轮可见，所以续写轮按批式办理。
                kept = [ln for ln in lines if ln.is_action]
                if kept:
                    if len(kept) != len(lines):
                        self._trace.append({
                            "step": step, "action": "-", "summary": "", "reply": "",
                            "payload": None, "parse_valid": True,
                            "parse_errors": ["续写轮的消息行已忽略（不重复上屏）"]})
                    lines = kept
                elif lines:
                    self._line_notes.append(
                        "上一轮有一行操作没执行（" + reask_note
                        + "）——不要重复它；玩家问起就如实说明。")
                    self._trace.append({
                        "step": step, "action": "-", "summary": "", "reply": "",
                        "payload": None, "parse_valid": True,
                        "parse_errors": ["续写轮未补控制行 → 改收消息行（兜底）"]})
                reask = False
                batch_rows, check_rows = lines, lines
            else:
                # 正常轮：块尾只剩独占行没办；组合校验（独占 / 标题长度）必须看**整轮**
                #（含已经即时交付的内容行）——独占性是"同一轮还有没有别的行"。
                batch_rows, check_rows = deferred, lines

            hard, _soft = split_issues(check_turn(all_rows, diags))

            # ③ 形状级：整段没解析出任何行（不是 JSONL）⇒ 整轮重发
            if not all_rows and hard:
                shape_retry += 1
                if shape_retry > SHAPE_RETRY_MAX:
                    raise MmtLoopError(
                        f"行协议: 输出不是可解析的行流（形状级重发 {shape_retry} 次仍失败）: "
                        f"{format_issues(hard)}")
                logger.warning("行协议形状级重发 %d/%d: %s",
                               shape_retry, SHAPE_RETRY_MAX, format_issues(hard))
                feedback(messages, f"上一轮输出不是「一行一条 JSON」: {format_issues(hard)}",
                         "请只输出 JSON 行（一行一个对象, 不要数组、不要围栏）。")
                continue

            if batch_rows:
                outcome = self._run_lines(
                    batch_rows, messages, step=step, candidates=candidates,
                    delivered=delivered, user_input=user_input,
                    record_input=record_input, check_rows=check_rows)
            else:
                outcome = _LineOutcome()

            # 块尾冲掉手里最后一行（独占行**先**办过 ⇒ 事件顺序仍是行序）
            if not outcome.fatal and not void[0]:
                _flush()
            if dropped:
                outcome.dropped = "; ".join(
                    x for x in (outcome.dropped, "; ".join(dropped)) if x)
            if not delivered and not outcome.fatal and not outcome.need_more:
                # ⚠️ `need_more` 排除在外：inspect 是**静默推理轮**，那一轮本来就不产出
                #    可见内容（"没有可交付的行"不是失败）。
                outcome.fatal = f"本轮没有产出任何可见内容（{outcome.dropped or '没有可交付的行'}）"

            if outcome.fatal:
                line_reask += 1
                if line_reask <= LINE_REASK_MAX:     # ② 行级续写：只补缺失的操作行
                    logger.warning("行协议行级续写 %d/%d: %s",
                                   line_reask, LINE_REASK_MAX, outcome.fatal)
                    feedback(messages, f"你这一轮有一行操作没能执行: {outcome.fatal}",
                             "请只补**缺失的那一条操作行**（一行 JSON）——"
                             "上面已经说出去的话不要再重复。")
                    reask, reask_note = True, outcome.fatal
                    continue
                if delivered:
                    # ⑥-3a：话已经说出去了 ⇒ **不回滚、也不把整轮标成"发送失败"**。
                    # 独占行不执行 + 记账，下一轮念一次（`mmt.control-unexecuted` 的用法）。
                    logger.warning("行协议: 已交付后仍有办不了的行（不回滚, 记账）: %s",
                                   outcome.fatal)
                    self._trace.append({
                        "step": step, "action": "line_stream/streamed", "summary": "",
                        "reply": "", "payload": None, "parse_valid": False,
                        "parse_errors": [outcome.fatal]})
                    self._line_notes.append(
                        "上一轮有一行操作没执行（" + outcome.fatal
                        + "）——不要重复它；玩家问起就如实说明。")
                    logger.info("mmt_turn %s/%s steps=%d rows=%d delivered=%d "
                                "first_ms=%d ms=%d late_issue=1",
                                self._char_id, self._session_id, step + 1, rows_total,
                                len(delivered),
                                int((first_at[0] - t0) * 1000) if first_at else -1,
                                int((time.monotonic() - t0) * 1000))
                    return _finish()
                raise MmtLoopError(
                    f"行协议: {outcome.fatal}（行级续写 {line_reask} 次仍失败）")

            if outcome.need_more:                # inspect 查完 → 带着资料继续这一轮
                continue

            if outcome.dropped:                  # 软丢行 → 记账 + 下一轮注记
                logger.info("行协议: 丢了操作行（下一轮注记）: %s", outcome.dropped)
                self._line_notes.append(
                    "上一轮有一行操作没执行（" + outcome.dropped
                    + "）——不要重复它；玩家问起就如实说明。")

            logger.info("mmt_turn %s/%s steps=%d rows=%d delivered=%d first_ms=%d ms=%d",
                        self._char_id, self._session_id, step + 1, rows_total,
                        len(delivered),
                        int((first_at[0] - t0) * 1000) if first_at else -1,
                        int((time.monotonic() - t0) * 1000))
            return _finish()

        raise MmtLoopError(f"行协议: 单轮超过 {MAX_STEPS} 步仍未产出可见回复")

    def _plan_line(self, ln: MmtLine, *, step: int,
                   candidates: dict[str, tuple[str, ...]]) -> _Planned:
        """**单行办理**（①自愈 → ③parse + 执行）→ `_Planned`。

        = `_run_lines` 那条流水线的**单行版**（⑥-3a 流式交付用）。消息行直接造
        `mmt_chat`（无需自愈、不进 registry）；操作行**先自愈再喂 registry**——顺序
        是正确性（§10.2 B5：写歪的 id / media_type 会被 registry 硬拒）。
        失败原因由 `_line_failure` 统一措辞（流式与批式同一个出处）。
        """
        if ln.is_text:
            self._trace.append({"step": step, "action": "mmt_chat", "summary": "",
                                "reply": ln.text, "payload": {}, "parse_valid": True,
                                "parse_errors": []})
            return _Planned(action=AgentAction(
                action="mmt_chat", domain=DOMAIN_MMT,
                approval=APPROVAL_AUTO, reply=ln.text, payload={}))
        fixed, note = repair_line(ln, candidates=candidates)
        if fixed is None:
            return _Planned(why=_line_failure(ln.action, "repair", note))
        if note:                                  # 自愈过 → 留痕（可 grep）
            logger.info("mmt 行协议自愈: %s", note)
        action, result = self.registry.parse(to_action_raw(fixed))
        if action is None or not result.is_valid:
            why = "; ".join(result.errors) if result is not None else "动作解析失败"
            return _Planned(why=_line_failure(ln.action, "parse", why))
        try:
            exec_result = self.executor.execute(action)
        except MmtExecError as e:
            return _Planned(why=_line_failure(action.action, "exec-reject", str(e)))
        self._trace.append({"step": step, "action": action.action, "summary": "",
                            "reply": action.reply or "",
                            "payload": dict(action.payload), "parse_valid": True,
                            "parse_errors": [],
                            "exec_ok": exec_result.ok,
                            "exec_message": exec_result.message})
        if not exec_result.ok:
            return _Planned(
                why=_line_failure(action.action, "exec-fail", exec_result.message),
                message=exec_result.message)
        return _Planned(action=action, message=exec_result.message)

    def _run_lines(self, lines: list[MmtLine], messages: list[dict], *, step: int,
                   candidates: dict[str, tuple[str, ...]],
                   delivered: list[AgentAction], user_input: str,
                   record_input: bool,
                   check_rows: list[MmtLine] | None = None) -> _LineOutcome:
        """按行序办理一批行（**四阶段**，顺序是正确性）。

        | 阶段 | 做什么 | 为什么这个顺序 |
        |---|---|---|
        | ① 自愈 | 逐操作行 `repair_line` | **必须早于 registry.parse**（inspect 的 id / send_media 的 media_type 都是硬拒绝 —— §10.2 B5 发现②） |
        | ② 组合校验 | `check_turn(自愈后的行)` | 必须在**【自愈后】**：`chapter_title` 超长会被截断救回，先判就会误报 `control-invalid` |
        | ③ parse + 执行 | `registry.parse` → `executor` | 执行很轻（读资料 / 占位 / 确认），先执行才能知道这一行到底行不行 |
        | ④ 交付 | 逐行 `_deliver_line` | **这批行前面全绿才交付**——`inspect` 混排时绝不先把话放出去 |

        ⚠️ **有硬问题（②）或修不了的操作行（①③）⇒ 这批行不交付** + 回灌；
        丢得起的软问题（`DROPPABLE_ACTIONS`）则**丢行 + 记账**，气泡照常交付。

        `check_rows`（**⑥-3a**）: **组合校验看哪些行**——批式 = 与 `lines` 相同（缺省）;
        流式 = 本步**全部行**（含已经即时交付的内容行）——独占性/标题长度这类判定必须
        看整轮，而块尾只剩独占行没办。校验面里属于 `lines` 的那些行换成**自愈后**的
        版本（② 的"必须在自愈之后"在流式下同样成立）。
        """
        out = _LineOutcome()
        droppable: list[str] = []

        # ---- ① 自愈（零 LLM 成本）------------------------------------------
        repaired: list[tuple[MmtLine, MmtLine | None]] = []   # (原行, 自愈后的行|丢弃)
        for ln in lines:
            if ln.is_text:
                repaired.append((ln, ln))
                continue
            fixed, note = repair_line(ln, candidates=candidates)
            if fixed is None:
                why = _line_failure(ln.action, "repair", note)
                if ln.action in DROPPABLE_ACTIONS:
                    droppable.append(why)
                    repaired.append((ln, None))
                    continue
                out.fatal = why
                return out
            if note:                                  # 自愈过 → 留痕（可 grep）
                logger.info("mmt 行协议自愈: %s", note)
            repaired.append((ln, fixed))

        # ---- ② 组合校验（自愈**之后**才判）----------------------------------
        if check_rows is None:
            subject = [fixed for _raw, fixed in repaired if fixed is not None]
        else:                                         # 流式: 校验面 = 整轮, 已办过的行原样
            fixed_by_id = {id(raw): fixed for raw, fixed in repaired
                           if fixed is not None}
            subject = [fixed_by_id.get(id(ln), ln) for ln in check_rows]
        hard, _soft = split_issues(check_turn(subject))
        if hard:
            out.fatal = format_issues(hard)
            return out

        # ---- ③ parse + 执行（**顺序 = 行序**）-------------------------------
        plan: list[tuple[str, MmtLine | AgentAction]] = []   # 交付计划（保持行序）
        for ln, fixed in repaired:
            if fixed is None:                        # ① 里已记账的软丢行
                continue
            if fixed.is_text:
                plan.append(("text", fixed))
                self._trace.append({"step": step, "action": "mmt_chat", "summary": "",
                                    "reply": fixed.text, "payload": {}, "parse_valid": True,
                                    "parse_errors": []})
                continue
            planned = self._plan_line(fixed, step=step, candidates=candidates)
            if planned.action is None:
                if fixed.action in DROPPABLE_ACTIONS:
                    droppable.append(planned.why)
                    continue
                out.fatal = planned.why
                return out
            if planned.action.action == ACTION_INSPECT:
                # ⭐ AUDIT §B9 的洞：查到的资料**必须回灌** —— 旧路径把它丢了，
                #    模型以为查过了却没资料（"答不上来 → 瞎编"的源头）。
                #    inspect 是静默轮（独占约束保证行序里只有它）⇒ 直接继续这一轮。
                feedback(messages, planned.message)
                out.need_more = True
                return out
            plan.append(("action", planned.action))

        # ---- ④ 交付（**保持行序**：话 → 图 → 话 就是 话 → 图 → 话）----------
        for kind, item in plan:
            if kind == "text":
                act = AgentAction(action="mmt_chat", domain=DOMAIN_MMT,
                                  approval=APPROVAL_AUTO, reply=item.text, payload={})
            else:
                act = item
            self._deliver_line(act, user_input=user_input,
                               record_input=record_input, first=not delivered)
            delivered.append(act)

        if not delivered:                            # 全被丢光（如只有一张空描述的图）
            out.fatal = f"本轮没有产出任何可见内容（{'; '.join(droppable)}）"
            return out
        out.dropped = "; ".join(droppable)
        return out

    def _deliver_line(self, action: AgentAction, *, user_input: str,
                      record_input: bool, first: bool) -> None:
        """**行交付**：事件即时落库（C4）+ 一行一条进历史。

        ⚠️ 与旧路径的差别：事件在**行交付时**就 append（不是整轮成功才落）——
        前端 `events_after` 轮询因此天然拿到增量（**不需要 SSE**）；语义 =
        "话已经发出去了"（半轮产物入真源）。
        """
        reply = (action.reply or "").strip()
        if first and record_input:
            self._history.append({"role": "user", "content": user_input})
        shown = _strip_action_brackets(reply).strip()
        self._history.append({
            "role": "assistant",
            "content": f"[{action.action}] {shown}" if shown else f"[{action.action}]"})
        if self._store is None or not self._session_id:
            return
        char_id = self._current_char.character_id if self._current_char else ""
        try:
            payload = dict(action.payload)
            payload["reply"] = reply
            if first and record_input:
                payload["player"] = user_input
            self._store.append_event(char_id, self._session_id,
                                     make_event("mmt", action.action, payload))
        except Exception as e:                      # 宁缺勿错: 存档失败不阻断对话
            logger.warning("事件流落盘失败, 该行不记录: %s", e)

    def _log_notices(self, notices: Iterable[MmtLine]) -> None:
        """⭐ **想起行的落账**（N5b）—— 一行一句, 编造的引用直接丢。

        链路（`DESIGN_MMT_NEW_ACTION §4.3`, 已裁 = **只记账 + L1 落地**）::

            她写 {"noticed": "名字"} → ① 引擎拿名字找**唯一**那条 episode
                                    ② 找不到 / 有多条 ⇒ **丢**（不猜）+ 台账
                                    ③ 找到 ⇒ 落一条 `noticed` 事件（**非内容事件**）
                                    ④ N5c: L1 建完本段 episode 后**补 akin 边**

        ⚠️ **这一笔不是边**: 此刻"当下这件事"还没成为 episode（`add_edge` 拒悬空,
        而"当下"是 seq 不是节点）⇒ 原设计的"seq 边"在边表里没有合法表示。
        账本来就在事件流里（零新存储）—— L1 从窗口里读它。

        ⚠️ **落账时机 = 本轮内容行都交付之后**（`_finish_turn_lines` 里调）:
        `noticed` 事件的 seq 因此落在**这一轮她自己的话之后** ⇒ N5c 判"这笔账属于哪条
        新 episode"时（取"它之前最近的内容事件"）才会落回**本轮**而不是上一轮。

        `hit` 存的是**引擎解析出来的**节点 id + 规范标题 —— 她写歪的形态只进日志
        （台账可 grep: `mmt_noticed`）。
        """
        rows = list(notices)
        if not rows or self._store is None or not self._session_id:
            return
        char = self._current_char
        if char is None:
            return
        try:
            wstore = WikiStoreV2(self._store.data_root, world_id=self._store.world_id,
                                 char_id=char.character_id)
        except Exception as e:                       # noqa: BLE001 — 宁缺勿错
            logger.warning("想起行落账失败（读不到 wiki, 本笔丢）: %s", e)
            return
        for ln in rows:
            node, why = find_episode(wstore, ln.noticed)
            if node is None:
                # 命中 0（编的 / 抄错字）或 ≥2（同名歧义）⇒ **丢, 不猜**
                logger.info("mmt_noticed drop=%s said=%r", why, ln.noticed)
                continue
            try:
                self._store.append_event(char.character_id, self._session_id,
                                         make_event(TYPE_NOTICED, TYPE_NOTICED,
                                                    {"title": node.title, "hit": node.id}))
            except Exception as e:                   # noqa: BLE001 — 存不上不阻断对话
                logger.warning("想起行落盘失败（本笔丢）: %s", e)
                continue
            logger.info("mmt_noticed hit=%s title=%r said=%r", node.id, node.title,
                        ln.noticed)

    def _finish_turn_lines(self, delivered: list[AgentAction], user_input: str, *,
                           record_input: bool,
                           notices: Iterable[MmtLine] = ()) -> TurnResult:
        """收尾：渲染步骤（**一行一个气泡**）+ 轮数 + digest 判定 → TurnResult。

        ⚠️ 事件与历史**已经在交付时逐行写过了**（`_deliver_line`）——这里不再记一遍
        （messages 时代是整轮一次性写）。
        ⚠️ **想起行的唯一落账口**（`notices`）: 放在最前 —— 它的 seq 要落在本轮内容行
        之后（见 `_log_notices` 的时机说明）, 而这里正是"内容行已经写完"的第一个点。
        两个成功出口都由 `_turn_lines._finish()` 调到, 所以只有这一处（陷阱 48）。
        """
        self._log_notices(notices)
        display = MomoTalkOutput(_process_for_momotalk, self._current_char.display_name)
        steps: list[DisplayStep] = []
        reply_blocks: list[str] = []
        actions_view: list[dict] = []
        for action in delivered:
            reply = (action.reply or "").strip()
            if reply:
                reply_blocks.append(reply)
                steps.extend(display.publish_line(reply))     # ⭐ 一行一个气泡（不切句）
            actions_view.append({"action": action.action, "reply": reply,
                                 "payload": dict(action.payload)})
        self._trim_history()
        if self._current_char is not None:
            self.bond_progress.record_turn(self._current_char.character_id)
        self._advance_round(self._char_id)
        self._maybe_mmt_digest()
        last = delivered[-1]
        return TurnResult(
            ok=True, steps=steps, reply="\n".join(reply_blocks),
            action=last.action, payload=dict(last.payload),
            bond_story=any(a.action == ACTION_TRIGGER for a in delivered),
            actions=actions_view)

    def _advance_round(self, char_id: str) -> None:
        """成功一轮后推进计数（2026-09-02 v2）: 距上次完整 bond 剧情 +1。

        持久化 progress.json（store 会话, 断线/重启继续累计）; 完整 bond
        结束清零（bond_completed）——供时机建议注记（建议线 SUGGEST_BOND_ROUNDS）。
        无 store → 内存镜像（不持久）; 写失败内存继续。
        """
        self._session_rounds += 1
        self._bond_gap += 1
        if self._store is None or not char_id:
            return
        try:
            self._store.write_bond_gap(char_id, self._bond_gap)
        except Exception as e:               # noqa: BLE001 — 写失败内存继续
            logger.warning("progress 写失败（内存计数继续）: %s", e)

    def _bond_progress_note(self) -> str:
        """本轮羁绊剧情时机注记（注入 LLM context, 不入历史）。

        2026-09-02 v2（用户复盘拍板: 引擎建议不拦截）——触发节奏是**建议**
        不是闸门:
          · 距上次完整剧情 < SUGGEST_BOND_ROUNDS: 报事实 + 沉淀提示（不拦——
            真遇到非现在不可的紧急场面, LLM 自行判断可提前, 见 rules 触发专段）
          · ≥ SUGGEST_BOND_ROUNDS: 主动建议——关系铺垫够了, 可找契机发起。
        LLM 有完整剧情上下文（玩家呼救 vs 闲聊）, 程序只有计数器——硬闸
        会误伤紧急剧情, 所以引擎只负责"挑时机提示", 裁决权全交 LLM。
        """
        gap = self._bond_gap
        if gap >= SUGGEST_BOND_ROUNDS:
            return (
                f"【剧情时机】距上次完整羁绊剧情已 {gap} 轮, 铺垫足够: "
                "若此刻出现共处契机或情感张力（或 sensei 需要你出面）, "
                "可以主动发起羁绊剧情（mmt_trigger_bond_story）"
            )
        return (
            f"羁绊进度事实: 距上次完整羁绊剧情仅 {gap} 轮, 还在沉淀期——"
            "不必急着切剧情, 自然聊天就好（真有非现在不可的紧急场面, 你自行判断）"
        )

    def _trim_history(self) -> None:
        max_messages = self._history_rounds * 2
        if len(self._history) > max_messages:
            self._history = self._history[-max_messages:]

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_character(self) -> DynamicCharacter | None:
        return self._current_char

    @property
    def _char_id(self) -> str:
        return self._current_char.character_id if self._current_char else ""

    @property
    def history(self) -> list[dict[str, str]]:
        return list(self._history)

    @property
    def history_length(self) -> int:
        return len(self._history)

    @property
    def trace(self) -> list[dict]:
        """最近一轮的完整动作轨迹（每步: action/summary/reply/payload/执行结果）。"""
        return list(self._trace)
