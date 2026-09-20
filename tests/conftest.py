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
    - 已退役机制的用例原本在 `tests/archive/`——**2026-09-21 随 v1 整族退役一并删除**
      （v1 动作契约/记忆三件套已从产品侧移除, 留档在 git 历史里）。
    - **生图默认硬关**（见下 `_no_image_gen`: 环境变量 `LIVE2BE_IMAGE=off` 会话级
      autouse）——测试绝不会真的调生图 API 出图烧钱, 也绝不写 gallery。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

#: 生图总开关的环境变量名 —— 不 import 项目模块（conftest 加载早于 pythonpath 生效,
#: 且减少耦合）; 与 `llm.image_gen.ENV_SWITCH` 的一致性由 test_image_gen 断言兜底。
_IMG_SWITCH = "LIVE2BE_IMAGE"

# ---------------------------------------------------------------------------
# 诊断日志重定向（2026-09-11, **必须在任何测试模块 import 之前**做）
# ---------------------------------------------------------------------------
# `webgui.app` 在 import 时就挂全局 FileHandler 写 data/diag/live2be.log——
# 测试（含各测试桩的 WARNING）会混进**真机诊断日志**: 用户就问过
# "settings reasoning_effort 非法: 'turbo' 是谁写的?"（那是 tests/llm 里
# 「非法档位被忽略」用例的桩值, 与用户 settings.toml 无关）, 类似的还有
# ScriptedLLM 脚本耗尽。这里在 conftest 导入期（早于测试模块）就把落盘路径
# 改到 .testtmp, 真机日志只留真实运行。
os.environ.setdefault(
    "LIVE2BE_DIAG_LOG",
    str(Path(__file__).resolve().parent.parent / ".testtmp" / "diag" / "test.log"))


@pytest.fixture(autouse=True)
def _clear_module_caches():
    """清**进程级模块缓存**——否则用例结果取决于执行顺序（2026-09-12 实测）。

    案例: `core/bond/place_annotate._RESOLVE_CACHE`（换场翻译: 同 `当前地点|地点话`
    只调一次 LLM）。先跑的用例（webgui 桩把「教室」译成 MISS）会把结果留给
    `tests/core/test_director.py::test_engine_attaches_background_audio`（它期望
    「教室」→ `class_room`）→ **`pytest tests/webgui tests/core` 红, 换个顺序就绿**。
    新增模块级缓存时请一并登记到这里。
    """
    from core.bond import place_annotate as pa

    cache = getattr(pa, "_RESOLVE_CACHE", None)
    if cache is not None:
        cache.clear()
    yield
    if cache is not None:
        cache.clear()


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


@pytest.fixture(scope="session", autouse=True)
def _isolate_runtime_files(tmp_path_factory):
    """**全局运行时落盘点重定向**（2026-09-11 二次事故后的兜底）。

    事故: 注入临时 store 也挡不住**模块级常量路径**——`mmt_preset.PLAYER_JSON`
    （登录取名）与 `BondProgress()`（对话轮数）写的是真实 `data/basic/*.json`。
    真机后果: 玩家名被测试写成"老师"、haruka 轮数被刷到 4550。

    产品侧已修（引擎跟着 store 走 + 冒烟桩世界改 PLAYER_JSON）; 这里再加一道
    会话级兜底: 任何用例/新代码只要碰这两个路径就落到 tmp, **测试永远碰不到
    data/**。新增全局落盘点时也请一并登记到这里。
    """
    from core.bond import bond_progress as bp
    from core.mmt import mmt_preset
    from pathlib import Path

    root = tmp_path_factory.mktemp("runtime")
    (root / "basic").mkdir(parents=True, exist_ok=True)
    old_player = mmt_preset.PLAYER_JSON
    old_default = bp.DEFAULT_DATA_ROOT
    old_init = bp.BondProgress.__init__
    mmt_preset.PLAYER_JSON = root / "basic" / "player.json"
    bp.DEFAULT_DATA_ROOT = root

    def _guarded_init(self, data_root=None):
        # 解析后再挡一道: 显式传"真实 data 根"的调用（如 chat.py 模块级 _store
        # 建的引擎）也要重定向到 tmp——否则 test 仍会写真实 basic/bond_progress.json
        # （2026-09-11 实测: 全量跑一轮把 haruka 刷到 38）。
        resolved = Path(data_root) if data_root else root
        if resolved == old_default:
            resolved = root
        old_init(self, resolved)

    bp.BondProgress.__init__ = _guarded_init
    try:
        yield root
    finally:
        mmt_preset.PLAYER_JSON = old_player
        bp.DEFAULT_DATA_ROOT = old_default
        bp.BondProgress.__init__ = old_init
