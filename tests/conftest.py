"""tests/ 公共 fixture 与说明。

运行方式（项目根）:
    python -m pytest                 # 全部离线测试
    python -m pytest -m api          # 只跑需要真实 API 的测试（烧钱/需 key）
    python -m pytest tests/ide       # 只跑某个域

约定:
    - 需要真实 LLM API 的测试标记 @pytest.mark.api（默认被排除, 见 pytest.ini）
    - 测试不得污染 data/、config/——用临时目录（tmp_path）或 monkeypatch
    - **旧动作输入开关**（记录流 v2, 决策 #27）: 存量测试桩仍返回
      `{"action": "story_scene", ...}` dict, 而生产默认只吃记录流; 这里显式打开
      兼容开关, 让存量用例继续有效。**新写的用例请用 `tests.vn_fixtures.scene`
      构造记录流**, 不要依赖该开关（迁移进度见 DESIGN_VN_UPGRADE §11 P0-7b/c）。
"""

import os

os.environ.setdefault("LIVE2BE_VN_LEGACY_ACTION", "1")
