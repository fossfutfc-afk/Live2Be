"""羁绊剧情 VN CLI — 段落渲染 + 选项交互 + 收敛分支循环 + 存档/回放。

main.py 在 result.bond_story 触发后调用 run_bond_story_vn:
    进入 VN 模式 → 逐场景推剧情（story_scene/story_end 契约 JSON）→ 玩家选选项 / 自由输入推进
    → story_end 收尾或 b 退出 → 回到 MomoTalk 正常对话。
    每场 append type=bond 事件进事件流（docs/archive/DESIGN_SAVE.md §4.2）; 回放从事件流过滤。

UI 行为（渲染收编 renderer/, 2026-08-28 M1 迁移）:
    - 渲染统一走 renderer 管线（DESIGN_RENDERER.md）: RenderScene.from_live(BondScene)
      → Renderer.render → renderer/cli.py 渲染（背景标签/表情标注/特效符号/打字机）
    - 每段逐字打字（任意键跳过动画直接显示全文）
    - 有选项 → 打印 1..N, 玩家输入编号选择
    - 无选项 → 玩家自由输入一句话推进
    - 输入 b 或 Ctrl-D → 退出 VN 回 MomoTalk

所有 input_fn 可注入（测试用 fake input_fn 模拟选择/推进）;
char_ms 可注入（测试传 0 跳过打字动画）。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.brain.store import WikiStoreV2
from core.director.wiring import _build_director, _trigger_title  # C11: 接线层（webgui 也用它）
from core.media.gallery import GalleryStore
from core.mmt.engine import MomoTalkEngine, load_brain_segment
from core.parsing.names import speaker_names  # 名字接口（N1）
from core.session import SessionStore
from core.session.events import (
    M_MEMORIAL_ENTER,
    M_VN_EXIT,
    M_VN_STATE,
    make_event,
)
from core.tui.streaming import simulate_steps
from llm.image_gen import ImageGenerator, collect_ref_images
from renderer import Renderer, RenderScene
from renderer.cli import PARA_CHAR_MS, read_choice, read_free_input, render_scene

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 单场景渲染（委托 renderer 管线——背景/表情/特效/打字/选项全部收编）
# ---------------------------------------------------------------------------

def _speaker_names(char) -> dict[str, str]:
    """记录流 v2 说话人显示名映射（**实现已收敛到 `core.parsing.names`**, N1）:
    角色 id → display_name, sensei → 老师。

    ⚠️ `with_narrator=False` —— CLI 靠"**缺键**"决定不画名字行（webgui 那边是
    `narrator` → 空串; 两套约定都是现网行为, 不统一）。
    """
    return speaker_names(char, with_narrator=False)


def simulate_vn_scene(
    scene: BondScene,
    input_fn=input,
    char_ms: int = PARA_CHAR_MS,
    renderer: Renderer | None = None,
    speaker_names: dict[str, str] | None = None,
) -> str | None:
    """渲染一个场景（视觉标签 + 段落 + 特效 + 选项/收尾）, 返回下一场景的用户输入。

    renderer: 由 run_bond_story_vn 构建一次注入（真实资产查库）;
    None → 懒构建空角色渲染器（无词表/无角色特效覆盖——测试与直接调用路径,
    背景/表情/全局特效照常）。
    speaker_names: 记录流 v2 说话人 → 显示名（缺省则不画名字行——旧档/测试路径）。
    """
    if renderer is None:
        renderer = Renderer("")
    render_scene_obj = RenderScene.from_live(scene)
    if speaker_names:
        for p in render_scene_obj.paragraphs:
            sp = p.get("speaker") if isinstance(p, dict) else None
            if isinstance(sp, str) and sp.strip() and sp.strip() in speaker_names:
                p["speaker_name"] = speaker_names[sp.strip()]
    out = renderer.render(render_scene_obj)
    render_scene(out, char_ms=char_ms)

    if scene.is_end:
        return None
    if scene.choices:
        return read_choice(scene.choices, input_fn=input_fn)
    return read_free_input(input_fn=input_fn)


# ---------------------------------------------------------------------------
# VN 主循环
# ---------------------------------------------------------------------------
# ⚠️ C11: `_build_director` / `_trigger_title` 已搬到 `core.director.wiring`
#    （webgui 也要用它们, 留在 CLI 里会形成 webgui → CLI 的反向依赖）;
#    上面已 import 回来, 本文件内的调用点一个字未改。


def run_bond_story_vn(
    engine: MomoTalkEngine,
    input_fn=input,
    char_ms: int = PARA_CHAR_MS,
    remind_rounds: int = 30,
    end_rounds: int = 50,
    max_tokens: int | None = None,
    seed: str | None = None,
    store: SessionStore | None = None,
    image_gen: ImageGenerator | None = None,
    gallery: GalleryStore | None = None,
    memorial_seed: int | None = None,
) -> bool:
    """羁绊剧情 VN 模式：触发后进入, is_end 或 b 退出后回到 MomoTalk。

    构造独立 BondStoryEngine（复用引擎的 char_loader.root + llm），
    首个种子 = 触发动作的 chapter_title（2026-09-05: reason 退役; 起因由上下文窗口承载——
    触发前对话经 window_messages 灌入 vn._history, 首场自带; title 有则旁白命题引述,
    无则固定开篇语）。
    store（SessionStore）注入时: 落**事件流**（docs/archive/DESIGN_SAVE.md §4）——enter_vn
    同会话 append vn_enter（单事件流, 无子会话）, 每场 append type=bond 事件 +
    vn_state marker（恢复点）, 结束时 vn_exit + session_end。写失败静默降级不阻断 VN。

    纪念子模式（§4.7, 2026-08-24; 2026-09-10 生图改 APIYI 单后端）:
        image_gen（ImageGenerator）注入时: LLM 输出 memorial_enter → 当场生图
        （APIYI 实测单张 26s 量级, 显示「生成中」）→ gallery 落盘 → l2d 事件 +
        marker memorial_enter; 下一轮 system_note 注入 memorial_exit schema
        （纪念模式内只许 exit）; exit 轮 → marker memorial_exit 回 bond。
        image_gen=None / 未配 key / **总开关为关** → 纪念场景纯文字渲染
        （测试环境友好）。
        gallery（GalleryStore）可注入（默认 data/）; memorial_seed 保留为历史参数。

    双层收尾兜底（模型可能迟迟不改用 story_end 动作收尾）:
        第 remind_rounds 场 → 注入系统注记「已推进 N 轮, 剩余约 M 轮」,
                              引导 AI 开始向结尾收束;
        第 end_rounds   场 → 注入系统注记「已达篇幅上限, 本轮务必改用 story_end 收尾」;
        超过 end_rounds+2 场仍不结束 → **不再程序兜底伪收场**（2026-09-09 CLI
        对齐 webgui 中止语义: 中断/异常 ≠ 失败/完成）——completed=False 中断
        退出（不落 closing story_end, 章在押; 重进续写能力待 CLI resume 落地,
        TODO 中期回放）。模型持续不收尾属异常, 纠正是注记, 不是伪终结。
    生产默认 30/50; 调试可传 15/22（实验脚本与单测用）。
    max_tokens: 输出上限透传 send_vn_scene（None → 真源 llm/task_levels.py 形态
    "vn_cli" = 1536, 2026-09-02 集中管理; 长段落场景可显式调高）;
    seed 覆盖开篇语（默认从触发 reason 引述, 无则固定开篇）。

    Returns:
        True  = 剧情 is_end 自然结束 / 程序兜底收尾（调用方可做手机收尾 wrapup_after_vn）
        False = 玩家 b / Ctrl-D 提前退出
    """
    if max_tokens is None:
        from llm.task_levels import max_tokens as _tl_mt
        max_tokens = _tl_mt("vn_cli")
    # 生图总开关（2026-09-11）: 关（LIVE2BE_IMAGE=off / settings [image].enabled=false）
    # → 一律当没注入生图器——纪念场景纯文字, 连 warmup 线程都不开
    if image_gen is not None and not getattr(image_gen, "enabled", True):
        logger.info("生图总开关为关 → CLI 纪念场景纯文字（不出图）")
        image_gen = None
    char = engine.current_character
    if char is None:
        return False

    title = _trigger_title(engine)
    # Brain 记忆段（DESIGN_BRAIN.md, brain 2026-09-02 切换）: 本世界线 wiki
    # 第一人称注入——VN 中角色记得这个世界线前面的事（resume 过则有 digest 产物;
    # 空 → 零注入, 平行世界）。读失败静默跳过（不阻断 VN）。
    brain_segment = ""
    try:
        store_ = store if store is not None else engine._store
        if store_ is not None and engine._session_id:
            brain_segment = load_brain_segment(
                store_, char.character_id, char.display_name,
                characters_root=engine.char_loader.root)
    except Exception:                                # noqa: BLE001
        brain_segment = ""
    vn = BondStoryEngine(
        engine.char_loader.root, engine.llm,
        director=_build_director(char), brain_segment=brain_segment)
    vn.start_session(char.character_id)
    # 统一上下文窗口（2026-09-05, DESIGN_CONTEXT_WINDOW）: 触发/恢复时从事件流
    # 灌最近叙事进 vn._history——首场带着触发前的 MMT 对话（断桥修复: AI 知道自己
    # 刚聊过什么）; 与引擎内部自增历史同构（render_bond_scene_text）。store 缺 → 跳过
    try:
        store_ = store if store is not None else engine._store
        if store_ is not None:
            from core.session.maintenance import exclude_abandoned
            from core.session.renderer import window_messages
            _win = window_messages(
                exclude_abandoned(store_.events(char.character_id)))
            if _win:
                vn._history = _win
    except Exception:                                # noqa: BLE001 — 灌窗失败不阻断
        pass

    # 渲染器（M1 收编）: 本场 VN 共用——背景查库/差分意图/特效/打字/选项全部走 renderer 管线
    renderer = Renderer(char.character_id)

    print("\n" + "═" * 40)
    print(f"  ── 羁绊剧情: {char.display_name} ──")
    print("═" * 40)

    if seed is None:
        seed = (f"（旁白）本章：{title}——从刚才的对话与契机自然展开。"
                if title else "（旁白）故事开始了……")

    # 事件流（docs/archive/DESIGN_SAVE.md §5.3, 2026-08-24 单流）: 同会话 append vn_enter, 无子会话
    # 2026-09-17（B0 整章暂存）: **章内一切改走暂存**（`staging_store`），见到
    # `vn_exit` 时由 `commit_staging` 整段搬进真源 —— 与 webgui 同一条链。
    # `truth` 留住真源 store（收尾时 commit 用）；失败则回退到真源（旧行为）。
    vn_sid = None
    truth = store
    if store is not None:
        try:
            from core.session.staging import staging_store
            store = staging_store(store)
            vn_sid = store.enter_vn(
                char.character_id, engine._session_id, title)
        except Exception as e:
            logger.warning("事件流 vn_enter 写入失败, 本次 VN 不落事件流: %s", e)
            store = truth
            vn_sid = None

    # 纪念立绘: trigger 后立即后台预热（APIYI 无预热对象, warmup 为兼容占位）
    if image_gen is not None:
        threading.Thread(target=image_gen.warmup, daemon=True).start()
    gallery_store = gallery if gallery is not None else GalleryStore()

    completed = False
    fails = 0                      # 连续生成失败计数（对齐 webgui MAX_GEN_FAILURES）
    user_input = seed
    force_after = end_rounds + 2          # 建议收尾后再留 2 场余量（超限 = 中断, 不伪收场）
    for i in range(1, force_after + 1):
        system_note = None
        # 随机事件（soft, 低频惊喜）: 记忆突然浮现——只在开场（第一场）触发,
        # brain 双通道随机摘段 → "你突然想起…"（不要求 AI 反馈, 自然流露即可）
        if i == 1 and store_ is not None and engine._session_id:
            try:
                from core.brain.read.recall import random_flash_segment
                from core.random_events import fire_event
                wstore = WikiStoreV2(store_.data_root, world_id=store_.world_id,
                                     char_id=char.character_id)
                flash = fire_event("memory_flash", {
                    "wstore": wstore,
                    "segment": random_flash_segment(wstore),
                })
                if flash:
                    system_note = flash
            except Exception:                                # noqa: BLE001 — 静默跳过
                system_note = None
        # 2026-09-21: 原"纪念子模式 → 注入 memorial_exit 动作 schema"分支已随 v1 动作
        # 整族退役删除（v2 的纪念是**块内区间**——`stage:memorial` 之后到块尾, 没有
        # exit 动作; 引擎也只吃记录流, 注入动作 schema 会被打回重发）。
        if i == remind_rounds:
            system_note = (
                f"（系统）剧情已推进 {i} 轮，剩余约 {end_rounds - i} 轮。"
                "请开始把剧情向结尾收束——感情到位、约定达成、道别告别的时刻"
                "就改用 story_end 动作收尾结束剧情，不要再开新场景"
                "不过也谨记这只是中段提示，你并不需要匆匆结尾，但是建议开始铺垫"
            )
        elif i == end_rounds:
            system_note = (
                "（系统）已达剧情篇幅上限。本轮请改用 story_end 动作收尾"
                "结束剧情——收尾场景只有 paragraphs，不再输出选项。"
            )

        try:
            scene = vn.send_vn_scene(user_input, max_tokens=max_tokens, system_note=system_note)
        except (SceneLoopError, ValueError) as e:
            # 2026-09-09 CLI 对齐（webgui 中止语义）: 失败 ≠ 完成——不再落
            # closing story_end + completed=True（历史伪收场: 中断被当成完成,
            # 事件流出现假结尾 + digest/收尾话误触发）。改: 同输入自动重试
            # （≤3 次）, 仍失败 → 中断退出（completed=False → vn_exit False,
            # 章在押不落收尾事件; 重进续写待 CLI resume 落地）
            fails += 1
            logger.warning("VN 场景生成失败（第 %d 次, 自动重试）: %s", fails, e)
            if fails <= 3:
                print(f"[系统] 剧情生成失败（第 {fails} 次）——正在自动重试同输入…")
                continue
            print("[系统] 连续多次生成失败，本章剧情暂缓——未结束不落收尾事件；"
                  "稍后重新触发本剧情可继续。")
            completed = False
            break

        # 纪念进入轮（§4.7）: 生图（APIYI 单张 26s 量级, 显示加载中）→ gallery 落盘
        # ref 图 = collect_ref_images（sprite_* 角色 → style_* 画风 → 其余 配饰, 顺序固定）
        # 生图失败 → 降级纯文字, 不阻断剧情（宁缺勿错）
        memorial_images: list[str] = []
        # v2 生图 prompt = 块级 `art` 画面意向 → 缺省退化用触发句; **复用引擎那条唯一实现**
        # （与 webgui 同源）。2026-09-21: 原 `scene.memorial_prompt`（v1 字段）已删。
        memorial_prompt = (vn._memorial_image_prompt(scene.records, scene.art_hint)
                           if scene.memorial else "")
        if memorial_prompt and image_gen is not None:
            print("[纪念立绘 生成中…]", flush=True)
            try:
                hints = engine.char_loader.load_illustration(char.character_id)
                persona = (hints.get("character_hint") or "").strip() or (
                    char.image_persona_brief())      # 性格简卡兜底（D1）
                refs = collect_ref_images(char.character_id)
                img = image_gen.generate(
                    memorial_prompt, seed=memorial_seed,
                    ref_images=refs,
                    character_name=char.display_name,
                    character_hint=persona,
                    halo_hint=hints.get("halo_hint", ""))
                sid = gallery_store.write(
                    char.character_id, memorial_prompt, vn_sid or "", img.path,
                    width=img.width, height=img.height,
                    # ⚠️ 写者是**触发那一次的 `BondStoryEngine`**（`vn`, 见
                    # `_fire_memorial_image`）——与 webgui 同款修正（2026-09-27）:
                    # 原先读 MMT `engine` 的属性 ⇒ 字段从来不写、art 命中率没得算。
                    prompt_source=getattr(vn, "memorial_prompt_source", "") or "",
                    refs=[Path(p).name for p in refs],
                    model=getattr(image_gen, "api_model", "") or "")
                memorial_images = [str(gallery_store.png_path(char.character_id, sid))]
                print(f"[纪念立绘] {memorial_images[0]} "
                      f"({img.width}x{img.height}, {img.elapsed_s:.1f}s)", flush=True)
            except Exception as e:
                logger.warning("纪念立绘生成失败, 本场降级为纯文字: %s", e)
                memorial_images = []

        choice = simulate_vn_scene(scene, input_fn=input_fn, char_ms=char_ms,
                                   renderer=renderer,
                                   speaker_names=_speaker_names(char))

        # 事件流（store 注入时）: type=bond 事件（input=本场触发输入, picked=玩家裁决）
        # + 纪念 marker/l2d 事件（§4.7）+ vn_state marker（恢复点: round/seed/visual）
        if store is not None and vn_sid is not None:
            try:
                sub = "story_end" if scene.is_end else "story_scene"
                store.append_event(char.character_id, vn_sid, make_event(
                    "bond", sub,
                    {**scene.to_dict(), "input": user_input, "picked": choice},
                ))
                # v2 纪念 marker + l2d 事件（立绘资产; 生图失败 → 无 l2d 事件, 剧情照走）
                if scene.memorial:
                    store.append_marker(char.character_id, vn_sid, M_MEMORIAL_ENTER,
                                        {"chapter_title": title, "v2": True})
                    if memorial_images:
                        store.append_event(char.character_id, vn_sid, make_event(
                            "l2d", "memorial_enter",
                            {"paragraphs": [p.get("text", "") for p in scene.paragraphs
                                            if isinstance(p, dict)],
                             "choices": scene.choices,
                             "images": memorial_images}))
                visual = vn.director.state.to_dict() if vn.director is not None else {}
                store.append_marker(char.character_id, vn_sid, M_VN_STATE, {
                    "round": i, "seed": choice or "", "visual": visual})
            except Exception as e:
                logger.warning("事件流写入失败, 跳过本轮: %s", e)

        if choice is None:                # 退出 / is_end 结束
            completed = scene.is_end      # 区分: is_end=剧情走到结尾; b=玩家退出
            break
        # 记录流 v2（P0-7c）: 选项 = 裁决 —— 物化进历史尾部 + 用"（继续）"领下一板
        # （与 webgui 裁决路径、事件流回放三者同形）; 纯叙事场的自由输入仍是玩家原话
        # （CLI 开发通道语义：那确实是"玩家说的话"）。
        if scene.records and choice in (scene.choices or []):
            vn.record_picked(choice)
            user_input = "（继续）"
        else:
            user_input = choice
    else:
        # for 循环耗尽 = 模型仍不 is_end（其间生成均成功）——2026-09-09 对齐:
        # 不再程序兜底 closing 伪收场（completed=False 中断, 不落 story_end;
        # 已落库场次 = 正常内容, 章在押, 重进续写待 CLI resume 落地）
        print("[系统] 剧情篇幅已达上限但角色仍未收尾——本章暂缓结束（未收尾不落"
              "收尾事件）。重新触发本剧情可继续。")
        completed = False
    print("[系统] 已退出羁绊剧情, 回到 MomoTalk。")

    # 事件流收尾（统一, 无论哪条路径）: vn_exit + session_end（没写 = 中断）
    # vn_exit 带剧情完成标志（2026-09-01）: completed = 剧情真正走完
    # （story_end/兜底收尾）; False = 玩家中途退出——收尾链据此分支
    if truth is not None and vn_sid is not None:
        try:
            from core.session.staging import commit_staging
            # `vn_exit` 进**暂存**，随后整段 commit —— 真源里 `vn_enter…vn_exit`
            # 一次到位，中间不留未闭合窗口（B0）。`session_end` 仍写真源（不属于章）。
            store.append_marker(char.character_id, vn_sid, M_VN_EXIT,
                                {"completed": completed})
            commit_staging(truth, char.character_id, vn_sid,
                           completed=completed)
            truth.finish(char.character_id, vn_sid, ended=completed)
        except Exception as e:
            logger.warning("事件流收尾失败: %s", e)
    # 2026-09-02 用户拍板: 完整剧情结束（vn_exit completed）→ 距上次剧情计数
    # 清零（触发门槛 + 剧情后冷却一体; 中途退出不清——只有完整演过才值得冷却）
    if completed and engine is not None:
        try:
            engine.bond_completed()
        except Exception as e:                   # noqa: BLE001 — 清零失败降级
            logger.warning("bond_gap 清零失败: %s", e)

    return completed


def wrapup_after_vn(engine: MomoTalkEngine,
                    completed: bool = True,
                    pending_check=None) -> None:
    """羁绊剧情收尾后的手机收尾: 自动触发一轮, AI 就这段剧情回几段话。

    系统注记只进 LLM context（agent_turn system_note + record_input=False）,
    历史只记 assistant 回复——不污染假 user 消息。一轮可见回复后结束,
    等玩家下一句（「结束一轮」）。收尾失败不阻塞聊天（宁缺勿错, 打印降级）。

    2026-09-05: reason 参数退役——收尾前给引擎灌统一窗口（事件流含刚结束的
    bond 场景叙事——agent_turn 的 AI 知道这段剧情讲了什么, 无需起因便签）。

    completed=True（剧情 story_end 自然结束/兜底收尾）: 话术按"完整剧情"收尾 +
    async_digest（【digest 唯一触发点】完整段（mmt+bond）异步消化）;
    completed=False（玩家中途退出）: 话术明示中断（防 LLM 脑补未发生的剧情
    结果）+ **不 digest**（记忆只反映完整剧情段——中断不提炼, 未消化的
    mmt 留到下次完整剧情段一起消化, 增量幂等）。

    pending_check（GUI 插嘴处理）: 若调用方提供且返回 True（玩家已有消息在
    排队——bond 刚结束瞬间手快发了消息）, 跳过收尾轮——玩家已表达"我要
    说话", 收尾话省略（省一次 LLM 调用 + 不错位）。CLI 同步输入天然无法
    插嘴, 不传。收尾轮【生成期间】的插嘴由调用方排队（收尾话照常显示,
    插嘴回复随后, LLM 上下文自然衔接）。
    """
    char = engine.current_character
    if pending_check is not None and pending_check():
        if completed:
            engine.async_digest_after_vn()    # 已完整闭环: 消化 + ⭐S3 清零轮数
        return
    if char is None:
        if completed:
            engine.async_digest_after_vn()    # ⭐ S3: 消化 + 清零 mmt 轮数
        return
    # 统一上下文窗口（2026-09-05）: bond 期间 momotalk 引擎未跑——收尾前把
    # 事件流（含刚结束的 bond 场景叙事）灌进 _history, 收尾话自然接续剧情
    try:
        if engine._store is not None:
            from core.session.maintenance import exclude_abandoned
            from core.session.renderer import window_messages
            _win = window_messages(
                exclude_abandoned(engine._store.events(char.character_id)))
            if _win:
                engine._history = _win
    except Exception:                                # noqa: BLE001 — 灌窗失败不阻断
        pass
    title = _trigger_title(engine)                  # 章名引述（引擎 trace 还在）
    title_suffix = f"（本章: {title}）" if title else ""
    if completed:
        note = (
            "（系统）羁绊剧情刚刚结束，你们回到了 MomoTalk 手机聊天。"
            f"请以{char.display_name}的身份，就刚才这段羁绊剧情{title_suffix}，"
            "在手机上回复老师几句话作为收尾——自然、简短、像真实的手机消息。"
            "只使用 mmt_chat 动作，不要再次触发羁绊剧情。"
        )
    else:
        # 中途退出: 剧情只进行到一半——明示中断, 防止 LLM 依据触发起因
        # 脑补"剧情结果"（实测: 收尾话把未发生的对决总结成"玩得很开心"）
        note = (
            "（系统）羁绊剧情**只进行到一半**就中断了——老师中途离开了，"
            f"你们没有完成这段剧情{title_suffix}。"
            f"请以{char.display_name}的身份，在手机上给老师发一条简短的告别消息"
            "（如「下次再继续」）——**不要总结剧情结果、不要描述没有发生的剧情**。"
            "只使用 mmt_chat 动作，不要再次触发羁绊剧情。"
        )
    try:
        result = engine.agent_turn("（自动收尾）", system_note=note, record_input=False,
                                   task_kind="wrapup")
        simulate_steps(result.steps)
    except Exception as e:
        print(f"[系统] 羁绊剧情收尾回复失败: {e}")
    if completed:
        engine.async_digest_after_vn()        # 仅完整剧情消化（中断不提炼）+ ⭐S3 清零


# ⚠️ C11: `_trigger_title` 见文件头的 import（真家 = `core.director.wiring`）。

