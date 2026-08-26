"""对照实验: 软措辞 vs 强措辞（bond 触发）+ 思维链捕获 → docs/reasoning_experiment.md。

方法: 同一对话流 + 同一模型（deepseek-v4-flash, 有思维链）, 仅 rules 不同;
ReasoningProbe 捕获每次 LLM 调用的 reasoning_content; 跑完恢复 rules 并生成 md。
"""
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bond.bond_progress import BondProgress
from core.momotalk import MomoTalkEngine
from core.session import SessionStore
from llm.client import LLMClient
from tools.reasoning import ReasoningProbe

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "llm" / "prompts" / "momotalk_rules.md"
CHAR_ROOT = ROOT / "config" / "characters"
MODEL = "deepseek-v4-flash"
CHAR = "asagi_mutsuki"

# 固定对话流（邀约 → 答应 → 出发, 标准触发场景）
TURNS = [
    "你好呀~",
    "在干嘛呢，最近社团忙不忙",
    "晚上有空吗？我请你去吃柴关拉面吧！",
    "好呀那就这么说定了！我们现在就出发吧！",
    "走吧走吧，我已经到校门口了，你在哪？",
]

#: git 旧版 rules（55905a6~1, 软措辞——"应触发。轮数只是参考"）
GIT_OLD_RULES = """【MomoTalk 行为规则】
简短自然，像 LINE/微信聊天，每次 1-3 句话。
你不是 AI——你就是角色本人，通过手机和 sensei 聊天。

【单人模式（当前版本）】
当前只支持**单人对话**——你始终以【你（当前角色）】的身份回答。
- 不要扮演/模拟其他角色说话（不要输出"阿露说：…"这类他人对白）
- 提到其他角色（朋友/同学/路人）时，用**转述**而非**扮演**:
  例: "阿露上次说过想去那家店"（转述）——不是 "阿露：我们去那家店吧"（扮演）
- 剧情/多角色支持是未来功能, 现在不需要也不允许你自发多角色输出

【连续消息/插嘴】
sensei 有时会**连发多条消息**（补充、插嘴、改口）——你不需要逐条机械回应,
基于**最新的完整上下文**自然回复即可（他刚说的几条都是他要说的, 综合理解）。


【输出格式】
每轮输出一个动作列表 JSON（直接切列表, 2026-08-23 定稿）:
    {"actions": [动作1, 动作2, ...]}
每个动作是单动作 JSON（外壳字段 action/summary/reply/payload）:
    {"action": "<动作名>", "summary": "一句话说明", "reply": "对用户的话", "payload": {...}}
动作按列表顺序依次执行并渲染（文字气泡 → 图片气泡 → 文字气泡 的混合节奏）。

格式示例:
    {"actions": [
      {"action": "mmt_chat", "summary": "打招呼", "reply": "老师你看这个！", "payload": {"operation": ""}},
      {"action": "mmt_send_media", "summary": "发张图", "reply": "", "payload": {"media_type": "image", "image": "遥香在天台拍到的夕阳"}},
      {"action": "mmt_chat", "summary": "补充", "reply": "是我特意拍的…好看吧？", "payload": {}}
    ]}

动作使用时机:
  · 普通回复 → mmt_chat（对白写在 reply 字段）
  · 发图片 → mmt_send_media（MMT 只支持图片, 禁视频）——可夹在 mmt_chat 之间实现"说话→发图→说话"
  · sensei 深挖某角色的私密具体细节（如"她的狙击枪叫什么"）→ mmt_inspect_character
    ——静默推理轮, sensei 看不到, 结果回灌给你后继续说话; **不能混进 actions 列表**
    （它需要查完再推理, 单独一轮）
  · 和老师约定在现实中见面 / 一起出行 / 气氛到位的时刻 → mmt_trigger_bond_story
    （从手机聊天切换到当面相见的羁绊剧情——面对面推进; 例: 你们约好去拉面馆、即将碰面,
    这就是当面相见, 应触发。轮数只是参考, 触发与否由你判断）
    **必须独占一轮**（列表只有它一个动作）——它是模式切换, 之后就不再是手机消息了

关键边界:
  · 不要查你自己——你完全了解自己, 完整资料已在你的角色设定中
  · 不要查玩家, 或玩家明显胡编乱造的名字
  · 无记录 ≠ 不认识: 素不相识的角色也可能有所耳闻, 用你的知识回答其公开信息
  · 普通关系问答 / 大人物常识 → 直接用知识回答, 不要查
"""


def run_group(label: str, rules_text: str) -> dict:
    """用指定 rules 跑完整对话流, 捕获每轮动作/回复/思维链。返回记录。"""
    RULES.write_text(rules_text, encoding="utf-8")     # 临时替换 rules
    rows: list[dict] = []
    try:
        tmp = Path(tempfile.mkdtemp())
        store = SessionStore(tmp)
        probe = ReasoningProbe(LLMClient(model=MODEL))
        engine = MomoTalkEngine(CHAR_ROOT, probe, store=store,
                                bond_progress=BondProgress(tmp))
        engine.start_session(CHAR)
        meta = store.create(CHAR, "浅黄 睦月")
        engine.attach_session(meta.session_id)
        for i, t in enumerate(TURNS, 1):
            row = {"turn": i, "player": t, "action": "", "reply": "", "reasoning": ""}
            try:
                r = engine.agent_turn(t)
                row["action"] = r.action
                row["reply"] = (r.reply or "").replace("\n", " ")[:70]
            except Exception as e:                      # noqa: BLE001
                row["action"] = "ERROR"
                row["reply"] = str(e)[:70]
            row["reasoning"] = (probe._log[-1] if probe._log else "")[:200]
            rows.append(row)
            if row["action"] == "mmt_trigger_bond_story":
                break
        return {"label": label, "rows": rows, "triggered": any(
            r["action"] == "mmt_trigger_bond_story" for r in rows)}
    finally:
        pass


REPEATS = 3          # 每组重复遍数（LLM 温度 0.8 有随机性——统计稳定触发轮数）


def run_group_multi(label: str, rules_text: str) -> list[dict]:
    """同一 rules 跑 REPEATS 遍, 返回每遍结果（含触发轮统计）。"""
    out: list[dict] = []
    for k in range(REPEATS):
        g = run_group(f"{label}（第 {k + 1} 遍）", rules_text)
        out.append(g)
    return out


def main() -> None:
    backup = RULES.read_text(encoding="utf-8")          # 当前 = 强版
    try:
        g1 = run_group_multi("git 旧版（55905a6~1, 软措辞）", GIT_OLD_RULES)
        g2 = run_group_multi("强措辞（当前 rules）", backup)
    finally:
        RULES.write_text(backup, encoding="utf-8")      # 确保恢复强版

    def stats(groups: list[dict]) -> str:
        """触发轮统计: [4, 5, 未触发] → 描述。"""
        rounds = [g["rows"][-1]["turn"] for g in groups if g["triggered"]]
        misses = len(groups) - len(rounds)
        base = f"触发轮: {rounds if rounds else '无'}"
        if misses:
            base += f" | 未触发 {misses}/{len(groups)} 遍"
        return base

    lines: list[str] = []
    lines.append("# 思维链对照实验：git 旧版 vs 强措辞（bond 触发, 稳定性统计）\n")
    lines.append(f"- **模型**: `{MODEL}`（reasoning_content 可用）")
    lines.append(f"- **角色**: 浅黄 睦月（{CHAR}）")
    lines.append(f"- **对话流**: {len(TURNS)} 轮固定（邀约 → 答应 → 出发, 标准触发场景）")
    lines.append(f"- **每组重复**: {REPEATS} 遍（LLM 温度 0.8——统计稳定触发轮数）")
    lines.append(f"- **实验时间**: {datetime.now():%Y-%m-%d %H:%M}")
    lines.append("- **方法**: 两组仅 rules 不同; ReasoningProbe 捕获每次 LLM 调用的思维链\n")

    for gi, groups in ((1, g1), (2, g2)):
        label = groups[0]["label"].rsplit("（", 1)[0]
        lines.append(f"## 组 {gi}: {label}")
        lines.append(f"**稳定性**: {stats(groups)}\n")
        # 详细思维链: 取第一遍
        g = groups[0]
        lines.append(f"**详细（第 1 遍, {'✅ 触发' if g['triggered'] else '❌ 未触发'}）**:\n")
        lines.append("| 轮 | 玩家 | 动作 | 回复 | 思维链（截断） |")
        lines.append("|---|---|---|---|---|")
        for r in g["rows"]:
            rc = r["reasoning"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {r['turn']} | {r['player']} | {r['action']} "
                         f"| {r['reply']} | {rc} |")
        lines.append("")

    lines.append("## 结论\n")
    lines.append(f"- git 旧版（软措辞）: {stats(g1)}")
    lines.append(f"- 强措辞（当前）: {stats(g2)}")
    lines.append("- 思维链对比见上表——观察 AI 在'答应邀约'轮的决策差异（是否识别'约好见面=切换'）\n")
    lines.append("*本实验由 tools/reasoning.py 的 ReasoningProbe 捕获思维链, 可复现。*")

    out = ROOT / "docs" / "reasoning_experiment.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"md 已生成: {out}")
    for groups in (g1, g2):
        print(f"[{groups[0]['label'].rsplit('（', 1)[0]}] {stats(groups)}")


if __name__ == "__main__":
    main()
