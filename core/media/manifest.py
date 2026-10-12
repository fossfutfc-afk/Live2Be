"""角色差分 manifest — assets/illustration/{char}/emotions.yml（情绪词表真源）。

形态（v2 视觉意图协议, DESIGN_VISUAL_PROTOCOL.md §4/§8 + 2026-08-28 双投影架构）:
    emotions:                 # 情绪名(id, 主 LLM 输出用) → 资源 ID
      正常1: 01               # 资源 ID（无 / 无扩展名）: diff 路径 + spine 动画双投影
      正常2: custom/a.png     # 显式相对路径（AI 生成/自绘, 无 spine 投影）
    spine: haruka_spr        # 可选: 优先的 spine 导出包名（= spine/ 下目录名, 兼容旧字段）
    diff_dir: diff           # 可选: 静态图目录（缺省 diff）

资源 ID 双投影（diff 与 spine 同源, 一份值派生两个资源）:
    值 "01" → diff 路径 = {diff_dir}/{spine}_01.png; spine 动画 = "01"
    值 "diff/haruka_spr_01.png"（旧格式路径）→ 原样路径; spine 动画 = stem 去 "{spine}_" 前缀
    值 "custom/a.png"（无前缀）→ 原样路径; spine 动画 = None（纯静态图, 播放器降级 diff）

2026-08 真源由 _media.yml 改为 emotions.yml（键=情绪名id, 值=diff/ 相对路径,
行尾注释=示范）; 旧 _media.yml 不再读取。
缺失/损坏/格式不对 → 降级 {"sprites": {}, "spine": None, "animations": {}}
（宁缺勿错, 查询返回 None, 不阻断引擎）。
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_character_manifest(char_dir: Path) -> dict:
    """读取角色情绪词表。

    Returns:
        {"sprites": {情绪: diff 相对路径}, "spine": 包名|None,
         "animations": {情绪: spine 动画名|None}}（双投影派生）
    """
    path = char_dir / "emotions.yml"
    empty = {"sprites": {}, "spine": None, "animations": {}}
    if not path.is_file():
        return empty
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception:
        return empty
    if not isinstance(data, dict):
        return empty
    sprites = data.get("emotions")
    if not isinstance(sprites, dict):
        sprites = {}
    # 键转 str（防御: yaml 数值键）; 值兼容 str/int（YAML 1.1 八进制坑: "01"→int 1,
    # 前导零丢失——int 补零回 2 位, 官方动画名是 2 位数字习惯; bool 排除）
    cleaned: dict[str, str] = {}
    for k, v in sprites.items():
        if isinstance(v, str) and v.strip():
            cleaned[str(k)] = v.strip()
        elif isinstance(v, int) and not isinstance(v, bool):
            cleaned[str(k)] = str(v).zfill(2)
    sprites = cleaned
    spine = data.get("spine")
    spine = str(spine) if isinstance(spine, str) and spine else None
    diff_dir = data.get("diff_dir")
    diff_dir = str(diff_dir).strip() if isinstance(diff_dir, str) and diff_dir.strip() else "diff"

    animations: dict[str, str | None] = {}
    for emotion, raw in sprites.items():
        rel, anim = _project(raw.strip(), spine, diff_dir)
        sprites[emotion] = rel
        animations[emotion] = anim
    return {
        "sprites": sprites,
        "spine": spine,
        "animations": animations,
    }


def _project(raw: str, spine: str | None, diff_dir: str) -> tuple[str, str | None]:
    """资源 ID → 双投影（diff 相对路径, spine 动画名）。

    资源 ID 形态（无 / 无扩展名）: diff = {diff_dir}/{spine}_{id}.png, 动画 = id（需 spine）;
    路径形态（含 / 或扩展名）: diff = 原样; 动画 = stem 去 "{spine}_" 前缀（匹配才推导, 否则 None）。
    """
    if "/" not in raw and not Path(raw).suffix:
        # 资源 ID 形态（双投影, 2026-08-28 定稿）
        if spine:
            return f"{diff_dir}/{spine}_{raw}.png", raw
        return raw, None                       # 无 spine → 无模板可拼, 也无动画投影
    # 路径形态（旧格式 / 显式自绘图）
    stem = Path(raw).stem
    if spine and stem.startswith(f"{spine}_"):
        return raw, stem[len(spine) + 1:]
    return raw, None
