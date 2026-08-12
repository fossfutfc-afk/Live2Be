# IDE-Resources（辅助项目）

Live2Be 的独立辅助工具：面向不会手写 YAML 的用户，把“角色配置生成”和“资源获取/导入”合并到一个程序里。

## 目标

- 用表单向导/可视化编辑代替手写 `config/characters/<id>/` 下的 YAML
- 自动生成符合 Live2Be 约定的 `profile.yml`、`personality.yml` 等文件
- 校验 `REQ~` / `SIG~` 字段，避免缺必填配置
- 抓取、下载并整理角色立绘、差分、背景等资源到 `Live2Be/resources/`
- 生成/更新角色目录时保持 Live2Be 现有配置结构兼容

## 当前状态

- 项目目录和说明已建立，具体功能尚未实现
- 下一步可先确定：GUI/CLI/Web 形态、资源来源、导入后如何映射到现有 Live2Be 配置

## 建议目录结构

```text
ide_resources/
  README.md
  src/ide_resources/
    __init__.py
    config_editor/        # YAML 可视化编辑/生成
    resource_fetcher/     # 资源抓取、下载、命名整理
    cli.py                # 入口（待定）
```

## 边界

- 只负责生成 Live2Be 可读的配置和整理可导入资源
- 不替代 Live2Be 的 LLM 对话、羁绊剧情或渲染引擎
- 不绕过角色的资源授权约束；抓取来源和许可证需要单独确认
