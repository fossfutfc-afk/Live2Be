<#
  build.ps1 — 打一个**能双击跑**的 onedir 包（dist/Live2Be/Live2Be.exe）

  先决条件（本脚本不代装）:
    C:\Users\johnf\miniconda3\envs\live2be\python.exe -m pip install pyinstaller

  用法（在仓根或任意目录）:
    pwsh -File packaging/build.ps1                 # 全量: 打包 + 拷 config + 拷样张
    pwsh -File packaging/build.ps1 -SkipSamples    # 不拷样张（包更小, 但没图）
    pwsh -File packaging/build.ps1 -NoClean        # 复用上次的 build/（迭代快）

  它做四件事:
    1. 检查 pyinstaller 在不在
    2. 报一次样张清单与体积（assets 全量 448 MB, 只挑 ~106 MB）
    3. PyInstaller 打包（spec 在 packaging/live2be.spec）
    4. 把 config/ 与样张拷到 **exe 同级**（五个根: APP_ROOT = exe 同级, 不拷进 _internal）

  ⚠️ 首次运行前要有 LLM key: 写 dist/Live2Be/.env（`LLM_API_KEY=...`）或启动后在设置页填。
#>
[CmdletBinding()]
param(
    [switch]$SkipSamples,
    [switch]$NoClean
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = 'C:\Users\johnf\miniconda3\envs\live2be\python.exe'
if (-not (Test-Path $Py)) { $Py = 'python' }

Write-Host ''
Write-Host '== Live2Be 打包 ==' -ForegroundColor Cyan
Write-Host ("   python : {0}" -f $Py)
Write-Host ("   仓库   : {0}" -f $Root)

# ── 1. pyinstaller 在不在 ────────────────────────────────────────────────
& $Py -c "import PyInstaller, sys; print('   pyinstaller:', PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host '没装 pyinstaller —— 先跑这一条（本脚本不代装）:' -ForegroundColor Yellow
    Write-Host ("  {0} -m pip install pyinstaller" -f $Py) -ForegroundColor Yellow
    exit 1
}

# ── 2. 样张清单（先看它挑了什么、多大）─────────────────────────────────
if (-not $SkipSamples) {
    Write-Host '[1/3] 样张清单:'
    & $Py packaging/collect_samples.py --src assets --dry-run
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host '[1/3] 样张: 按 -SkipSamples 跳过（包里没有 assets/）' -ForegroundColor Yellow
}

# ── 3. 打包 ─────────────────────────────────────────────────────────────
Write-Host '[2/3] PyInstaller:'
$clean = if ($NoClean) { '--noconfirm' } else { '--noconfirm --clean' }
$args = @('-m', 'PyInstaller') + ($clean -split ' ') + @('packaging/live2be.spec')
& $Py @args
if ($LASTEXITCODE -ne 0) { Write-Host '打包失败（看上面最后几行）' -ForegroundColor Red; exit $LASTEXITCODE }

# ── 4. 组装 exe 同级的东西 ──────────────────────────────────────────────
Write-Host '[3/3] 组装:'
$Dist = Join-Path $Root 'dist\Live2Be'
if (-not (Test-Path $Dist)) { Write-Host "  没找到 $Dist（PyInstaller 没产出?）" -ForegroundColor Red; exit 1 }

Copy-Item (Join-Path $Root 'config') (Join-Path $Dist 'config') -Recurse -Force
Write-Host '   config/ → exe 同级（角色卡 / 世界观）'

if (-not $SkipSamples) {
    & $Py packaging/collect_samples.py --src assets --dst (Join-Path $Dist 'assets')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$size = (Get-ChildItem $Dist -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ''
Write-Host ("完成: {0}" -f $Dist) -ForegroundColor Green
Write-Host ("总体积: {0:N0} MB" -f $size) -ForegroundColor Green
Write-Host '跑它: 双击 Live2Be.exe（浏览器会自己打开; --window 用原生窗口）'
Write-Host '停它: 前端菜单「关闭服务」（Ctrl+C 被忽略）'
Write-Host ''
Write-Host '⚠️ 首次运行前给 LLM key: 在 dist/Live2Be/ 放一个 .env, 内容 LLM_API_KEY=...' -ForegroundColor Yellow
Write-Host '   （或在设置页填; 没有 key 时聊天会报错，但页面能打开）' -ForegroundColor Yellow
