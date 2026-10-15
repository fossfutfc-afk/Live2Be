"""召回旋钮与召回台账（DESIGN_WIKI_V3 §3.1/§3.5, V3-0 2026-09-13）。

V3-0 只做两件事、且**行为零变化**：
  ① 把记忆召回的旋钮从模块常量搬到 `settings.toml [recall]`（默认 = 原值）
  ② 给两条此前完全不可观测的路径加台账（写路径候选碰撞 / 读路径注入视图）

本文件钉住这两件事的**契约**：
    - 旋钮: 默认值 / 配置文件覆盖 / 坏值不炸 / 未知键报错 / 缓存可重载
    - 台账: 不抛异常、格式含关键字段、forced 比例算对、桶统计如实反映渲染
    - **零行为变化**: 不配 [recall] 时 `recommend_candidates` 与 v2 同口径
"""
import logging
import sys
from pathlib import Path

import pytest

from core.brain import recall_config as rc
from core.brain import recall_ledger as rl
from core.brain.nodes import make_node
from core.brain.read.render import render_character_view, take_last_view_account
from core.brain.store import WikiStoreV2
from infra import settings


@pytest.fixture(autouse=True)
def _drain_view_account():
    """每个用例前**抽干** `_last_view_account`（模块级状态, 跨文件会串）。

    生产里每次渲染后调用方都会取走（`_log_read_ledger`），所以正常不积压;
    但别的测试文件渲染完不取 → 残留会污染本文件的"取走即清空"断言。
    **测试不该造生产不会产生的状态**——这里按生产语义清干净。
    """
    while take_last_view_account() is not None:
        pass
    yield
    while take_last_view_account() is not None:
        pass


# ---------------------------------------------------------------------------
# 旋钮
# ---------------------------------------------------------------------------

def test_no_threshold_knobs_left():
    """★ T17（2026-09-15）: **三个阈值旋钮已删** —— 配置面不再有任何"阈值"。

    用户裁决 *"cand_high 相关全删掉"*（落地 Q11/Q31/Q32）。留下的旋钮只有
    "取几条"（`cand_k`/`sim_k`）与"半衰期/下界"（`time_half_life_*`）。

    ⚠️ **`time_freshness_floor`（2026-09-17 新增）不是阈值**: 阈值是"过线/不过线"
    的**硬闸门**（`cand_high` 就是那样把新认知永远掐死的）; 而 `floor` 是
    `freshness` 曲线的**渐近下界**, 只影响分数不影响准入 —— 排序仍然全量参与。

    ⚠️ **`turn_k` / `turn_budget`（N5, 2026-09-29 新增）也不是阈值**:
    它们是 `cand_k` 那一类（"取几条"）——`turn_budget` 是**装填停止条件**
    （按字符累计到预算就少摆一条）, 一条已经命中的 episode **不会**因为分数低
    被它丢掉（"准入"这件事在这一层根本不存在: 命中即摆, 只是摆不下几条）。

    ⚠️ **`like_k`（2026-10-08 新增）也不是阈值**: 它是 `like()` 的签名缺省（"取几条"）。
    `like` 里那条**准入**（内容轴 > 0）是**代码规则不是旋钮** —— 配置面只留"取几条"
    与"半衰期/下界"。
    """
    from core.brain.read import like as L
    from core.brain.read import recall as R
    snap = rc.snapshot()
    assert set(snap) == {"cand_k", "sim_k", "like_k", "turn_k", "turn_budget",
                         "time_half_life_days", "time_freshness_floor"}, snap
    assert snap["cand_k"] == float(R.CAND_K) == 3.0
    assert snap["turn_k"] == float(R.TURN_K) == 2.0
    assert snap["like_k"] == float(L.LIKE_K) == 3.0
    for gone in ("cand_high", "cand_med", "accept_hit_rate"):
        assert gone not in snap
        assert not hasattr(R, gone.upper())
        try:
            rc.get(gone)
            raise AssertionError(f"{gone} 仍可读——没删干净")
        except KeyError:
            pass                              # 未知键 → KeyError（防拼错静默走默认）
    print("    旋钮: cand_k/sim_k/like_k/turn_k/turn_budget/time_half_life_days/"
          "time_freshness_floor（三个阈值已删）")


def test_time_half_life_default_and_override(tmp_path, monkeypatch):
    """`time_half_life_days`（A 链路新鲜度半衰期）——默认 5 **现实日** + 可覆盖。

    语义钉住: **新鲜度不是遗忘曲线**（用户裁决 2026-09-13）——
    所以默认值必须是"一周上下"的量级, 而不是遗忘曲线的 60 天。

    ⚠️ 单位是**现实日**, 不是"叙事日"（本用例原先写错, 2026-09-17 时间轴换代后
    叙事日已不存在）。
    """
    assert rc.DEFAULTS["time_half_life_days"] == 5.0
    p = tmp_path / "settings.toml"
    p.write_text("[recall]\ntime_half_life_days = 12\n", encoding="utf-8")
    monkeypatch.setenv("LIVE2BE_SETTINGS", str(p))
    assert rc.get("time_half_life_days") == 12.0
    # 坏值 → 默认（不抛）
    p.write_text('[recall]\ntime_half_life_days = "long"\n', encoding="utf-8")
    assert rc.get("time_half_life_days") == 5.0
    print("    旋钮: time_half_life_days 默认 5.0（现实日）+ 覆盖/坏值回落")


def test_freshness_floor_knob(tmp_path, monkeypatch):
    """`time_freshness_floor`（2026-09-17 新增）—— 默认 0.25 + 可覆盖 + 可关掉。

    `0.0` = 关掉下界（回到换代前的行为: 老记忆掉到 10⁻²²）。
    """
    assert rc.DEFAULTS["time_freshness_floor"] == 0.25
    p = tmp_path / "settings.toml"
    p.write_text("[recall]\ntime_freshness_floor = 0.0\n", encoding="utf-8")
    monkeypatch.setenv("LIVE2BE_SETTINGS", str(p))
    assert rc.get("time_freshness_floor") == 0.0     # 显式关掉（不是回落默认）
    p.write_text('[recall]\ntime_freshness_floor = "low"\n', encoding="utf-8")
    assert rc.get("time_freshness_floor") == 0.25    # 坏值 → 默认
    print("    旋钮: time_freshness_floor 默认 0.25 / 0.0 可关 / 坏值回落")


def test_settings_override(tmp_path, monkeypatch):
    """`[recall]` 覆盖生效（这是 V3-0 存在的理由: 按模型标定不必改代码）。"""
    p = tmp_path / "settings.toml"
    p.write_text("[recall]\ncand_k = 2\nsim_k = 8\n", encoding="utf-8")
    monkeypatch.setenv("LIVE2BE_SETTINGS", str(p))
    assert rc.get("cand_k") == 2.0
    assert rc.get("sim_k") == 8.0
    # 未配的键保持默认
    assert rc.get("time_half_life_days") == rc.DEFAULTS["time_half_life_days"]
    print("    旋钮: [recall] 覆盖生效 + 未配键保持默认")


def test_bad_values_fall_back(tmp_path, monkeypatch):
    """坏值/坏文件**不得**炸（宁缺勿错——配置层绝不能阻断对话或 digest）。"""
    p = tmp_path / "settings.toml"
    p.write_text('[recall]\nsim_k = "many"\ncand_k = true\n', encoding="utf-8")
    monkeypatch.setenv("LIVE2BE_SETTINGS", str(p))
    assert rc.get("sim_k") == rc.DEFAULTS["sim_k"], "字符串应被拒"
    assert rc.get("cand_k") == rc.DEFAULTS["cand_k"], "bool 应被拒（不是数值）"

    # 文件损坏 → 全默认
    p.write_text("[recall\n 这行不是合法 toml", encoding="utf-8")
    assert rc.get("sim_k") == rc.DEFAULTS["sim_k"]
    print("    旋钮: 类型不符/TOML 损坏 → 回落默认, 不抛")


def test_unknown_key_raises():
    """未知键报错——防拼错后静默走默认（那会让标定白做）。"""
    with pytest.raises(KeyError) as e:
        rc.get("cand_hihg")
    assert "cand_k" in str(e.value)
    print("    旋钮: 未知键 KeyError（并列出可用键）")


def test_file_change_takes_effect_without_restart(tmp_path, monkeypatch):
    """手改 settings.toml 后，下一次读就是新值（按 mtime 失效，不必重启/reload）。

    2026-10-15 改语义：从前这里断言的是"未 reload 应命中缓存"（进程级懒加载缓存）。
    现在读盘由 `infra/settings` 按 mtime 缓存 ⇒ 文件一动就失效，这正是要的行为
    （从前改了 `[recall]` 不重启不生效，而没有任何地方写着这件事）。
    """
    p = tmp_path / "settings.toml"
    monkeypatch.setenv("LIVE2BE_SETTINGS", str(p))
    p.write_text("[recall]\nsim_k = 5\n", encoding="utf-8")
    assert rc.get("sim_k") == 5.0
    p.write_text("[recall]\nsim_k = 8\n", encoding="utf-8")
    assert rc.get("sim_k") == 8.0, "文件改了就该读到新值（不必重启）"
    print("    旋钮: 改文件即生效（mtime 失效）+ reload 仍可用")


# ---------------------------------------------------------------------------
# 台账
# ---------------------------------------------------------------------------

def test_collision_account_reports_coverage(caplog):
    """写路径台账（T17 后）: 报**候选覆盖度**，不再报 forced 比例。

    `forced%` 随结构强制一起删了——它观测的是"阈值把全部 episode 判成同一件事"
    那个失效模式，而闸门本身已取消。留下的告警是**反向**的:
    `⚠no_candidate`（一条候选都抬不出来 → 查 embedding 后端或空库）。
    """
    with caplog.at_level(logging.INFO, logger="live2be.brain"):
        acc = rl.CollisionAccount("igusa_haruka")
        for _ in range(4):
            acc.episode(n_cand=3, best_sim=0.92)
        acc.mode = "semantic"
        acc.log(thr_k=3)
    line = next(r.message for r in caplog.records if r.message.startswith("recall_write"))
    assert "collide=100%" in line and "mode=semantic" in line and "k=3" in line
    assert "char=igusa_haruka" in line and "eps=4" in line
    assert "forced" not in line and "⚠" not in line

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="live2be.brain"):
        acc2 = rl.CollisionAccount("x")
        for _ in range(4):
            acc2.episode(n_cand=0, best_sim=0.0)      # 一条都抬不出来
        acc2.log(thr_k=3)
    line2 = next(r.message for r in caplog.records if r.message.startswith("recall_write"))
    assert "collide=0%" in line2 and "⚠no_candidate" in line2
    print("    台账: 候选覆盖度 + ⚠no_candidate（forced 已随阈值一起删）")


def test_collision_account_disabled(caplog):
    """开关关掉 → 不打点（测试/离线跑时静音）。"""
    with caplog.at_level(logging.INFO, logger="live2be.brain"):
        rl.ENABLED = False
        try:
            rl.CollisionAccount("x").log(thr_k=3)
        finally:
            rl.ENABLED = True
    assert not [r for r in caplog.records if r.message.startswith("recall_write")]
    print("    台账: 关闭开关后静音")


def test_log_read_format(caplog):
    """读路径台账含 total/picked/dropped/buckets（回答"这轮给了 LLM 哪几条"）。"""
    with caplog.at_level(logging.INFO, logger="live2be.brain"):
        rl.log_read(char_id="igusa_haruka", total=8, picked=5,
                    buckets={"belief": "4/5", "episode": "1/6"}, mode="off")
    line = next(r.message for r in caplog.records if r.message.startswith("recall_read"))
    assert "total=8 picked=5 dropped=3" in line
    assert "belief:4/5" in line and "episode:1/6" in line
    assert "surface=chara" in line
    print("    台账: 读路径口径（total/picked/dropped/buckets）")


def test_ledger_never_raises(caplog):
    """台账是观测层——**任何**畸形输入都不得抛（坏了不能阻断剧情）。"""
    with caplog.at_level(logging.INFO, logger="live2be.brain"):
        rl.CollisionAccount("x").log(thr_k=3)                         # 0 episode
        rl.log_read(char_id="", total=0, picked=0, buckets={})        # 空
    print("    台账: 空/畸形输入不抛")


# ---------------------------------------------------------------------------
# 渲染层记账（读路径的事实来源）
# ---------------------------------------------------------------------------

def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path)
    st.add(make_node("episode", text="老师约我去看杂草。", title="看杂草",
                     significance=0.7, tags=["杂草"]))
    st.add(make_node("episode", text="我给草取了名字。", title="取名字",
                     significance=0.6, tags=["命名"]))
    st.add(make_node("belief", subject="被老师需要", text="只要老师需要我就会答应。",
                     significance=0.8,
                     tags=["老师"]))
    return st


def test_render_records_view_account(tmp_path):
    """`render_character_view` 记下桶统计, 且**取走即清空**（消费语义）。

    台账的全部价值在于"如实反映 LLM 看到了什么"——所以它必须与渲染共用同一份
    分桶结果（同一实现 `_bucket_view`），不能另算一遍。
    """
    st = _store(tmp_path)
    txt = render_character_view(st.all(), char_name="伊草 遥香")
    acct = take_last_view_account()
    assert acct is not None, "渲染后应有台账"
    assert acct["total"] == len(st.all())
    buckets = acct["buckets"]
    assert buckets["belief"] == 1, buckets           # 1 条 belief（cap 已删 → 桶内全量）
    assert buckets["episode"] == 2, buckets          # 2 条 episode
    picked = sum(buckets.values())
    assert picked == 3
    # 文本里确实能读到这些内容（台账与文本同源）
    assert "我心里渐渐觉得" in txt and "被老师需要" in txt
    assert take_last_view_account() is None, "取走应清空"
    print("    渲染: 桶统计入账 + 取走即清空")


def test_bucket_summary_matches_text(tmp_path):
    """桶统计必须与文本一致（防"台账好看、文本没给"这类漂移）。

    2026-09-13 cap 全删后：桶内即全量，`picked == total`（不再有被砍掉的分母）。
    """
    st = _store(tmp_path)
    txt = render_character_view(st.all(), char_name="遥香")
    acct = take_last_view_account()
    n_belief = acct["buckets"]["belief"]
    assert n_belief == 1 and "我心里渐渐觉得" in txt
    assert sum(acct["buckets"].values()) == acct["total"], "cap 删后不应再有未注入的节点"
    print("    渲染: 桶统计与文本一致（桶内全量, picked==total）")
