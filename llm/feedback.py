"""错误/结果回灌给 LLM 的公共助手 — 追加一条 user 修正指令。

fetch IDE loop 与未来 MMT loop 共用。所有域的回灌统一走这一个函数:
消息体由调用方构造（带域内措辞/指引）, 本函数只负责把它作为 user 角色
追加进 messages, 并留出 guidance 附言约定——避免每个域手写
messages.append({"role": "user", "content": ...}) 的三四行样板。

注意 web/mock.py 依赖部分回灌消息的原文（如 "动作已执行" 前缀、
"用户拒绝" 子串）——调用方必须保留既有措辞, 别在这里统一改写。
"""


def feedback(
    messages: list[dict],
    reason: str | Exception,
    guidance: str = "",
) -> None:
    """回灌失败/结果给 LLM: 追加一条 user 消息, 让 LLM 修正后重试。

    Args:
        messages: OpenAI 风格历史 [{role, content}, ...], 原地追加。
        reason:   回灌正文。Exception（str() 后得到 [file][Class][msg]）、
                  '; '.join(errors)（parse 级）或任意提示文本——调用方自带
                  域内措辞前缀（如 '无法执行: '）。
        guidance: 可选, 追加在正文下一行的修正提示（schema 要点 / 建议）。
    """
    content = str(reason)
    if guidance:
        content = f"{content}\n{guidance}"
    messages.append({"role": "user", "content": content})
