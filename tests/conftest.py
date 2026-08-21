"""tests/ 公共 fixture 与说明。

运行方式（项目根）:
    python -m pytest                 # 全部离线测试
    python -m pytest -m api          # 只跑需要真实 API 的测试（烧钱/需 key）
    python -m pytest tests/ide       # 只跑某个域

约定:
    - 需要真实 LLM API 的测试标记 @pytest.mark.api（默认被排除, 见 pytest.ini）
    - 测试不得污染 data/、config/——用临时目录（tmp_path）或 monkeypatch
"""
