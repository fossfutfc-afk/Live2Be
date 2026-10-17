"""章节收束注记 —— 两条壳共用的 LLM 可见文案。

`cli/vn_cli.py`（同步驱动）与 `webgui/bond/pregen.py`（链式读前）都从这里取,
**别在壳里另写一份**: 这两处曾经各抄一份, CLI 那份一路在教 v1 的 `story_end` 动作,
而记录流 v2 里没有这个动作（引擎只吃记录流, 那种注记会被打回重发）。

轮次语义: `round_no` = **这一轮在整章里的序号**（不是"已消费轮数"——webgui 的读前
还要加手里没被读过的板数, 见 `pregen._system_note`）。
"""

REMIND_ROUNDS = 30
END_ROUNDS = 50


def closing_notes(round_no: int, remind_rounds: int = REMIND_ROUNDS,
                  end_rounds: int = END_ROUNDS) -> list[str]:
    """按第几轮给收束注记（0~1 条, 按"提醒 → 上限 → 超限"分档）。"""
    if round_no == remind_rounds:
        return [
            f"（系统）剧情已推进 {round_no} 轮，剩余约 {end_rounds - round_no} 轮。"
            "请开始把剧情向结尾收束——感情到位、约定达成、道别告别的时刻"
            "就把本轮的**最后一条记录**写成 stage=end 收尾，不要再开新场景"
            "不过也谨记这只是中段提示，你并不需要匆匆结尾，但是建议开始铺垫"
        ]
    if round_no == end_rounds:
        return [
            "（系统）已达剧情篇幅上限。本轮请用 stage=end 收尾"
            "结束剧情——收尾那一条 text 是收尾字段（可留空 = 直接黑屏退场）。"
        ]
    if round_no > end_rounds:
        # 余量场次每轮强制（不是伪收场: 收尾仍然由模型把最后一条写成 stage=end）
        return [
            "（系统）剧情已远超篇幅上限。本轮**必须**把最后一条记录写成 stage=end"
            "收尾结束剧情——不再开新场景、不再写新的铺垫。"
        ]
    return []
