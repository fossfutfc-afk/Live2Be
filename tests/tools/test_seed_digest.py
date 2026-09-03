"""tools/seed_digest.py 单测（TODO 阶段 4.4）——出厂经历改编工具。

不调真实 LLM——fake client 注入 adapt_one; 写盘用 monkeypatch 的假角色目录
（CHARACTERS_ROOT → tmp）; 真实遥香目录只读（人设锚/称谓表渲染）。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import tools.seed_digest as sd          # noqa: E402

HARUKA = "igusa_haruka"


class FakeClient:
    """chat 返回脚本序列（逐条改编输出; response_format 兼容）。"""

    def __init__(self, script: list[dict]):
        self._script = list(script)

    def chat(self, messages, **kwargs):
        if not self._script:
            raise AssertionError("fake client 脚本耗尽")
        out = self._script.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


# ---------------------------------------------------------------------------
# prompt 组装（2.3）
# ---------------------------------------------------------------------------

def test_assemble_prompt_no_placeholder_leftover():
    p = sd.assemble_prompt(HARUKA, "伊草 遥香", "self.regular.1", "原文内容X" * 10)
    assert "{{" not in p and "}}" not in p
    assert "【占位符说明】" not in p          # 工具端契约段被裁
    assert "伊草 遥香" in p
    assert "【本轮改编目标】" in p and "self.regular.1" in p
    assert "原文内容X" in p
    # 主体结构保持: 角色定位/输出规格/规则/纪律都在
    assert "预设经历改编员" in p
    assert "【输出规格】" in p and "author_notes" in p
    assert "【改编规则】" in p and "【输出纪律】" in p
    assert p.index("【输出规格】") < p.index("【改编规则】") < p.index("【输出纪律】")


# ---------------------------------------------------------------------------
# 人设锚 / 称谓表（2.1/2.2, 读真实遥香 config——只读）
# ---------------------------------------------------------------------------

def test_anchor_and_name_table_real_haruka():
    anchor = sd.render_character_anchor(HARUKA)
    assert "角色档案" in anchor and "伊草 遥香" in anchor or "遥香" in anchor
    table = sd.render_name_table(HARUKA)
    assert "sensei:" in table and "aru:" in table
    assert "阿露大人" in table                  # 称谓线索在文本里


def test_char_aliases_real_haruka():
    aliases = sd.char_aliases(HARUKA)
    assert "伊草 遥香" in aliases and "遥香" in aliases


# ---------------------------------------------------------------------------
# 产物校验（2.4）
# ---------------------------------------------------------------------------

def test_validate_entry_hard_and_soft():
    aliases = ("遥香", "伊草 遥香")
    ok, warns = sd.validate_entry(
        {"source_key": "self.regular.1", "title": "t", "narration": "我拆完了炸弹",
         "significance": 0.9}, "self.regular.1", aliases)
    assert ok == [] and warns == []
    # 硬错误: key 回填错 / 空 / sig 越界 / 类型错
    errs, _ = sd.validate_entry(
        {"source_key": "x", "title": "", "narration": "", "significance": 2,
         "verbatim": 123}, "self.regular.1", aliases)
    joined = " | ".join(errs)
    assert "source_key 回填不一致" in joined
    assert "title 为空" in joined and "narration 为空" in joined
    assert "significance 越界" in joined and "verbatim 必须是字符串" in joined
    # 软警告: 第三人称残留 + 多余键
    errs2, warns2 = sd.validate_entry(
        {"source_key": "self.regular.1", "title": "t",
         "narration": "遥香发现老师没有责怪我", "significance": 0.5,
         "bogus": 1}, "self.regular.1", aliases)
    assert errs2 == []
    assert any("遥香" in w for w in warns2)
    assert any("bogus" in w for w in warns2)


# ---------------------------------------------------------------------------
# 逐条改编（2.3, fake client）
# ---------------------------------------------------------------------------

def test_adapt_one_uses_fake_client():
    fake = FakeClient([{"source_key": "k", "title": "t", "narration": "n",
                        "significance": 0.8}])
    out = sd.adapt_one(fake, "prompt")
    assert out["source_key"] == "k"


def test_adapt_all_retry_then_fail_without_blocking():
    """失败重试 RETRIES 次后跳过; 好条照常; failed 清单返回。"""
    fake = FakeClient([
        {"source_key": "a", "title": "t", "narration": "n", "significance": 0.8},
        RuntimeError("网络断"), RuntimeError("网络断"), RuntimeError("网络断"),
        {"source_key": "c", "title": "t", "narration": "n", "significance": 0.8},
    ])
    leaves = [("a", "x"), ("b", "y"), ("c", "z")]
    entries, failed = sd.adapt_all(fake, HARUKA, "伊草 遥香", leaves)
    assert [e["source_key"] for e in entries] == ["a", "c"]
    assert failed == ["b"]


def test_validate_entry_copy_mirror_detected():
    """v2 规则 2: 句式镜像照抄/无浓缩 → 软警告（相似度 + 压缩率双指标）。"""
    aliases = ("遥香", "伊草 遥香")
    original = ("不小心错误地给sensei发送了消息, 结果被sensei发现是在埋炸弹, "
                "sensei告诉她她误解了消息, 并且陪着她让她拆除了所有的炸弹。")
    # 镜像平移（换主语照抄）→ 相似度高 → 警告
    mirror = ("我不小心错误地给老师发送了消息, 结果被老师发现我是在埋炸弹。"
              "老师告诉我, 是我误解了消息, 然后没有怪我, 只是陪着我, 让我拆除了所有炸弹。")
    _, warns = sd.validate_entry(
        {"source_key": "k", "title": "t", "narration": mirror,
         "significance": 0.8}, "k", aliases, original=original)
    assert any("相似度" in w and "镜像" in w for w in warns), warns
    # 真重构 → 相似度低, 无镜像警告
    rebuilt = ("埋炸弹的事被老师发现了。老师没有骂我, 反而留下来陪着我, "
               "让我把炸弹一颗颗拆完。长这么大, 第一次有人这样对我。")
    _, warns2 = sd.validate_entry(
        {"source_key": "k", "title": "t", "narration": rebuilt,
         "significance": 0.8}, "k", aliases, original=original)
    assert not any("镜像" in w for w in warns2), warns2
    # 无浓缩（几乎等长）→ 压缩警告
    _, warns3 = sd.validate_entry(
        {"source_key": "k", "title": "t", "narration": original + "补充一点内容让长度相近",
         "significance": 0.8}, "k", aliases, original=original)
    assert any("浓缩" in w for w in warns3)


# ---------------------------------------------------------------------------
# brain_seed.yml 写入（2.5, monkeypatch 假角色目录）
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_char(monkeypatch, tmp_path):
    root = tmp_path / "config" / "characters"
    (root / HARUKA).mkdir(parents=True)
    monkeypatch.setattr(sd, "CHARACTERS_ROOT", root)
    return root / HARUKA


def test_write_brain_seed_content_and_overwrite_guard(fake_char):
    entries = [
        {"source_key": "self.regular.1", "title": "拆炸弹乌龙",
         "narration": "我给老师发消息时…", "verbatim": "没关系",
         "significance": 0.95},
        {"source_key": "main.1", "title": "黑市讨债", "narration": "一起讨债",
         "significance": 0.7, "author_notes": "她对sensei无比信任。"},
    ]
    out = sd.write_brain_seed(HARUKA, entries, force=False, generated_at="t0")
    text = out.read_text(encoding="utf-8")
    assert "拆炸弹乌龙" in text and "我给老师发消息时…" in text
    assert "verbatim: \"没关系\"" in text
    assert "significance: 0.95" in text
    assert "review_notes:" in text and "她对sensei无比信任。" in text
    # 防覆盖
    with pytest.raises(FileExistsError):
        sd.write_brain_seed(HARUKA, entries, force=False, generated_at="t1")
    # --force → .bak 备份
    out2 = sd.write_brain_seed(HARUKA, entries, force=True, generated_at="t2")
    assert out2 == out
    assert (fake_char / "brain_seed.yml.bak").exists()
    bak_text = (fake_char / "brain_seed.yml.bak").read_text(encoding="utf-8")
    assert "generated_at" not in bak_text or "t0" in bak_text


def test_write_brain_seed_omits_optional_keys(fake_char):
    entries = [{"source_key": "k", "title": "t", "narration": "n", "significance": 0.5}]
    out = sd.write_brain_seed(HARUKA, entries, force=False, generated_at="t")
    text = out.read_text(encoding="utf-8")
    assert "verbatim" not in text
    assert "review_notes:" not in text          # 无 author_notes → 不产段（注释提及不算）
