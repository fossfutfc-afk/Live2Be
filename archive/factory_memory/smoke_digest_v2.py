"""digest v2 真 LLM 冒烟: 至少两轮真实最小 unit（mmt→bond→finish）× digest。

流程:
    1. 世界线: experiments/out/smoke_digest_v2/{world}/（每次重建）
    2. seed_from_config(遥香出厂基座) → store.audit() 必须干净
    3. 两轮 unit, 事件形态与真实引擎一致（make_event 同款 payload）:
       Round 1: mmt 闲聊 → vn_enter → bond 剧情(公园) → vn_exit → digest
       Round 2: 玩家回环提问"还记得公园那天吗" → bond(夜谈) → vn_exit → digest
       （第二轮考验: 召回旧记忆 → LLM 组织/链接/accrue 的碰撞能力）
    4. 每轮 digest 后: 报告 created/evidence/好感/LLM 输出原文 → audit 必须干净
    5. 两轮后: 打印角色视图样例（记忆分层渲染效果）

用法（需 .env/settings.toml 的 LLM key）:
    $env:NO_PROXY='api.deepseek.com,*'
    python experiments/smoke_digest_v2.py
退出码: 0 = 两轮全过; 非 0 = 某轮失败。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from core.brain import (
    WikiStoreV2,
    digest_segment,
    render_character_view,
    seed_from_config,
)
from core.parsing.dynamic_character_parser import CharacterLoader
from core.session import make_event
from llm.client import LLMClient

OUT = Path("experiments/out/smoke_digest_v2")
CHAR = "igusa_haruka"
WORLD = "smoke-world1"

#: digest 全程时间预算（实验放宽——high 档单次长考可能数分钟; 生产默认 150s）
DEADLINE_SECONDS = 900.0

FAILS: list[str] = []


def report(title: str, body: str = "") -> None:
    print(f"\n=== {title} ===")
    if body:
        print(body)


def audit_or_fail(store: WikiStoreV2, stage: str) -> None:
    problems = store.audit()
    if problems:
        FAILS.append(f"{stage}: audit 不干净: {problems}")
        report(stage, "❌ AUDIT 违规:\n" + "\n".join(f"- {p}" for p in problems))
    else:
        report(stage, "✅ audit 干净")


def ev(seq: int, typ: str, sub: str, payload: dict):
    e = make_event(typ, sub, payload)
    e.seq = seq
    return e


def unit1_events(start: int) -> list:
    """Round 1: 公园散步的最小 unit（mmt → bond → finish）。"""
    return [
        ev(start + 1, "mmt", "chat", {
            "player": "遥香，明天放假，要不要一起去公园走走？最近天气很好。",
            "reply": "公、公园？和老师一起……！好、好的！我会努力的！（小声）不会搞砸的……"})
        if False else ev(start + 1, "mmt", "chat", {
            "player": "遥香，明天放假，要不要一起去公园走走？最近天气很好。",
            "reply": "公、公园……和老师两个人去……？好、好的！我会努力不搞砸的！"}),
        ev(start + 2, "marker", "vn_enter", {}),
        ev(start + 3, "bond", "story_scene", {
            "input": "",
            "place": "city_park",
            "paragraphs": [
                {"text": "老师在公园长椅上坐下，遥香抱着保温杯站在旁边，紧张得手指绞着衣角。", "emotion": "nervous"},
                {"text": "「遥香，坐下来一起喝点热茶吧。」老师说。她小心翼翼地坐下，隔着一个拳头的距离。", "emotion": "shy"},
                {"text": "一只流浪猫走过来蹭老师的裤脚，遥香的眼睛一下子亮了，又不敢出声。", "emotion": "surprised"},
                {"text": "「你很喜欢猫吗？」「嗯……猫不会嫌弃我。杂草和猫，都不会嫌弃我……」她说完就慌了神，「啊、不是、我是说……！」", "emotion": "flustered"},
                {"text": "老师没有笑话她，只是把猫轻轻抱到她腿边。「它想认识你。」遥香小心翼翼地伸出手，猫蹭了蹭她的手指。她愣住，眼眶悄悄红了。", "emotion": "moved"},
            ]}),
        ev(start + 4, "bond", "story_end", {"paragraphs": [
            {"text": "回家路上，遥香一路都低着头，却在嘴角藏着一个很小的笑。", "emotion": "happy"}]}),
        ev(start + 5, "marker", "vn_exit", {}),
    ]


def unit2_events(start: int) -> list:
    """Round 2: 玩家回环提问 + 深夜天台夜谈（考验召回碰撞: 提到公园/猫/杂草）。"""
    return [
        ev(start + 1, "mmt", "chat", {
            "player": "遥香，还记得上次在公园的那只猫吗？它昨天又出现在夏莱门口了！",
            "reply": "诶——！是那只、蹭老师裤脚的那只吗……？它、它还记得老师……（声音越来越小）也、也不知道它还记不记得我……"}),
        ev(start + 2, "mmt", "chat", {
            "player": "当然记得你啦，它今天还让我带话呢——说想再见到遥香。",
            "reply": "呜……（把脸埋进围巾里）那、那明天我给它带猫粮……啊，老师说可以吗？"}),
        ev(start + 3, "marker", "vn_enter", {}),
        ev(start + 4, "bond", "story_scene", {
            "input": "",
            "place": "school_rooftop",
            "paragraphs": [
                {"text": "傍晚的天台，遥香带着一袋猫粮和一个小碗，认真地把猫粮倒进碗里，摆得端端正正。", "emotion": "focused"},
                {"text": "猫果然来了，绕着她的脚转了两圈，才低头吃。遥香蹲在旁边看着，眼睛里亮亮的。", "emotion": "warm"},
                {"text": "「老师……我小时候，没有人愿意和我玩。杂草、猫，还有老师……都是第一个。」她说得很轻，「所以我会好好珍惜的。真的。」", "emotion": "sincere"},
                {"text": "老师伸手揉了揉她的头。她没躲，只是耳朵尖红透了，小声说：「老师是第一个……这样摸我头的人。」", "emotion": "shy"},
                {"text": "「以后想被摸头的时候，随时都可以来找老师。」遥香猛地抬头，张了张嘴，最后只是用力点了点头，把脸埋进膝盖里。", "emotion": "moved"},
            ]}),
        ev(start + 5, "bond", "story_end", {"paragraphs": [
            {"text": "太阳落山前，猫吃饱走了。遥香站起来，认真地对老师说：「下次，我想带老师去看我的杂草屋。」", "emotion": "determined"}]}),
        ev(start + 6, "marker", "vn_exit", {}),
    ]


def run_unit(store: WikiStoreV2, llm, events: list, label: str,
             character_prompt: str, extra_body: dict | None = None) -> bool:
    """跑一个最小 unit 的 digest; 返回是否成功。"""
    import time as _time
    t0 = _time.monotonic()
    report(f"{label}: 事件 {len(events)} 条 (seq {events[0].seq}~{events[-1].seq})")
    try:
        res = digest_segment(
            store, llm, events,
            character_prompt=character_prompt,
            temperature=0.3, max_tokens=8192,
            deadline_seconds=DEADLINE_SECONDS,       # 实验档放宽（high 长考）
            extra_body=extra_body,
        )
    except Exception as e:                       # noqa: BLE001
        FAILS.append(f"{label}: digest 异常: {e}")
        report(label, f"❌ digest 异常: {e}")
        return False
    elapsed = _time.monotonic() - t0
    if not res.ok:
        FAILS.append(f"{label}: digest 失败: {res.errors}")
        report(label, f"❌ digest 失败（{elapsed:.0f}s）:\n"
               + "\n".join(f"- {e}" for e in res.errors))
        return False
    kinds = {}
    for n in store.all():
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    body = [
        f"✅ ok  llm_calls={res.llm_calls}  耗时 {elapsed:.0f}s  好感 +{res.affection_delta}",
        f"   新建条目: {res.created or '（无）'}",
        f"   evidence: {res.evidence or '（无）'}",
        f"   库内节点: {kinds}（共 {len(store.all())}）",
        f"   水位: digested_seq={store.digested_seq}",
    ]
    if llm.last_reasoning:
        body.append(f"   思维链(尾 200): {llm.last_reasoning[-200:]}")
    report(label, "\n".join(body))
    audit_or_fail(store, label)
    return True


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    store = WikiStoreV2(OUT, world_id=WORLD, char_id=CHAR)

    # 出厂基座
    seed = seed_from_config(store, f"config/characters/{CHAR}")
    report("Step 0 出厂 digest", f"created={len(seed.created)} errors={seed.errors or '无'}")
    audit_or_fail(store, "seed 后")

    # 锚点（盒B 风格: profile+personality）
    char = CharacterLoader("config/characters").load(CHAR)
    character_prompt = char.build_prompt("bond_story")

    llm = LLMClient(timeout=300)
    # 模型 = 客户端默认（settings.toml/.env, 当前 deepseek-v4-flash, thinking）;
    # reasoning_effort = argv[1]（low|medium|high, 默认 low——digest 生产默认）;
    # timeout 300s 防 high 档单次长考被掐断
    import sys as _sys
    effort_name = _sys.argv[1] if len(_sys.argv) > 1 else "low"
    effort = {"reasoning_effort": effort_name}
    report("effort", f"reasoning_effort={effort_name}（low|medium|high）")
    ok1 = run_unit(store, llm, unit1_events(10), "Round 1 unit（公园散步）",
                   character_prompt, extra_body=effort)
    if ok1:
        ok2 = run_unit(store, llm, unit2_events(30), "Round 2 unit（天台夜谈）",
                       character_prompt, extra_body=effort)
    else:
        ok2 = False
        FAILS.append("Round 2 跳过（Round 1 失败）")

    if ok1 and ok2:
        report("角色视图样例（记忆注入效果）",
               render_character_view(store.all(), char_name="伊草遥香",
                                     summary="和遥香在基沃托斯一起度过的日子"))
        report("最终审计", "✅ 两轮 digest 全过, 图不变量全程干净")
    print("\n" + ("❌ 冒烟失败:\n" + "\n".join(f"- {f}" for f in FAILS)) if FAILS
          else "\n✅ 冒烟通过: 两轮真实最小 unit 全过")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
