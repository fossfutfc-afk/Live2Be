"""日志配置守门 —— 控制台只静音轮询、长消息截断、setup 只装一次。

为什么值得钉: 控制台一静音就容易连**该留的**也静掉（4xx/5xx、业务日志）;
而 `setup()` 若装两次, 每行日志会打两遍（看起来像"系统在重复执行"）。

跑法: python -m pytest tests/core/test_logsetup.py
"""
import logging

from infra import logsetup


def _access(path: str, status: int) -> logging.LogRecord:
    """造一条 uvicorn 访问日志记录（args 五个位置: client/method/path/ver/status）。"""
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, "uvicorn/logging.py", 0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:50000", "GET", path, "1.1", status), None)


def test_access_quiet_only_silences_polling_2xx():
    f = logsetup.AccessQuiet()
    # 轮询与静态资源: 2xx 不打印
    assert not f.filter(_access("/api/bond/status?char_id=x", 200))
    assert not f.filter(_access("/api/mmt/events", 200))
    assert not f.filter(_access("/static/js/mmt.js", 200))
    assert not f.filter(_access("/assets/illustration/x.png", 200))
    # 业务请求照打
    assert f.filter(_access("/api/bond/turn", 200))
    assert f.filter(_access("/api/mmt/chat", 200))
    # 失败必须留（静音只看 2xx）
    assert f.filter(_access("/api/bond/status", 500))
    assert f.filter(_access("/api/bond/turn", 422))
    # 不是 uvicorn 那种记录（业务日志）一律放行
    biz = logging.LogRecord("core.mmt.engine", logging.INFO, __file__, 0, "x=1", None, None)
    assert f.filter(biz)


def test_console_formatter_is_short_and_truncates():
    fmt = logsetup.ConsoleFormatter(limit=40)
    short = logging.LogRecord("core.digest.rounds.relate", logging.INFO, __file__, 0,
                              "digest_relate cands=%d", (3,), None)
    out = fmt.format(short)
    assert out.endswith("digest_relate cands=3"), out
    assert " digest " in out, out                       # 短域名
    long = logging.LogRecord("core.digest.call", logging.INFO, __file__, 0,
                             "长" * 200, None, None)
    clipped = fmt.format(long)
    assert clipped.endswith("…") and len(clipped) < 80, clipped


def test_setup_installs_handlers_once_and_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE2BE_DIAG_LOG", str(tmp_path / "diag.log"))
    monkeypatch.delenv("LIVE2BE_LOG", raising=False)
    logsetup._reset_for_tests()
    try:
        logsetup.setup()
        # 只数**我们装的那几个**（pytest 自己往 root 上挂 LogCaptureHandler）
        assert len(logsetup._handlers) == 2, logsetup._handlers   # 控制台 + 文件
        logsetup.setup()                                          # 重复调用不许再装
        assert len(logsetup._handlers) == 2, logsetup._handlers
        logging.getLogger("core.mmt.engine").info("hello from logsetup test")
        text = (tmp_path / "diag.log").read_text(encoding="utf-8")
        assert "hello from logsetup test" in text
        assert "core.mmt.engine INFO" in text, text          # 文件里保留原名（可 grep）
    finally:
        logsetup._reset_for_tests()
        logsetup.setup()


def test_file_log_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("LIVE2BE_DIAG_LOG", "off")
    root = logging.getLogger()
    logsetup._reset_for_tests()
    try:
        logsetup.setup()
        assert len(logsetup._handlers) == 1, logsetup._handlers  # 只剩控制台
        assert root.handlers, root.handlers
    finally:
        logsetup._reset_for_tests()
        logsetup.setup()
