"""tests/ 公共 fixture 与说明。

运行方式（项目根）:
    python -m pytest                 # 全部离线测试
    python -m pytest -m api          # 只跑需要真实 API 的测试（烧钱/需 key）
    python -m pytest tests/ide       # 只跑某个域

约定:
    - 需要真实 LLM API 的测试标记 @pytest.mark.api（默认被排除, 见 pytest.ini）
    - 测试不得污染 data/、config/——用临时目录（tmp_path）或 monkeypatch
    - **VN 场景桩一律用记录流**（`tests/vn_fixtures.scene(...)`）——记录流 v2 起
      引擎只接受记录流字符串, 旧动作 JSON 会被打回重发（决策 #27/§11 P0-7c）。
      仍在写 v1 形状 dict 的存量桩由 `tests.vn_fixtures.from_v1_scene()` **测试侧**
      适配（产品侧没有这条通道）, 新用例请直接用 `scene(...)`。
    - 已退役机制的用例在 `tests/archive/`（不收集, 见该目录 README）。
"""

