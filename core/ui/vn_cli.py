"""羁绊剧情 VN CLI — 段落渲染 + 选项交互 + 收敛分支循环 + 存档/回放。

main.py 在 result.bond_story 触发后调用 run_bond_story_vn:
    进入 VN 模式 → 逐场景推剧情（story_scene/story_end 契约 JSON）→ 玩家选选项 / 自由输入推进
    → story_end 收尾或 b 退出 → 回到 MomoTalk 正常对话。
    每场 append type=bond 事件进事件流（DESIGN_SAVE.md §4.2）; 回放从事件流过滤。

UI 行为:
    - 每段逐字打字（任意键跳过动画直接显示全文）
    - 有选项 → 打印 1..N, 玩家输入编号选择
    - 无选项 → 玩家自由输入一句话推进
    - 输入 b 或 Ctrl-D → 退出 VN 回 MomoTalk

所有 input_fn 可注入（测试用 fake input_fn 模拟选择/推进）;
char_ms 可注入（测试传 0 跳过打字动画）。
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path

from core.momotalk import MomoTalkEngine
from core.bond.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.director import build_director
from core.media.gallery import GalleryStore
from core.session import SessionStore
from core.session.events import (
    M_MEMORIAL_ENTER,
    M_MEMORIAL_EXIT,
    M_VN_EXIT,
    M_VN_STATE,
    make_event,
)
from core.ui.streaming import simulate_steps
from llm.image_gen import ImageGenerator, collect_ref_images

logger = logging.getLogger(__name__)

# 打字节奏（毫秒/字）; 测试传 char_ms=0 跳过动画
_PARA_CHAR_MS = 40


# ---------------------------------------------------------------------------
# 打字渲染
# ---------------------------------------------------------------------------

def _kbhit() -> bool:
    """是否有点击任意键（Windows 用 msvcrt; 其他平台无法阻塞探测 → False）。"""
    try:
        import msvcrt
        return bool(msvcrt.kbhit())
    except ImportError:
        return False


def _drain_input() -> None:
    """清空键盘缓冲——跳过动画时按下的 Enter 不能污染下一个 input()。"""
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getch()
    except ImportError:
        pass


def _type_paragraph(text: str, char_ms: int = _PARA_CHAR_MS) -> None:
    """逐字打字渲染一段; char_ms<=0 直接全文, 打字期间任意键跳过。"""
    if char_ms <= 0:
        print(text, end="", flush=True)
        print()
        return
    printed = 0
    for ch in text:
        print(ch, end="", flush=True)
        printed += 1
        if _kbhit():                      # 跳过动画 → 补全剩余文本
            _drain_input()
            print(text[printed:], end="", flush=True)
            break
        time.sleep(char_ms / 1000.0)
    print()  # 段落结束换行


# ---------------------------------------------------------------------------
# 单场景渲染
# ---------------------------------------------------------------------------

def _print_visual(scene: BondScene) -> None:
    """CLI 视觉标签（导演层背景/音频; 纯文本模式无字段 → 不打印）。

    表情不在此汇总——改由 simulate_vn_scene 逐段标注（per-para sprite）。
    """
    if scene.background is None and scene.audio is None:
        return
    parts = []
    if scene.background is not None:
        parts.append(f"[背景 {scene.background or '-'}]")
    if scene.audio is not None:
        parts.append(f"[音频 {scene.audio}]")
    print(" ".join(parts))


def simulate_vn_scene(
    scene: BondScene,
    input_fn=input,
    char_ms: int = _PARA_CHAR_MS,
) -> str | None:
    """渲染一个场景（视觉标签 + 段落 + 选项/收尾）, 返回下一场景的用户输入。

    Returns:
        有选项 → 玩家选择的选项文本（喂回下一场景）
        无选项 → 玩家自由输入的一句话
        b / Ctrl-D / 【完】 → None（退出 VN 回 MomoTalk）
    """
    _print_visual(scene)
    # per-para sprite（架构定稿: 情绪内联进 paragraphs {text, emotion?}）——
    # 段落显式带 emotion 才标注; 延续的段静默（渲染端默认/继承表情）
    # inner（A 版内心戏, 低频惊喜）: 段落带 inner → 屏幕变黑（CLI 近似: 分隔 + 淡标记）
    #   单独展示角色没说出口的心理活动, 再回到台词
    for para in scene.paragraphs:
        if isinstance(para, dict):
            inner = para.get("inner")
            if isinstance(inner, str) and inner.strip():
                print("\n" + "·" * 36 + "  (内心)  " + "·" * 36)
                _type_paragraph(inner.strip(), char_ms)
                print("\n" + "·" * 36 + "  (回到现实)  " + "·" * 36)
            emotion = para.get("emotion")
            if emotion:
                print(f"[表情 {emotion}]")
            text = para.get("text", "")
        else:
            text = str(para)
        _type_paragraph(text, char_ms)

    if scene.is_end:
        print("\n── 羁绊剧情结束 ──")
        return None

    if scene.choices:
        print("\n")
        for i, choice in enumerate(scene.choices, 1):
            print(f"  [{i}] {choice}")
        print("  [b] 退出")
        while True:
            try:
                raw = input_fn("选择: ").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if raw.lower() == "b":
                return None
            if raw.isdigit() and 1 <= int(raw) <= len(scene.choices):
                return scene.choices[int(raw) - 1]
            print("  无效选择, 请再试")
    else:
        try:
            raw = input_fn("（输入一句话推进剧情, b 退出）: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        return None if raw.lower() == "b" else raw


# ---------------------------------------------------------------------------
# VN 主循环
# ---------------------------------------------------------------------------

def _build_director(char, reason: str):
    """构建视觉导演（v2 纯查表模式, 无辅助 LLM; 任何失败 → None 纯文本）。

    情感由主 LLM 在段落内联 emotion 给出, 导演只做 place→背景查表;
    背景/音乐等未来非情感决策若需语义仲裁, 直接用 llm/client.py 的 LLMClient。
    """
    try:
        return build_director(char)
    except Exception as e:
        logger.warning("视觉导演构建失败, 本次 VN 纯文本模式: %s", e)
        return None


def run_bond_story_vn(
    engine: MomoTalkEngine,
    input_fn=input,
    char_ms: int = _PARA_CHAR_MS,
    remind_rounds: int = 30,
    end_rounds: int = 50,
    max_tokens: int = 1536,
    seed: str | None = None,
    store: SessionStore | None = None,
    image_gen: ImageGenerator | None = None,
    gallery: GalleryStore | None = None,
    memorial_seed: int | None = None,
) -> bool:
    """羁绊剧情 VN 模式：触发后进入, is_end 或 b 退出后回到 MomoTalk。

    构造独立 BondStoryEngine（复用引擎的 char_loader.root + llm），
    首个种子 = 触发动作的 reason（有则旁白引述, 无则固定开篇语）。
    store（SessionStore）注入时: 落**事件流**（DESIGN_SAVE.md §4）——enter_vn
    同会话 append vn_enter（单事件流, 无子会话）, 每场 append type=bond 事件 +
    vn_state marker（恢复点）, 结束时 vn_exit + session_end。写失败静默降级不阻断 VN。

    纪念子模式（§4.7, 2026-08-24）:
        image_gen（ImageGenerator）注入时: 开场后台预热生图 pipe（首次 ~12s 不阻塞）;
        LLM 输出 memorial_enter → 当场生图（已预热 ~2s, 显示「生成中」）→ gallery 落盘
        → l2d 事件 + marker memorial_enter; 下一轮 system_note 注入 memorial_exit
        schema（纪念模式内只许 exit）; exit 轮 → marker memorial_exit 回 bond。
        image_gen=None → 纪念场景纯文字渲染（测试/无 GPU 环境）。
        gallery（GalleryStore）可注入（默认 data/）; memorial_seed 固定 → 立绘可复现。

    双层收尾兜底（模型可能迟迟不改用 story_end 动作收尾）:
        第 remind_rounds 场 → 注入系统注记「已推进 N 轮, 剩余约 M 轮」,
                              引导 AI 开始向结尾收束;
        第 end_rounds   场 → 注入系统注记「已达篇幅上限, 本轮务必改用 story_end 收尾」;
        超过 end_rounds+2 场仍不结束 → 程序兜底收尾（循环必须终结, 宁缺勿错）。
    生产默认 30/50; 调试可传 15/22（实验脚本与单测用）。
    max_tokens 透传给 send_vn_scene（长段落场景可调高）;
    seed 覆盖开篇语（默认从触发 reason 引述, 无则固定开篇）。

    Returns:
        True  = 剧情 is_end 自然结束 / 程序兜底收尾（调用方可做手机收尾 wrapup_after_vn）
        False = 玩家 b / Ctrl-D 提前退出
    """
    char = engine.current_character
    if char is None:
        return False

    reason = _trigger_reason(engine)
    # Brain 记忆段（DESIGN_BRAIN.md）: 本世界线 wiki 第一人称注入——
    # VN 中角色记得这个世界线前面的事（resume 过则有 digest 产物; 空 → 零注入, 平行世界）。
    # 读失败静默跳过（不阻断 VN）。
    brain_segment = ""
    try:
        store_ = store if store is not None else engine._store
        if store_ is not None and engine._session_id:
            from core.brain.hippocampus import WikiStore
            from core.brain.recall import build_brain_injection
            wiki = WikiStore(store_.data_root).load(char.character_id, engine._session_id)
            brain_segment = build_brain_injection(wiki, char_name=char.display_name)
    except Exception:                                # noqa: BLE001
        brain_segment = ""
    vn = BondStoryEngine(
        engine.char_loader.root, engine.llm,
        director=_build_director(char, reason), brain_segment=brain_segment)
    vn.start_session(char.character_id)

    print("\n" + "═" * 40)
    print(f"  ── 羁绊剧情: {char.display_name} ──")
    print("═" * 40)

    if seed is None:
        seed = f"（旁白）基于「{reason}」……" if reason else "（旁白）故事开始了……"

    # 事件流（DESIGN_SAVE.md §5.3, 2026-08-24 单流）: 同会话 append vn_enter, 无子会话
    vn_sid = None
    if store is not None:
        try:
            vn_sid = store.enter_vn(
                char.character_id, engine._session_id, reason)
        except Exception as e:
            logger.warning("事件流 vn_enter 写入失败, 本次 VN 不落事件流: %s", e)
            vn_sid = None

    # 纪念立绘: trigger 后立即后台预热生图 pipe（首次 ~12s 不阻塞玩家; enter 轮当场仅 ~2s）
    if image_gen is not None:
        threading.Thread(target=image_gen.warmup, daemon=True).start()
    gallery_store = gallery if gallery is not None else GalleryStore()

    completed = False
    user_input = seed
    force_after = end_rounds + 2          # 建议收尾后再留 2 场余量, 超限硬兜底
    for i in range(1, force_after + 1):
        system_note = None
        # 随机事件（soft, 低频惊喜）: 记忆突然浮现——只在开场（第一场）触发,
        # 双通道回忆 → "你突然想起…"（不要求 AI 反馈, 自然流露即可）
        if i == 1 and store_ is not None and engine._session_id:
            try:
                from core.random_events import fire_event
                from core.brain.hippocampus import WikiStore
                wiki = WikiStore(store_.data_root).load(char.character_id, engine._session_id)
                events = SessionStore(store_.data_root).events(
                    char.character_id, engine._session_id)
                flash = fire_event("memory_flash", {
                    "events": events,
                    "wiki": wiki,
                    "digested_seq": wiki.get("digested_seq", 0),
                })
                if flash:
                    system_note = flash
            except Exception:                                # noqa: BLE001 — 静默跳过
                system_note = None
        if vn.in_memorial:
            # 纪念子模式（§4.7）: 本场只输出 memorial_exit——临时注入 exit schema
            # （纪念模式只有 1 轮: enter 独占一轮含全部内容 → 下一轮 exit 回 bond）
            system_note = (
                "（系统）当前处于**纪念模式**——纪念场景已结束, 本场请输出"
                " memorial_exit 动作回到 bond（可选过渡文字, 不要输出其他动作）。\n"
                f"可用动作 schema:\n{vn.memorial_exit_schema()}"
            )
        elif i == remind_rounds:
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
            # 模型连语义校验都过不了 → 中断收场（宁缺勿错, 循环必须终结）
            print(f"[系统] 剧情生成失败: {e}")
            closing = BondScene(paragraphs=[{"text": "（这一章的羁绊剧情就此中断收场。）"}], is_end=True)
            _type_paragraph(closing.paragraphs[0], char_ms)
            print("\n── 羁绊剧情结束 ──")
            # 事件流: 中断收尾也落 closing 场景（事件流完整, 回放不缺最后一场）
            if store is not None and vn_sid is not None:
                try:
                    store.append_event(char.character_id, vn_sid, make_event(
                        "bond", "story_end",
                        {**closing.to_dict(), "input": user_input, "picked": None}))
                except Exception as ex:
                    logger.warning("事件流写入失败: %s", ex)
            completed = True
            break

        # 纪念进入轮（§4.7）: 生图（APIYI 秒级 / 本地预热后 ~2s, 显示加载中）→ gallery 落盘
        # ref 图 = collect_ref_images（sprite_* 角色 → style_* 画风 → 其余 配饰, 顺序固定）
        # 生图失败 → 降级纯文字, 不阻断剧情（宁缺勿错）
        memorial_images: list[str] = []
        if scene.memorial_prompt and image_gen is not None:
            print("[纪念立绘 生成中…]", flush=True)
            try:
                png = image_gen.generate(
                    scene.memorial_prompt, seed=memorial_seed,
                    ref_images=collect_ref_images(char.character_id),
                    character_name=char.display_name)
                sid = gallery_store.write(
                    char.character_id, scene.memorial_prompt, vn_sid or "", png)
                memorial_images = [str(gallery_store.png_path(char.character_id, sid))]
                print(f"[纪念立绘] {memorial_images[0]}", flush=True)
            except Exception as e:
                logger.warning("纪念立绘生成失败, 本场降级为纯文字: %s", e)
                memorial_images = []

        choice = simulate_vn_scene(scene, input_fn=input_fn, char_ms=char_ms)

        # 事件流（store 注入时）: type=bond 事件（input=本场触发输入, picked=玩家裁决）
        # + 纪念 marker/l2d 事件（§4.7）+ vn_state marker（恢复点: round/seed/visual）
        if store is not None and vn_sid is not None:
            try:
                if scene.memorial_exit:
                    sub = "memorial_exit"
                elif scene.memorial_prompt:
                    sub = "memorial_enter"
                else:
                    sub = "story_end" if scene.is_end else "story_scene"
                store.append_event(char.character_id, vn_sid, make_event(
                    "bond", sub,
                    {**scene.to_dict(), "input": user_input, "picked": choice},
                ))
                # 纪念子模式 marker + l2d 事件（立绘资产; 生图失败 → 无 l2d 事件, 剧情照走）
                if scene.memorial_prompt:
                    store.append_marker(char.character_id, vn_sid, M_MEMORIAL_ENTER,
                                        {"reason": reason})
                    if memorial_images:
                        store.append_event(char.character_id, vn_sid, make_event(
                            "l2d", "memorial_enter",
                            {"paragraphs": [p.get("text", "") for p in scene.paragraphs
                                            if isinstance(p, dict)],
                             "choices": scene.choices,
                             "images": memorial_images}))
                elif scene.memorial_exit:
                    store.append_marker(char.character_id, vn_sid, M_MEMORIAL_EXIT)
                visual = vn.director.state.to_dict() if vn.director is not None else {}
                store.append_marker(char.character_id, vn_sid, M_VN_STATE, {
                    "round": i, "seed": choice or "", "visual": visual})
            except Exception as e:
                logger.warning("事件流写入失败, 跳过本轮: %s", e)

        if choice is None:                # 退出 / is_end 结束
            completed = scene.is_end      # 区分: is_end=剧情走到结尾; b=玩家退出
            break
        user_input = choice
    else:
        # for 循环耗尽 = 模型仍不 is_end → 程序兜底收尾（循环必须终结）
        closing = BondScene(paragraphs=[{"text": "（夜色渐深，这一章的羁绊剧情就此落下帷幕。）"}], is_end=True)
        _type_paragraph(closing.paragraphs[0], char_ms)
        print("\n── 羁绊剧情结束 ──")
        # 事件流: 程序兜底收尾也落 closing 场景（事件流完整, 回放不缺最后一场）
        if store is not None and vn_sid is not None:
            try:
                store.append_event(char.character_id, vn_sid, make_event(
                    "bond", "story_end",
                    {**closing.to_dict(), "input": user_input, "picked": None}))
            except Exception as e:
                logger.warning("事件流写入失败: %s", e)
        completed = True
    print("[系统] 已退出羁绊剧情, 回到 MomoTalk。")

    # 事件流收尾（统一, 无论哪条路径）: vn_exit + session_end（没写 = 中断）
    if store is not None and vn_sid is not None:
        try:
            store.append_marker(char.character_id, vn_sid, M_VN_EXIT)
            store.finish(char.character_id, vn_sid, ended=completed)
        except Exception as e:
            logger.warning("事件流收尾失败: %s", e)

    return completed


def wrapup_after_vn(engine: MomoTalkEngine, reason: str = "") -> None:
    """羁绊剧情【完】后的手机收尾: 自动触发一轮, AI 就这段剧情回几段话。

    系统注记只进 LLM context（agent_turn system_note + record_input=False）,
    历史只记 assistant 回复——不污染假 user 消息。一轮可见回复后结束,
    等玩家下一句（「结束一轮」）。收尾失败不阻塞聊天（宁缺勿错, 打印降级）。
    """
    char = engine.current_character
    if char is None:
        return
    if not reason:
        reason = _trigger_reason(engine)      # 注记引述起因（引擎 trace 还在）
    reason_suffix = f"（起因: {reason}）" if reason else ""
    note = (
        "（系统）羁绊剧情刚刚结束，你们回到了 MomoTalk 手机聊天。"
        f"请以{char.display_name}的身份，就刚才这段羁绊剧情{reason_suffix}，"
        "在手机上回复老师几句话作为收尾——自然、简短、像真实的手机消息。"
        "只使用 mmt_chat 动作，不要再次触发羁绊剧情。"
    )
    try:
        result = engine.agent_turn("（自动收尾）", system_note=note, record_input=False)
        simulate_steps(result.steps)
    except Exception as e:
        print(f"[系统] 羁绊剧情收尾回复失败: {e}")


def _trigger_reason(engine: MomoTalkEngine) -> str:
    """从最近一轮动作轨迹里取触发动作的 reason（找不到 → 空串）。"""
    if not engine.trace:
        return ""
    for step in reversed(engine.trace):
        if step.get("action") == "mmt_trigger_bond_story":
            payload = step.get("payload") or {}
            return payload.get("reason") or ""
    return ""
