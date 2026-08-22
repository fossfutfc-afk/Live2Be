"""羁绊剧情 VN CLI — 段落渲染 + 选项交互 + 收敛分支循环 + 存档/回放。

main.py 在 result.bond_story 触发后调用 run_bond_story_vn:
    进入 VN 模式 → 逐场景推剧情（story_scene/story_end 契约 JSON）→ 玩家选选项 / 自由输入推进
    → story_end 收尾或 b 退出 → 回到 MomoTalk 正常对话。
    每场经 BondStorySave 原子落盘 data/saves/（一解析器两用: 存档可只读回放）。

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
import time
from pathlib import Path

from core.momotalk import MomoTalkEngine
from core.bond_story import BondScene, BondStoryEngine, SceneLoopError
from core.bond_story_save import BondStorySave, load_save
from core.director import DirectorLLM, build_director
from core.ui.streaming import simulate_steps

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
    """CLI 视觉标签（导演层字段; 纯文本模式无字段 → 不打印）。"""
    if scene.sprite is None and scene.background is None:
        return
    print(f"[表情 {scene.sprite or '-'}] [背景 {scene.background or '-'}]")


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
    for para in scene.paragraphs:
        _type_paragraph(para, char_ms)

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
    """构建视觉导演（人设 + 触发原因注入）; 任何失败 → None（本次 VN 纯文本模式）。

    本地导演 LLM 缺失/挂了不影响 VN——调用失败自动降级正则+默认（宁缺勿错）。
    """
    try:
        return build_director(char, trigger_reason=reason, llm=DirectorLLM())
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
    recorder: BondStorySave | None = None,
) -> bool:
    """羁绊剧情 VN 模式：触发后进入, is_end 或 b 退出后回到 MomoTalk。

    构造独立 BondStoryEngine（复用引擎的 char_loader.root + llm），
    首个种子 = 触发动作的 reason（有则旁白引述, 无则固定开篇语）。
    每场经 recorder（BondStorySave）原子落盘 data/saves/——契约 JSON 副产物,
    存档可被 replay_bond_story 只读回放（一解析器两用）。

    双层收尾兜底（模型可能迟迟不改用 story_end 动作收尾）:
        第 remind_rounds 场 → 注入系统注记「已推进 N 轮, 剩余约 M 轮」,
                              引导 AI 开始向结尾收束;
        第 end_rounds   场 → 注入系统注记「已达篇幅上限, 本轮务必改用 story_end 收尾」;
        超过 end_rounds+2 场仍不结束 → 程序兜底收尾（循环必须终结, 宁缺勿错）。
    生产默认 30/50; 调试可传 15/22（实验脚本与单测用）。
    max_tokens 透传给 send_vn_scene（长段落场景可调高）;
    seed 覆盖开篇语（默认从触发 reason 引述, 无则固定开篇）;
    recorder 注入存档器（None 时自动建, 建失败降级为不记录——写失败不阻断 VN）。

    Returns:
        True  = 剧情 is_end 自然结束 / 程序兜底收尾（调用方可做手机收尾 wrapup_after_vn）
        False = 玩家 b / Ctrl-D 提前退出
    """
    char = engine.current_character
    if char is None:
        return False

    reason = _trigger_reason(engine)
    vn = BondStoryEngine(
        engine.char_loader.root, engine.llm, director=_build_director(char, reason))
    vn.start_session(char.character_id)

    print("\n" + "═" * 40)
    print(f"  ── 羁绊剧情: {char.display_name} ──")
    print("═" * 40)

    if seed is None:
        seed = f"（旁白）基于「{reason}」……" if reason else "（旁白）故事开始了……"

    if recorder is None:
        try:
            recorder = BondStorySave(char.character_id, char.display_name, reason)
        except Exception as e:
            logger.warning("存档创建失败, 本次不记录: %s", e)
            recorder = None

    completed = False
    user_input = seed
    force_after = end_rounds + 2          # 建议收尾后再留 2 场余量, 超限硬兜底
    for i in range(1, force_after + 1):
        system_note = None
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
            # 模型连语义校验都过不了 → 中断收场（宁缺勿错, 循环必须终结）
            print(f"[系统] 剧情生成失败: {e}")
            closing = BondScene(paragraphs=["（这一章的羁绊剧情就此中断收场。）"], is_end=True)
            _type_paragraph(closing.paragraphs[0], char_ms)
            print("\n── 羁绊剧情结束 ──")
            if recorder:
                try:
                    recorder.append(closing, None, user_input)
                    recorder.finish(ended=True)
                except Exception as ex:
                    logger.warning("存档写入失败: %s", ex)
            completed = True
            break

        choice = simulate_vn_scene(scene, input_fn=input_fn, char_ms=char_ms)
        if recorder:
            try:
                recorder.append(scene, picked=choice, input_text=user_input)
            except Exception as e:
                logger.warning("存档写入失败, 跳过本轮: %s", e)

        if choice is None:                # 退出 / is_end 结束
            completed = scene.is_end      # 区分: is_end=剧情走到结尾; b=玩家退出
            if recorder:
                try:
                    recorder.finish(ended=scene.is_end)
                except Exception as e:
                    logger.warning("存档收尾写入失败: %s", e)
            break
        user_input = choice
    else:
        # for 循环耗尽 = 模型仍不 is_end → 程序兜底收尾（循环必须终结）
        closing = BondScene(paragraphs=["（夜色渐深，这一章的羁绊剧情就此落下帷幕。）"], is_end=True)
        _type_paragraph(closing.paragraphs[0], char_ms)
        print("\n── 羁绊剧情结束 ──")
        if recorder:
            try:
                recorder.append(closing, None, user_input)
                recorder.finish(ended=True)
            except Exception as e:
                logger.warning("存档写入失败: %s", e)
        completed = True
    print("[系统] 已退出羁绊剧情, 回到 MomoTalk。")
    return completed


# ---------------------------------------------------------------------------
# 只读回放（无 LLM, 纯渲染存档 scenes[]）
# ---------------------------------------------------------------------------

def _replay_scene(scene: BondScene, picked: str | None, char_ms: int = _PARA_CHAR_MS) -> None:
    """渲染一个回放场景: 视觉标签 + 段落 + 选项（▶ 高亮当时选择）+ 结束语。"""
    _print_visual(scene)
    for para in scene.paragraphs:
        _type_paragraph(para, char_ms)
    if scene.choices:
        print("\n")
        for i, choice in enumerate(scene.choices, 1):
            mark = "▶" if choice == picked else " "
            print(f"  [{i}] {mark} {choice}")
        if picked in scene.choices:
            print("      ↑ 你当时的选择")
    if scene.is_end:
        print("\n── 羁绊剧情结束（回放）──")


def replay_bond_story(save_path: str | Path, char_ms: int = _PARA_CHAR_MS) -> bool:
    """只读回放一份羁绊剧情存档（无 LLM 调用, 纯渲染）。

    Returns:
        True  = 存档读取成功并完整回放
        False = 存档缺失/损坏（宁缺勿错, 不崩）
    """
    data = load_save(save_path)
    if not data:
        print(f"[系统] 无法读取存档: {save_path}")
        return False
    name = data.get("character_name") or data.get("character_id") or "?"
    status = "" if data.get("ended") else "（未完成）"
    print(f"── 回放羁绊剧情: {name} {status}──")
    if data.get("trigger_reason"):
        print(f"起因: {data['trigger_reason']}")
    for rec in data.get("scenes", []):
        _replay_scene(BondScene.from_dict(rec), rec.get("picked"), char_ms)
    return True


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
