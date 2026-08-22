# scan_diff.ps1 — 递归扫描 diff 目录, 生成情绪词表 yml 雏形（_media.yml 的替代/并行真源）
#
# 为什么是 yml 而不是 json: yml 支持注释 —— 每个情绪条目可以带一行注释,
# 给主 LLM 提供示范（few-shot）; json 无注释, 示范没地方放。
#
# 用法（在 Live2Be 项目根运行）:
#   powershell -ExecutionPolicy Bypass -File scan_diff.ps1
#   powershell -ExecutionPolicy Bypass -File scan_diff.ps1 -DiffDir assets/illustration/igusa_haruka/diff -OutFile assets/illustration/igusa_haruka/emotions.yml
#
# 输出格式（emotions: 键 = 情绪名id, 值 = diff/ 相对路径, 行尾注释 = 示范）:
#   emotions:
#     : diff/haruka_spr_01.png
#   键默认留空 —— 直接在每行的冒号前打情绪名即可, 不用删任何占位
#   （值里的文件名可对照原图; 填完全部键前不要用 yaml 解析, 空键是重复键）
#   行尾可加 # 示范注释（引擎逐行解析 键:路径 # 示范, 会被提取为 few-shot）;
#   改示范只动注释别动键, id 保持稳定。
#   - 编码 UTF-8（无 BOM）; 直接 stdout 输出（可重定向）或 -OutFile 落盘

param(
    [string]$DiffDir = "assets/illustration/igusa_haruka/diff",
    [string]$OutFile  = ""
)

$exts = @(".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

if (-not (Test-Path $DiffDir)) {
    Write-Error "目录不存在: $DiffDir"
    exit 1
}
$diffPath = (Resolve-Path $DiffDir).Path

$files = Get-ChildItem -Path $diffPath -Recurse -File |
    Where-Object { $exts -contains $_.Extension.ToLower() } |
    Sort-Object Name

if (-not $files) {
    Write-Warning "目录 $diffPath 下没有图片文件"
    exit 1
}

# 逐行拼 YAML: 头部注释说明用法 + emotions: 列表（键留空, 值=diff/ 相对路径）
$lines = [System.Collections.Generic.List[string]]::new()
$lines.Add('# 情绪词表雏形（scan_diff.ps1 自动生成）— 键 = 情绪名id, 值 = diff/ 相对路径, 行尾注释 = 给主 LLM 的示范')
$lines.Add('# 键已留空: 直接在每行的冒号前填情绪名（值里的文件名可对照原图）; 行尾可加 # 示范（引擎逐行解析, 提取为 few-shot）')
$lines.Add('# 填完全部键前不要用 yaml 解析（空键是重复键）; 改示范只动注释别动键, id 保持稳定')
$lines.Add('# 例: 库呼呼: diff/haruka_spr_01.png   # 阿露招牌笑: "（库呼呼地笑了）"')
$lines.Add('emotions:')
foreach ($f in $files) {
    $rel = $f.FullName.Substring($diffPath.Length).TrimStart('\', '/')
    $rel = ($rel -replace '\\', '/')
    $lines.Add("  : diff/$rel")
}

$yaml = $lines -join "`n"

if ($OutFile) {
    # UTF-8 无 BOM（.NET 方法兼容 PS 5.1 / 7）
    [System.IO.File]::WriteAllText($OutFile, $yaml, [System.Text.UTF8Encoding]::new($false))
    Write-Host "已写入: $OutFile （$($files.Count) 个文件）"
} else {
    $yaml
}
