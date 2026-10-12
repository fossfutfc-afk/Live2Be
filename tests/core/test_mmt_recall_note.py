"""⭐ N5 接线单测 —— 「你想起的事」真的进了 MMT 本轮的 messages（2026-09-29）。

与 `tests/core/test_momotalk_time_notes.py` 同一套桩口径（**脚本按 `task=` 分派**）。

VALUE: 这条测的是**接线与落点**（`agent_turn` 的 P19 槽位）, 不是召回质量本身
（那在 `test_wiki_recall.py`）。三个最容易静默错的地方各钉一条:

1. ⭐ **它必须落在动态尾, 不能拼进 system** —— 这一段的查询是**玩家这一句**,
   每轮都不同; 进了 system（盒 + brain 的稳定前缀）就**逐轮破上下文缓存**,
   而"稳定前缀"是体感主线的地基（`core/promptkit/tail.py` 的不变式）。
2. ⭐ **查询 = 本轮玩家输入**（不是她的上一句、不是窗口全文）——用"哪一条被想起"
   反着验: 两条 episode 各带一个词, 换一句话就该换一条出来。
3. 召回失败 / 空库 / 一条都不像 ⇒ **不注**（宁缺勿错: 少一段上下文, 剧情照走）。

⭐ **2026-10-12 起 P19 是两段**（`modes.MODES`: 先 `name` 名字段, 后 `turn` 兜底段）——
落在这一层的新判据有三条, 见文件末尾那三条用例（先后 / 去重 / 保留号不开段）。

⚠️ **后端一律走构造参数 `embed_fn=`（N5 接缝）, 不 patch 模块属性**:
`core.mmt.engine` 在 `tests/core/test_split_safety.py` 的 TARGETS 里, patch 模块属性
将来会**静默失效**（那条守门拦的就是这个）。这里给一个"一调就炸"的后端 ⇒
走**词面降级**（确定性, 不依赖本机有没有起 embedding 服务）。
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from core.brain import WikiStoreV2, make_node
from core.mmt.engine import MomoTalkEngine
from core.session.store import SessionStore
from llm import task_labels as T
from tests import stub_tasks

ROOT = Path(__file__).resolve().parents[2]
CHARACTER = "igusa_haruka"
HEADER = "【你想起的事"
#: 名字段的段头（2026-10-12 起带**钥匙** —— "你想着「老师用的那个词」"）
NAME_HEADER = "【你想着「"
#: 空手那句（钥匙扫到了、车道上一条也没有）
NAME_EMPTY = "一时没想起来"


def _no_embed():
    """确定性后端: 一调就炸 ⇒ `recommend_candidates` 自动退词面（tags/Dice）。"""
    def boom(texts):
        raise RuntimeError("embed backend off（本用例走词面降级）")
    return boom


class ScriptedLLM:
    def __init__(self):
        self.snapshots: list[list[dict]] = []

    def chat(self, messages, **kw):
        task = kw.get("task")
        self.snapshots.append([dict(m) for m in messages])
        reply = stub_tasks.annotation_reply(task, messages)
        if reply is not None:
            return reply
        if task in T.MAIN:
            return '{"text": "嗯……早、早上好！"}'
        raise stub_tasks.unknown_task(task)


def _engine(tmp_path, llm, *, embed_fn=_no_embed) -> MomoTalkEngine:
    store = SessionStore(data_root=tmp_path)
    eng = MomoTalkEngine(ROOT / "config" / "characters", llm, store=store,
                         embed_fn=embed_fn)
    name = eng.start_session(CHARACTER)
    root = store.create(CHARACTER, name)
    eng.attach_session(root.session_id)
    return eng


def _seed(tmp_path, text, *, title, tags, ts="2026-09-20T10:00:00") -> None:
    """写一条 episode 到真机同款位置（引擎是**另开一个 store** 读的, 所以要 save）。"""
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    st.add(make_node("episode", text=text, title=title, tags=list(tags), ts=ts,
                     significance=0.6, event_seq=[1]))
    st.save()          # ⚠️ `add` 只改内存


def _joined(llm: ScriptedLLM) -> str:
    return "\n".join((m.get("content") or "") for m in llm.snapshots[-1])


def test_recall_note_reaches_messages(tmp_path, caplog):
    """★ 召回到的那条（**带标题**）出现在本轮 messages 里；台账那一行记的也是标题。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午",
          title="苔藓的约定", tags=("杂草",))
    with caplog.at_level("INFO", logger="core.mmt.engine"):
        eng.agent_turn("我今天又去杂草屋那边了")
    joined = _joined(llm)
    assert HEADER in joined, joined[-500:]
    assert "《苔藓的约定》" in joined                 # ⭐ 标题 = 她要指的地址
    assert "老师陪我在杂草屋蹲了一下午" in joined
    # 台账（可 grep, 排查"这一轮摆了谁"的唯一线索）: 记的是**她看到的标题**,
    # 不是她看不到的编号 —— 2026-10-08 改走候选直传时这两格跟着换了写法。
    line = next(r.getMessage() for r in caplog.records
                if "mmt_recall" in r.getMessage())
    assert "eps=1" in line and "titles=苔藓的约定" in line, line
    print("    N5: 「你想起的事」进了 messages（带标题 · 台账同款）")


def test_recall_note_is_in_the_dynamic_tail_not_system(tmp_path):
    """⭐⭐ **落点守卫**: 它必须在 history 之后的动态尾, 且**不在**盒+brain 那条 system 里。

    进了 system = 每轮改一次前缀 ⇒ 上下文缓存逐轮全灭（`tail.py` 的不变式）。
    这条用例就是那个不变式的守门人。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午",
          title="苔藓的约定", tags=("杂草",))
    eng.agent_turn("我今天又去杂草屋那边了")
    msgs = llm.snapshots[-1]

    assert msgs[0]["role"] == "system"
    assert HEADER not in msgs[0]["content"], "召回段被拼进了 system（前缀缓存会逐轮失效）"
    idx_recall = next(i for i, m in enumerate(msgs)
                      if HEADER in (m.get("content") or ""))
    assert idx_recall > 0
    # 在 task 卡**之前**（时间事实 → 想起的事 → 目标层, 末位离生成最近）
    idx_card = next(i for i, m in enumerate(msgs)
                    if "本回合任务" in (m.get("content") or ""))
    assert idx_recall < idx_card, (idx_recall, idx_card)
    # 一轮里**只出现一次**（重复注入 = 白花一遍 token, 还会读成"两件事"）
    assert _joined(llm).count(HEADER) == 1
    print("    N5: 落点在动态尾（system 干净 / 在 task 卡之前 / 只出现一次）")


def test_query_is_this_player_line(tmp_path):
    """⭐ 查询 = **本轮玩家输入** —— 换一句话, 浮上来的就是另一条。

    这是"按当前对话召回"的**可观测**判据（比 spy 调用参数更强: 它同时钉住了
    "查询取的是这一句"和"召回结果真的随它变"）。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定", tags=("杂草",))
    _seed(tmp_path, "和老师去吃了高级料理", title="第一顿高级料理", tags=("料理",))

    eng.agent_turn("我今天又去杂草屋那边了")
    first = _joined(llm)
    assert "《苔藓的约定》" in first and "《第一顿高级料理》" not in first

    eng.agent_turn("上次那家餐厅的料理真好吃")
    second = _joined(llm)
    assert "《第一顿高级料理》" in second and "《苔藓的约定》" not in second
    print("    N5: 查询随玩家这一句变（杂草屋 → 苔藓 / 料理 → 高级料理）")


def test_p19_never_touches_the_embedder(tmp_path):
    """⭐⭐ **实时注入这条路一次都不许碰 embedding 后端**（2026-10-08 用户裁）。

    为什么单列一条: 它不是"召回质量"问题, 是**时延**问题 —— 语义那一路要每轮把整个库
    重新编码一遍（真档实测 **916 ms**, 而它同步跑在 `round_messages` 之前 ⇒ 直接进 TTFT;
    不跑后端那套同一句 **2 ms**）。所以这里放一个**记账的后端**: 一旦被调到, `calls` 就非空。

    ⚠️ 用"一调就炸"的后端是**测不出**这条的（`like` 会降级、测试照样绿）——
    必须记账。另外**档位本身**也要钉住: 只钉"引擎没传后端"不够 ——
    真正的开关是 `SPECS["turn"]` 里那个权重（把它写回 1.00 才是"接回去了"）。
    """
    from core.brain.read.like import SPECS
    calls: list = []

    def spy(texts):
        calls.append(texts)
        raise RuntimeError("实时注入不该调 embedding 后端")

    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm, embed_fn=lambda: spy)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定", tags=("杂草",))
    eng.agent_turn("我今天又去杂草屋那边了")
    assert dict(SPECS["turn"].parts).get("semantic") == 0.0, "实时档把语义接回来了"
    assert calls == [], calls                    # 一次都没调
    assert HEADER in _joined(llm)                # 而召回段照旧在（字面那套给的）
    print("    N5: 实时注入零后端调用（turn 档 semantic=0）")


def test_recall_note_silent_when_nothing_matches(tmp_path):
    """宁缺勿错: 空库 / 一条都不像 ⇒ **不注**（不返回一个空段头）。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    eng.agent_turn("今天天气不错")                    # 空库
    assert HEADER not in _joined(llm)

    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定", tags=("杂草",))
    eng.agent_turn("你昨天睡得好吗")                  # 有库, 但这句话跟它不像
    assert HEADER not in _joined(llm), _joined(llm)[-400:]
    print("    N5: 无命中 → 不注（宁缺勿错）")


def test_recall_query_is_truncated(tmp_path):
    """查询截断到 `RECALL_QUERY_CHARS` —— 长消息的后半段不进检索。"""
    from core.mmt import engine as engine_mod
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定", tags=("杂草",))
    # 关键词**落在截断点之后** ⇒ 不该被召回（钉子: 截断真的发生了）
    eng.agent_turn("啊" * engine_mod.RECALL_QUERY_CHARS + "杂草屋")
    assert HEADER not in _joined(llm)
    # 关键词在最前面 ⇒ 召回
    eng.agent_turn("杂草屋" + "啊" * engine_mod.RECALL_QUERY_CHARS)
    assert HEADER in _joined(llm)
    print(f"    N5: 查询截断到 {engine_mod.RECALL_QUERY_CHARS} 字")


def test_recall_uses_the_now_of_the_turn(tmp_path):
    """时间短语来自**本轮的 `now`**（与时间注记共用同一个"现在"）。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed(tmp_path, "老师陪我在杂草屋蹲了一下午", title="苔藓的约定",
          tags=("杂草",), ts="2026-09-20T10:00:00")
    eng.agent_turn("我今天又去杂草屋那边了",
                   now=datetime.fromisoformat("2026-09-21T10:00:00"))
    assert "〔《苔藓的约定》｜昨天｜9/20〕" in _joined(llm), _joined(llm)[-400:]
    print("    N5: 短语用本轮 now（昨天）")


# ---------------------------------------------------------------------------
# ⭐ 2026-10-12: P19 的第二段（形式 `name`, set 形状）—— 段头带**钥匙**, 空手也说话
# ---------------------------------------------------------------------------

def _seed_lane(tmp_path, *, titles: list[tuple[str, str]]) -> None:
    """一个人（**便利屋68/老师之外的新名字**）+ 挂他车道的经历（`about` 边, 正文可无名）。

    ⚠️ 两条夹具纪律（都踩过）:
      · **名字要避开**她人设表里的那些人（阿露/睦月/佳代子/纱织…）: 撞名会让
        `like.build_ctx` 的名字表 `setdefault` 命中**另一个** entity（车道是空的）——
        那种失败看起来很玄, 其实是夹具撞车。
      · **id 必须写死成非保留号**: 测试档里引擎不一定已经物化过 self/sensei
        （那一步在脑注入那次）, `next_id("x")` 于是把 `x0001`（= 老师）分给它 ⇒
        名字段被例外条款整条剔掉, 用例红得莫名其妙。
    """
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    person = make_node("entity", name="拉面店的老板", text="")
    person.id = "x0002"
    person.aliases = ["老板"]
    pid = st.add(person)
    for title, text in titles:
        eid = st.add(make_node("episode", text=text, title=title, tags=["拉面"],
                               ts="2026-10-05T10:00:00", significance=0.4, event_seq=[9]))
        st.add_edge("about", eid, pid, ts="2026-10-05T10:00:00")
    st.save()


def _seed_reserved(tmp_path) -> tuple[str, str]:
    """按 `ensure_entities` 的形状建出**保留号**（她自己 / 老师）+ 各一条车道经历。

    ⚠️ id 写死成 `entities.SELF_ID` / `SENSEI_ID` —— 例外条款是**按 id** 认的,
    换个号这条用例就测不到东西了（而且会静默绿）。
    """
    from core.brain.entities import SELF_ID, SENSEI_ID
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    me = make_node("entity", name="伊草 遥香")
    me.id = SELF_ID
    me.aliases = ["遥香"]
    st.add(me)
    sen = make_node("entity", name="老师")
    sen.id = SENSEI_ID
    sen.aliases = ["sensei"]
    st.add(sen)
    for owner, title, text, seq in ((SENSEI_ID, "跟老师那天", "老师陪我在杂草屋蹲了一下午", 10),
                                    (SELF_ID, "我自己那天", "我一个人在杂草屋发呆", 11)):
        eid = st.add(make_node("episode", text=text, title=title, tags=["杂草"],
                               ts="2026-10-05T10:00:00", significance=0.5, event_seq=[seq]))
        st.add_edge("about", eid, owner, ts="2026-10-05T10:00:00")
    st.save()
    return SELF_ID, SENSEI_ID


def test_name_form_opens_a_section_before_the_turn_section(tmp_path):
    """⭐ 老师这句提到一个名字 ⇒ 多一段「你想着「X」」, 且**排在兜底段之前**。

    三条判据一次钉住（每一条都是能静默错的地方）:
      · 名字段在（**含正文里没写"老板"二字**的那条 —— set 形状的语义）;
      · 段序 = 确定命中在前（`joined.index` 比先后, 不比长度）;
      · 同一条 episode **只出现一次**（`like` 的名字那一路也在加成 ⇒ 不剔就两段各摆一遍）。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed_lane(tmp_path, titles=[("多加叉烧", "老板多给了我一份叉烧"),      # 两段都会命中 ⇒ 去重靶子
                                 ("留了一份", "他说下次还给我留一份")])      # 只挂车道 ⇒ 名字段独有
    _seed(tmp_path, "他今天给我加了叉烧", title="别人也加了", tags=("料理",))
    eng.agent_turn("老板给我加叉烧了吗")
    joined = _joined(llm)

    assert NAME_HEADER in joined, joined[-600:]
    assert "你想着「老板」" in joined, "段头没印出**老师用的那个词**（钥匙）"
    assert "《留了一份》" in joined, "车道上的那条（正文没写他名字）没摆出来"
    assert joined.index(NAME_HEADER) < joined.index(HEADER), "两段的先后反了"
    assert joined.count("《多加叉烧》") == 1, "同一条 episode 被两段各摆了一遍"
    assert "《别人也加了》" in joined, "兜底段被名字段挤掉了"
    # 落点照旧: 两段都在动态尾, 不进 system（前缀缓存的地基）
    assert NAME_HEADER not in (llm.snapshots[-1][0].get("content") or "")
    print("    P19: 名字段在兜底段之前 · 跨段去重 · 车道全量（含正文无名的）")


def test_name_form_ignores_whitespace_in_the_name(tmp_path):
    """⭐ **空白不敏感**（2026-10-12）: 表上印的主名带空格, 老师话里没打空格**照样开段**。

    名表只印主名, 而卡上的主名中间就带一个空格（`陆八魔 阿露` / `浅黄 睦月` / …）
    ⇒ 若匹配要求逐字相同, 老师少打一个空格就**静默不开段**（这段的全部价值就在
    "引擎认得出那个词"）。
    ⚠️ 归一 = `entities.form_key`（去空白 + casefold）; 而**钥匙仍印存档里的写法**
    （`named` 的第二项 = 原写法）—— 段头要让她看见"引擎认的是这个名字"。
    ⚠️ 夹具**不带别名**: 带了"老板"这种短别名, 老代码也会命中, 用例就测不到东西了。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    person = make_node("entity", name="荞麦面 老板", text="")
    person.id = "x0002"                       # 非保留号（见 `_seed_lane` 的两条纪律）
    pid = st.add(person)
    eid = st.add(make_node("episode", text="他多给了我一份荞麦面", title="多加一份",
                           tags=["荞麦"], ts="2026-10-05T10:00:00",
                           significance=0.4, event_seq=[9]))
    st.add_edge("about", eid, pid, ts="2026-10-05T10:00:00")
    st.save()

    eng.agent_turn("荞麦面老板今天还开门吗")          # ⚠️ 查询里**没打**那个空格
    joined = _joined(llm)
    assert "你想着「荞麦面 老板」" in joined, joined[-600:]
    assert "《多加一份》" in joined
    print("    P19: 名字段空白不敏感（少打一个空格照样开段, 钥匙照印存档写法）")


#: 引擎内部地址的形状（`m0007` 节点 / `x0001` 对象 / `e0003` 认知）—— ⛔ 她的视图里一个都不许有
INTERNAL_ID = re.compile(r"(?<![0-9A-Za-z])[emx]\d{4}(?![0-9])")


def test_no_internal_ids_in_what_she_sees(tmp_path):
    """⭐ **编号永不进她的视图**（她看到的只有 `《标题》` 与名字）。

    `m0014` / `x0001` / `e0003` 是**引擎内部地址**; 漏进注入面她会照着抄进
    `{"noticed": "m0014"}`（永远指不中, 而且**静默**）。扫的是**整段注入文本**
    （system 里的 brain 段 + P19 三段 + user）—— 漏点通常是"新加的那一行忘了走渲染器",
    只看某一块是抓不到的。
    ⚠️ **防恒绿**: 同时断言夹具里**真的**有这些编号、而且 brain 段真的注进去了。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed_lane(tmp_path, titles=[("多加叉烧", "老板多给了我一份叉烧")])
    _seed(tmp_path, "他今天给我加了叉烧", title="别人也加了", tags=("料理",))
    # ⭐ 把 **brain 段**也注进来（`attach_session` 自己不注）—— 要让这条守门同时罩住
    #    "河 + 名表"那一块, 否则漏点只会在 P19 那三段里被抓到。
    eng._inject_brain(CHARACTER, eng._session_id)
    eng.agent_turn("老板给我加叉烧了吗")
    joined = _joined(llm)

    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    ids = sorted(n.id for n in st.all())
    assert any(INTERNAL_ID.match(i) for i in ids), ids          # 图里真有编号
    assert "我记得的事" in joined, joined[-400:]                  # brain 段真注进去了
    assert "我知道的名字" in joined, joined[-400:]                # 名表也在
    assert "多加叉烧" in joined, joined[-400:]                    # P19 真摆了东西
    leaked = sorted(set(INTERNAL_ID.findall(joined)))
    assert not leaked, f"这些内部编号漏进了她的视图: {leaked}"
    print(f"    P19: 整段注入文本里零内部编号（图里 {len(ids)} 个节点, 一个都没漏）")


def test_recall_log_says_which_sections_were_placed(tmp_path, caplog):
    """台账那一行要说得清**摆了几段/各几条/各多少字/花了多久**（排查"她这轮到底看见了什么"
    的唯一线索; 真机还要盯 `ms=` 随库长有没有恶化）。

    ⭐ `per=` 与 `chars=` 必须**自洽**（`per` 就是那几个段的字数, 按 `modes=` 同一套标签）——
    不然"哪一段把预算吃掉了"这个问题在日志里答不出来。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    _seed_lane(tmp_path, titles=[("多加叉烧", "老板多给了我一份叉烧")])
    _seed(tmp_path, "他今天给我加了叉烧", title="别人也加了", tags=("料理",))
    with caplog.at_level("INFO", logger="core.mmt.engine"):
        eng.agent_turn("老板给我加叉烧了吗")
    line = next(r.getMessage() for r in caplog.records if "mmt_recall" in r.getMessage())
    assert "modes=name+turn" in line and "name=1" in line and "eps=1" in line, line
    assert "titles=多加叉烧" in line, line
    # ⭐ 每段各多少字 + 召回耗时
    assert re.search(r"chars=\d+ per=\S+ ms=\d+\.\d", line), line
    total = int(re.search(r"chars=(\d+)", line).group(1))
    per_txt = re.search(r"per=(\S+)", line).group(1)
    labels = [item.split(":")[0] for item in per_txt.split("/")]
    per = [int(v.removesuffix("(empty)"))
           for v in (item.split(":")[1] for item in per_txt.split("/"))]
    assert labels == ["name", "turn"], per_txt      # 与 `modes=` 同一套标签
    assert sum(per) == total, (per_txt, per, total)
    print(f"    P19: 台账分清两段（{line.split('modes=')[1].split(' titles=')[0]}）"
          f" + per={per_txt}")


def test_empty_lane_prints_a_blank_line_only_when_a_name_was_mentioned(tmp_path, caplog):
    """⭐ 空手也要说话（2026-10-12 用户: *"即使思索了（词语）……"*）—— 但**只在真有钥匙时**。

    三件一次钉住:
      · 提了名字、车道上**一条也没有** ⇒ 印那句"一时没想起来"（**沉默有歧义**:
        "引擎没查"和"查了没有"在她眼里长得一样; 这句是她**能拿来说话的事实**）;
      · 没提名字（普通闲聊）⇒ ⛔ 不印（否则每轮收一句"你什么也没想起来"）;
      · ⭐ 而且那一轮的沉默必须是**判据**的结果, **不是兜底**的结果 —— 召回这条路上任何
        异常都会被 `agent_turn` 吞掉（宁缺勿错）, 光看"没印"分不出"正确地不印"和
        "炸了所以没印" ⇒ 这里连**日志**一起钉（变异验红时正是这一条抓的）。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    person = make_node("entity", name="拉面店的老板", text="")
    person.id = "x0002"
    person.aliases = ["老板"]
    st.add(person)                       # ⚠️ 只建人、**不挂任何经历** = 车道空
    st.save()

    eng.agent_turn("老板今天在店里吗")            # 有钥匙、无货
    joined = _joined(llm)
    assert NAME_HEADER in joined and NAME_EMPTY in joined, joined[-400:]
    assert "你想着「老板」" in joined

    caplog.clear()
    with caplog.at_level("WARNING", logger="core.mmt.engine"):
        eng.agent_turn("今天天气不错")            # 没钥匙 ⇒ 空手也不印
    assert NAME_EMPTY not in _joined(llm), _joined(llm)[-400:]
    assert "每轮召回失败" not in caplog.text, caplog.text   # ⛔ 沉默不是"炸了"
    print("    P19: 空手只在真有钥匙时说话（提了名字没人 / 闲聊不响且不靠兜底）")


def test_when_form_opens_a_section_and_dedup_keeps_it_honest(tmp_path):
    """⭐ 三段的顺序与**去重掏空 ≠ 空手**（2026-10-12 的 `when` 形式）。

    老师一句同时点名 + 点时间 ⇒ 名字段与时间窗段指着**同一条经历**:
      · 段序 = `name` → `when` → `turn`（确定命中在前, 兜底在后）;
      · 那条归**名字段**（先到先得）;
      · ⛔ 时间窗那段**一个字都不印** —— 它空是因为"被前一段拿走了", 不是"没想起来",
        印空手就是**假话**（`empty_ok` 那一格）。
    """
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    now = datetime.fromisoformat("2026-10-12T21:00:00")          # 周一; 上周 = 10/5..10/11
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    person = make_node("entity", name="拉面店的老板", text="")
    person.id = "x0002"
    person.aliases = ["老板"]
    st.add(person)
    both = st.add(make_node("episode", text="老板多给了我一份叉烧", title="上周加叉烧",
                            ts="2026-10-07T10:00:00", significance=0.5, event_seq=[20]))
    st.add_edge("about", both, "x0002", ts="2026-10-07T10:00:00")
    st.add(make_node("episode", text="老板上周也给我加了叉烧", title="别人也加了",
                     ts="2026-09-20T10:00:00", significance=0.5, event_seq=[21]))
    st.save()

    # ① 上周里**只有**他车道那一条 ⇒ 名字段先拿走, 时间窗段被掏空 ⇒ ⛔ 一个字都不印
    eng.agent_turn("老板上周给我加叉烧了吗", now=now)
    joined = _joined(llm)
    assert joined.index(NAME_HEADER) < joined.index(HEADER), "名字段不在兜底段之前"
    assert "你想着「老板」" in joined and "《上周加叉烧》" in joined, joined[-600:]
    assert joined.count("《上周加叉烧》") == 1, "同一条被两段各摆了一遍"
    assert "你想着「上周」那阵子" not in joined, "被去重掏空的那段印了空手（那是假话）"
    assert "《别人也加了》" in joined, "兜底段被挤掉了"
    # ② 上周里再添一条**不在他车道**的 ⇒ 两段同时有货, 这才能钉两者的先后
    _seed(tmp_path, "上周的课排得很满", title="上周的课", tags=("课",),
          ts="2026-10-09T10:00:00")
    eng.agent_turn("老板上周都忙什么了", now=now)
    both = _joined(llm)
    assert "你想着「老板」" in both and "你想着「上周」那阵子" in both, both[-600:]
    assert both.index("你想着「老板」") < both.index("你想着「上周」那阵子"), "两段先后反了"
    assert "《上周的课》" in both, "时间窗里那条（不在他车道上）没摆出来"
    print("    P19: 三段顺序 name→when→turn · 去重掏空的那段不说话")


def test_when_section_says_so_when_that_window_is_empty(tmp_path):
    """⭐ 时间窗**真**空（那阵子一条都没有）⇒ 印空手那句; 闲聊里没有时间词 ⇒ 什么都不印。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    now = datetime.fromisoformat("2026-10-12T21:00:00")
    _seed(tmp_path, "在杂草屋蹲了一下午", title="苔藓的约定", tags=("杂草",),
          ts="2026-09-20T10:00:00")
    eng.agent_turn("上周我们都干什么了", now=now)
    joined = _joined(llm)
    assert "你想着「上周」那阵子" in joined and "那几天的事，一时没想起来" in joined, joined[-500:]
    eng.agent_turn("今天的天气不错", now=now)      # ⚠️ "今天"是**还没过完**的窗口 ⇒ 不算旧事
    assert "你想着「今天」" not in _joined(llm), _joined(llm)[-400:]
    print("    P19: 时间窗真空 ⇒ 空手说话; 「今天」不算旧事（不许摆）")


def test_blank_line_is_marked_in_the_ledger(tmp_path, caplog):
    """空手那一轮，台账要标 `name(empty)` —— 否则"摆了一段"与"摆了一句空手"在日志里一样。"""
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    st = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    person = make_node("entity", name="拉面店的老板", text="")
    person.id = "x0002"
    person.aliases = ["老板"]
    st.add(person)
    st.save()
    with caplog.at_level("INFO", logger="core.mmt.engine"):
        eng.agent_turn("老板今天在店里吗")
    line = next(r.getMessage() for r in caplog.records if "mmt_recall" in r.getMessage())
    assert "name(empty)" in line and "name=0" in line, line
    print(f"    P19: 空手在台账里看得见（{line.split('modes=')[1].split(' chars=')[0]}）")


def test_reserved_names_do_not_open_the_name_section(tmp_path):
    """⛔ 她自己 / 老师的名字**不算"提到了谁"**（`modes.RESERVED_TRIGGERS`）。

    ⚠️ **前提自己验**: 保留号真被字面命中了才算测到（否则名字表里压根没这两行 ⇒
    用例会**假绿**）。老师几乎连着每一件事 ⇒ 少了这一格, 一句"老师你觉得呢"
    就能把整条河摆进动态尾, 还顶着"你想着…"这个抬头。
    """
    from core.brain.read.like import RecallCtx, build_ctx
    llm = ScriptedLLM()
    eng = _engine(tmp_path, llm)
    self_id, sensei_id = _seed_reserved(tmp_path)
    now = datetime.fromisoformat("2026-10-12T21:00:00")
    wstore = WikiStoreV2(tmp_path, world_id="world1", char_id=CHARACTER)
    for q, want in (("遥香你在吗", self_id), ("老师你觉得呢", sensei_id)):
        base = build_ctx(wstore, RecallCtx(now=now, query=q), active=[])
        assert want in base.named, f"前提不成立（{q} 没命中 {want}）—— 这条用例会假绿"
        eng.agent_turn(q, now=now)
        assert NAME_HEADER not in _joined(llm), q
    print(f"    P19: 保留号（{self_id}/{sensei_id}）不触发名字段")
