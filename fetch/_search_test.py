# -*- coding: utf-8 -*-
"""fetch/ 搜索可靠性增强回归测试（别名/繁简/多候选尝试）。

覆盖:
    search_index   normalize_query / build_alias_index（自动从 profile 构建）
    search 契约    parse_search 的 aliases 字段（新角色候选词, 一次提交）
    executor       _search_attempts 候选序列（含 aliases 种子词展开）;
                   _execute_search 注入 _opensearch（首个命中即停 /
                   全空失败信息 / 繁体命中简体）
    live 冒烟      真实萌娘百科一条（网络不可用则跳过）

用法: python fetch/_search_test.py   （项目根环境, 推荐 live2be env, 需 zhconv）
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contract import AgentAction, DOMAIN_IDE, APPROVAL_NEVER, ContractError
import fetch.executor as E
from fetch.search_index import normalize_query, build_alias_index
from fetch.executor import Executor, _opensearch


# 真实 profile 名字数据
_PROFILES = {
    "igusa_haruka": """REQ~most_called_name: 伊草 遥香
REQ~is_official_character: true
en_name: Igusa Haruka
jp_name: 伊草 ハルカ
other_names: 伊草 春香，春香，遥香，瑶香
""",
    "asagi_mutsuki": """REQ~most_called_name: 浅黄 睦月
REQ~is_official_character: true
en_name: Asagi Mutsuki
jp_name: 浅黄 ムツキ
other_names: 浅黄无月，无月，睦月，Mukki，地雷妹，大头
""",
    "onikata_kayoko": """REQ~most_called_name: 鬼方 佳代子
REQ~is_official_character: true
en_name: Onikata Kayoko
jp_name: 鬼方 カヨコ
other_names: 鬼方佳世子，佳代子，佳世子，カヨコ
""",
}


def _seed_chars() -> Path:
    root = Path(tempfile.mkdtemp())
    for cid, profile in _PROFILES.items():
        d = root / "config" / "characters" / cid
        d.mkdir(parents=True)
        (d / "profile.yml").write_text(profile, encoding="utf-8")
    return root


def _search_action(query: str, aliases: list[str] | None = None) -> AgentAction:
    payload: dict = {"query": query, "source": "moegirl", "max_results": 5}
    if aliases is not None:
        payload["aliases"] = aliases
    return AgentAction(action="search", domain=DOMAIN_IDE, approval=APPROVAL_NEVER,
                       payload=payload)


def _patch_opensearch(fake):
    """monkeypatch executor._opensearch, 返回 restore。"""
    real = E._opensearch
    E._opensearch = fake
    return lambda: setattr(E, "_opensearch", real)


# ============================================================================
# search_index
# ============================================================================

def test_normalize_query():
    assert normalize_query("  伊草 遥香  ") == "伊草遥香"
    assert normalize_query("伊草　遥香（日文名）") == "伊草遥香"
    assert normalize_query("Igusa Haruka") == "igusaharuka"
    assert normalize_query("地雷妹") == "地雷妹"
    print("normalize_query PASS")


def test_build_alias_index():
    root = _seed_chars()
    index = build_alias_index(root)

    assert index["遥香"] == {"伊草遥香"}
    assert index["伊草遥香"] == {"伊草遥香"}
    assert index["春香"] == {"伊草遥香"}
    assert index["ハルカ"] == {"伊草遥香"}        # jp_name 子 token
    assert index["haruka"] == {"伊草遥香"}        # en_name 子 token

    assert index["地雷妹"] == {"浅黄睦月"}        # other_names 昵称
    assert index["浅黄无月"] == {"浅黄睦月"}      # other_names 恰是另一译名
    assert index["ムツキ"] == {"浅黄睦月"}

    assert index["佳代子"] == {"鬼方佳代子"}
    assert index["カヨコ"] == {"鬼方佳代子"}
    print("build_alias_index PASS")


# ============================================================================
# search 契约（aliases 字段）
# ============================================================================

def test_parse_search_aliases():
    from fetch.actions.search import parse_search, MAX_ALIASES

    clean = parse_search({"query": "阿露", "aliases": ["陆八魔阿露", "アコ"]})
    assert clean["aliases"] == ["陆八魔阿露", "アコ"]
    # 缺省无 aliases → 不出现在 payload（执行层 .get 兜底）
    assert "aliases" not in parse_search({"query": "阿露"})
    # 非法: 非数组 / 空项 / 超上限
    for bad in ({"query": "阿露", "aliases": "阿露"},
                {"query": "阿露", "aliases": ["阿露", ""]},
                {"query": "阿露", "aliases": ["a"] * (MAX_ALIASES + 1)}):
        try:
            parse_search(bad)
        except ContractError:
            pass
        else:
            raise AssertionError(f"应抛 ContractError: {bad!r}")
    print("parse_search aliases PASS")


# ============================================================================
# executor._search_attempts
# ============================================================================

def test_search_attempts():
    root = _seed_chars()
    ex = Executor(root)

    # 别名 → 规范标题追加
    assert ex._search_attempts("遥香") == ["遥香", "伊草遥香"]
    # 繁体 → 简体变体（索引无此 key, zhconv 转换）
    assert ex._search_attempts("伊草遙香") == ["伊草遙香", "伊草遥香"]
    # 规范标题本身 → 去重后只有一条
    assert ex._search_attempts("伊草遥香") == ["伊草遥香"]
    # 未建档角色 → 只有原查询（zhconv 无变化）
    assert ex._search_attempts("阿露") == ["阿露"]
    print("_search_attempts PASS")


def test_search_attempts_with_aliases():
    root = _seed_chars()
    ex = Executor(root)

    # 新角色（索引无条目）: aliases 作为附加种子词展开
    assert ex._search_attempts("阿露", ["陆八魔阿露", "アコ"]) == \
        ["阿露", "陆八魔阿露", "アコ"]
    # aliases 里的繁体 → 简体变体也展开
    assert ex._search_attempts("アコ", ["陸八魔阿露"]) == \
        ["アコ", "陸八魔阿露", "陆八魔阿露"]
    print("_search_attempts(aliases) PASS")


# ============================================================================
# executor._execute_search（注入 _opensearch）
# ============================================================================

def test_execute_first_hit():
    root = _seed_chars()
    calls: list[str] = []

    def fake(base, q, limit):
        calls.append(q)
        if q == "伊草遥香":
            return (["伊草遥香", "伊草遥香/MomoTalk"], [""], ["u1", "u2"])
        return ([], [], [])

    restore = _patch_opensearch(fake)
    try:
        res = Executor(root).execute(_search_action("遥香"))
    finally:
        restore()
    assert res.ok
    assert calls == ["遥香", "伊草遥香"]          # 原查询失败 → 规范标题命中
    assert "伊草遥香" in res.message              # 结果含命中标题
    print("_execute_search 别名→规范标题命中 PASS")


def test_execute_traditional_hits_simplified():
    root = _seed_chars()
    calls: list[str] = []

    def fake(base, q, limit):
        calls.append(q)
        if q == "伊草遥香":
            return (["伊草遥香"], [""], ["u1"])
        return ([], [], [])

    restore = _patch_opensearch(fake)
    try:
        res = Executor(root).execute(_search_action("伊草遙香"))
    finally:
        restore()
    assert res.ok
    assert calls == ["伊草遙香", "伊草遥香"]       # 繁体原查失败 → 简体命中
    print("_execute_search 繁体→简体命中 PASS")


def test_execute_first_attempt_stops():
    root = _seed_chars()
    calls: list[str] = []

    def fake(base, q, limit):
        calls.append(q)
        return (["浅黄睦月"], [""], ["u1"])

    restore = _patch_opensearch(fake)
    try:
        res = Executor(root).execute(_search_action("浅黄睦月"))
    finally:
        restore()
    assert res.ok and calls == ["浅黄睦月"]       # 原查询即命中, 不再多试
    print("_execute_search 原查询命中即停 PASS")


def test_execute_search_alias_hits():
    root = _seed_chars()
    calls: list[str] = []

    def fake(base, q, limit):
        calls.append(q)
        if q == "陆八魔阿露":
            return (["陆八魔阿露"], [""], ["u1"])
        return ([], [], [])

    restore = _patch_opensearch(fake)
    try:
        res = Executor(root).execute(_search_action("阿露", ["陆八魔阿露", "アコ"]))
    finally:
        restore()
    assert res.ok
    assert calls == ["阿露", "陆八魔阿露"]       # 原查失败 → 第 1 个别名命中即停
    assert "陆八魔阿露" in res.message
    print("_execute_search aliases 命中 PASS")


def test_execute_all_empty_error():
    root = _seed_chars()

    def fake(base, q, limit):
        return ([], [], [])

    restore = _patch_opensearch(fake)
    try:
        try:
            Executor(root).execute(_search_action("不存在的角色XYZ"))
        except E.ExecError as e:
            msg = str(e)
            assert "已尝试" in msg
            assert "不存在的角色XYZ" in msg
            assert "简体全名" in msg and "别名" in msg
        else:
            raise AssertionError("全空应抛 ExecError")
    finally:
        restore()
    print("_execute_search 全空失败信息 PASS")


# ============================================================================
# live 冒烟（网络可用才跑）
# ============================================================================

def test_live_opensearch():
    try:
        titles, _, _ = _opensearch("https://zh.moegirl.org.cn", "伊草遥香", 3)
    except Exception as e:  # noqa: BLE001
        print(f"live 冒烟跳过（网络不可用）: {e}")
        return
    assert any("伊草遥香" in t for t in titles), titles
    print("live 冒烟: 伊草遥香 命中")


def main() -> None:
    tests = [
        test_normalize_query, test_build_alias_index,
        test_parse_search_aliases,
        test_search_attempts, test_search_attempts_with_aliases,
        test_execute_first_hit, test_execute_traditional_hits_simplified,
        test_execute_first_attempt_stops, test_execute_search_alias_hits,
        test_execute_all_empty_error, test_live_opensearch,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\nfetch/ 搜索可靠性回归: {len(tests) - failed}/{len(tests)} 通过")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
