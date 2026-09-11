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
    - **生图默认硬关**（见下 `_no_image_gen`: 环境变量 `LIVE2BE_IMAGE=off` 会话级
      autouse）——测试绝不会真的调生图 API 出图烧钱, 也绝不写 gallery。
"""
from __future__ import annotations

import os

import pytest

#: 生图总开关的环境变量名 —— 不 import 项目模块（conftest 加载早于 pythonpath 生效,
#: 且减少耦合）; 与 `llm.image_gen.ENV_SWITCH` 的一致性由 test_image_gen 断言兜底。
_IMG_SWITCH = "LIVE2BE_IMAGE"


@pytest.fixture(scope="session", autouse=True)
def _no_image_gen():
    """生图总开关: 整个测试会话硬关（`LIVE2BE_IMAGE=off`）。

    **为什么在 conftest 而不是各文件**: 本机 `settings.toml` 配着真 key 时,
    `ImageGenerator.available` 为真——纪念路径（webgui `_make_memorial_cb` /
    CLI memorial_enter）会真的开线程出图: 花钱、写真实 gallery、且线程可能活过
    用例（2026-09-11 事故同型: 后台线程写错世界线）。环境变量优先级最高
    （> settings `[image].enabled`）, 且读在**调用时**（不受模块导入顺序影响）,
    所以新增用例/新文件无需各自打桩即天然安全; 需要真出图的用例显式
    `monkeypatch.setenv(LIVE2BE_IMAGE, "on")` + `monkeypatch.setattr(
    bond, "_image_generator", fake)` 覆盖（见 tests/archive 的老用例）。
    """
    old = os.environ.get(_IMG_SWITCH)
    os.environ[_IMG_SWITCH] = "off"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(_IMG_SWITCH, None)
        else:
            os.environ[_IMG_SWITCH] = old
