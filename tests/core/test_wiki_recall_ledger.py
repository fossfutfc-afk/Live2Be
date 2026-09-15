# -*- coding: utf-8 -*-
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.brain.wiki_v2 import recall_config as rc            # noqa: E402
from core.brain.wiki_v2 import recall_ledger as rl            # noqa: E402
from core.brain.wiki_v2.nodes import make_node               # noqa: E402
from core.brain.wiki_v2.render import (                      # noqa: E402
    render_character_view, take_last_view_account)
from core.brain.wiki_v2.store import WikiStoreV2             # noqa: E402


@pytest.fixture(autouse=True)
def _clean_config():
    """每个用例前后清缓存——否则用例间会串（recall_config 是进程级懒加载）。"""
    rc.reload()
    yield
    rc.reload()


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

def test_defaults_match_v2_constants():
    """默认旋钮必须**逐字等于 v2 模块常量**（V3-0 的承诺: 行为零变化）。"""
    from core.brain.wiki_v2 import recall as R
    snap = rc.snapshot()
    assert snap["cand_high"] == R.CAND_HIGH == 0.50
    assert snap["cand_med"] == R.CAND_MED == 0.25
    assert snap["cand_k"] == float(R.CAND_K) == 3.0
    print("    旋钮: 默认值 == v2 常量（行为零变化）")


def test_time_half_life_default_and_override(tmp_path, monkeypatch):
    """`time_half_life_days`（A 链路新鲜度半衰期, §4.11）——默认 5 叙事日 + 可覆盖。

    语义钉住: **新鲜度不是遗忘曲线**（用户裁决 2026-09-13）——
    所以默认值必须是"一周上下"的量级, 而不是遗忘曲线的 60 天。
    """
    assert rc.DEFAULTS["time_half_life_days"] == 5.0
    p = tmp_path / "settings.toml"
    p.write_text("[recall]\ntime_half_life_days = 12\n", encoding="utf-8")
    monkeypatch.setattr(rc, "_SETTINGS_PATH", p)
    rc.reload()
    assert rc.get("time_half_life_days") == 12.0
    # 坏值 → 默认（不抛）
    p.write_text('[recall]\ntime_half_life_days = "long"\n', encoding="utf-8")
    rc.reload()
    assert rc.get("time_half_life_days") == 5.0
    print("    旋钮: time_half_life_days 默认 5.0（叙事日）+ 覆盖/坏值回落")


def test_settings_override(tmp_path, monkeypatch):
    """`[recall]` 覆盖生效（这是 V3-0 存在的理由: 按模型标定不必改代码）。"""
    p = tmp_path / "settings.toml"
    p.write_text("[recall]\ncand_high = 0.72\ncand_med = 0.40\ncand_k = 2\n",
                 encoding="utf-8")
    monkeypatch.setattr(rc, "_SETTINGS_PATH", p)
    rc.reload()
    assert rc.get("cand_high") == 0.72
    assert rc.get("cand_med") == 0.40
    assert rc.get("cand_k") == 2.0
    # 未配的键保持默认
    assert rc.get("sim_k") == rc.DEFAULTS["sim_k"]
    print("    旋钮: [recall] 覆盖生效 + 未配键保持默认")


def test_bad_values_fall_back(tmp_path, monkeypatch):
    """坏值/坏文件**不得**炸（宁缺勿错——配置层绝不能阻断对话或 digest）。"""
    p = tmp_path / "settings.toml"
    p.write_text('[recall]\ncand_high = "high"\ncand_k = true\n',
                 encoding="utf-8")
    monkeypatch.setattr(rc, "_SETTINGS_PATH", p)
    rc.reload()
    assert rc.get("cand_high") == rc.DEFAULTS["cand_high"], "字符串应被拒"
    assert rc.get("cand_k") == rc.DEFAULTS["cand_k"], "bool 应被拒（不是数值）"

    # 文件损坏 → 全默认
    p.write_text("[recall\n 这行不是合法 toml", encoding="utf-8")
    rc.reload()
    assert rc.get("cand_high") == rc.DEFAULTS["cand_high"]
    print("    旋钮: 类型不符/TOML 损坏 → 回落默认, 不抛")


def test_unknown_key_raises():
    """未知键报错——防拼错后静默走默认（那会让标定白做）。"""
    with pytest.raises(KeyError) as e:
        rc.get("cand_hihg")
    assert "cand_high" in str(e.value)
    print("    旋钮: 未知键 KeyError（并列出可用键）")


def test_reload_picks_up_change(tmp_path, monkeypatch):
    """`reload()` 后读新值（测试与设置变更依赖这个语义）。"""
    p = tmp_path / "settings.toml"
    monkeypatch.setattr(rc, "_SETTINGS_PATH", p)
    p.write_text("[recall]\ncand_high = 0.5\n", encoding="utf-8")
    rc.reload()
    assert rc.get("cand_high") == 0.5
    p.write_text("[recall]\ncand_high = 0.8\n", encoding="utf-8")
    assert rc.get("cand_high") == 0.5, "未 reload 应命中缓存"
    rc.reload()
    assert rc.get("cand_high") == 0.8, "reload 后应读新值"
    print("    旋钮: 懒加载缓存 + reload 生效")


# ---------------------------------------------------------------------------
# 台账
# ---------------------------------------------------------------------------

def test_collision_account_forced_rate(caplog):
    """写路径台账: forced 比例算对 + 超告警线打 ⚠forced_high。

    这条告警的语义是"阈值把同一段关系的不同侧面判成了同一件事 → 新认知永远
    长不出来"（真机实测 4/4 皆 forced、best sim 0.92）。
    """
    with caplog.at_level(logging.INFO, logger="live2be.brain"):
        acc = rl.CollisionAccount("igusa_haruka")
        for _ in range(4):
            acc.episode(hi=1, med=2, n_cand=3, best_sim=0.92)
        acc.mode = "semantic"
        acc.log(thr_high=0.50, thr_med=0.25)
    line = next(r.message for r in caplog.records if r.message.startswith("recall_write"))
    assert "forced=100%" in line and "⚠forced_high" in line
    assert "mode=semantic" in line and "thr=0.50/0.25" in line
    assert "char=igusa_haruka" in line and "eps=4" in line

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="live2be.brain"):
        acc2 = rl.CollisionAccount("x")
        for _ in range(4):
            acc2.episode(hi=0, med=1, n_cand=1, best_sim=0.3)   # 全 MED, 无强制
        acc2.log(thr_high=0.50, thr_med=0.25)
    line2 = next(r.message for r in caplog.records if r.message.startswith("recall_write"))
    assert "forced=0%" in line2 and "⚠forced_high" not in line2
    print("    台账: forced 比例 + ⚠forced_high 告警线")


def test_collision_account_disabled(caplog):
    """开关关掉 → 不打点（测试/离线跑时静音）。"""
    with caplog.at_level(logging.INFO, logger="live2be.brain"):
        rl.ENABLED = False
        try:
            rl.CollisionAccount("x").log(thr_high=0.5, thr_med=0.25)
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
        rl.CollisionAccount("x").log(thr_high=0.5, thr_med=0.25)      # 0 episode
        rl.log_read(char_id="", total=0, picked=0, buckets={})        # 空
    print("    台账: 空/畸形输入不抛")


# ---------------------------------------------------------------------------
# 渲染层记账（读路径的事实来源）
# ---------------------------------------------------------------------------

def _store(tmp_path) -> WikiStoreV2:
    st = WikiStoreV2(tmp_path)
    st.add(make_node("episode", narration="老师约我去看杂草。", title="看杂草",
                     significance=0.7, tags=["杂草"]))
    st.add(make_node("episode", narration="我给草取了名字。", title="取名字",
                     significance=0.6, tags=["命名"]))
    st.add(make_node("belief", subject="被老师需要", content="只要老师需要我就会答应。",
                     significance=0.8, epistemic="inferred_belief",
                     tags=["老师"], links=[st.all()[0].id]))
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
