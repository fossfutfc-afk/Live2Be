<#
  build.ps1 — 打一个**能双击跑**的 onedir 包（dist/Live2Be/Live2Be.exe）

  先决条件（本脚本不代装）:
    C:\Users\johnf\miniconda3\envs\live2be\python.exe -m pip install pyinstaller

  用法（在仓根或任意目录）:
    pwsh -File packaging/build.ps1                 # 完整版: 四角色 + 435 张背景随包（~290 MB, 断网可玩）
    pwsh -File packaging/build.ps1 -Slim           # 轻量版: 素材只带 0.4 MB（~131 MB, 立绘走「素材」页下载）
    pwsh -File packaging/build.ps1 -NoClean        # 复用上次的 build/（迭代快）

  素材口径由 `packaging/collect_assets.py` 决定（`full` / `minimal`）:
  只带产品**真正读**的东西 —— `diff/`（119 MB, 只有 CLI 用）与没被地点表引用的背景
  （151 MB）都不进包。

  它做四件事:
    1. 检查 pyinstaller 在不在
    2. 报一次素材清单与体积
    3. PyInstaller 打包（主程序 onedir + 配置助手 onefile）
    4. 把 config/ 与素材拷到 **exe 同级**（五个根: APP_ROOT = exe 同级, 不拷进 _internal）

  ⚠️ 首次运行前要有 LLM key: 写 dist/Live2Be/.env（`LLM_API_KEY=...`）或启动后在设置页填。
#>
[CmdletBinding()]
param(
    [switch]$Slim,
    [switch]$NoClean
)

$AssetMode = if ($Slim) { 'minimal' } else { 'full' }

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

# ── 2. 素材清单（先看它挑了什么、多大）──────────────────────────────────
Write-Host ("[1/4] 素材清单（{0}）:" -f $AssetMode)
& $Py packaging/collect_assets.py --src assets --config config --mode $AssetMode --dry-run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ── 3. 打包 ─────────────────────────────────────────────────────────────
Write-Host '[2/4] PyInstaller（主程序 onedir）:'
$clean = if ($NoClean) { '--noconfirm' } else { '--noconfirm --clean' }
$pyArgs = @('-m', 'PyInstaller') + ($clean -split ' ') + @('packaging/live2be.spec')
& $Py @pyArgs
if ($LASTEXITCODE -ne 0) { Write-Host '打包失败（看上面最后几行）' -ForegroundColor Red; exit $LASTEXITCODE }

# ── 3b. 「资源配置」辅助工具（onefile，和主程序放同一目录）───────────────
Write-Host '[3/4] PyInstaller（配置助手 onefile）:'
$toolArgs = @('-m', 'PyInstaller') + ($clean -split ' ') + @('packaging/setup_tool.spec')
& $Py @toolArgs
if ($LASTEXITCODE -ne 0) { Write-Host '配置助手打包失败' -ForegroundColor Red; exit $LASTEXITCODE }

# ── 4. 组装 exe 同级的东西 ──────────────────────────────────────────────
Write-Host '[4/4] 组装:'
$Dist = Join-Path $Root 'dist\Live2Be'
if (-not (Test-Path $Dist)) { Write-Host "  没找到 $Dist（PyInstaller 没产出?）" -ForegroundColor Red; exit 1 }

$SetupExe = Join-Path $Root 'dist\Live2BeSetup.exe'
if (Test-Path $SetupExe) {
    Copy-Item $SetupExe (Join-Path $Dist 'Live2BeSetup.exe') -Force
    Write-Host '   Live2BeSetup.exe → exe 同级（配置助手；也可以单独双击）'
} else {
    Write-Host '   ⚠ 没找到 dist\Live2BeSetup.exe（配置助手没出来）' -ForegroundColor Yellow
}

# ⚠️ 先删目标再拷: `Copy-Item -Recurse` 到已存在的目录会套成 config/config
$DistConfig = Join-Path $Dist 'config'
if (Test-Path $DistConfig) { Remove-Item $DistConfig -Recurse -Force }
Copy-Item (Join-Path $Root 'config') $DistConfig -Recurse -Force
Write-Host '   config/ → exe 同级（角色卡 / 世界观）'

$DistAssets = Join-Path $Dist 'assets'
if (Test-Path $DistAssets) { Remove-Item $DistAssets -Recurse -Force }
& $Py packaging/collect_assets.py --src assets --config config --mode $AssetMode --dst $DistAssets
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ("   assets/ → exe 同级（口径 {0}）" -f $AssetMode)

$size = (Get-ChildItem $Dist -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ''
Write-Host ("完成: {0}" -f $Dist) -ForegroundColor Green
Write-Host ("总体积: {0:N0} MB" -f $size) -ForegroundColor Green
Write-Host '跑它: 双击 Live2Be.exe（浏览器会自己打开; --window 用原生窗口）'
Write-Host '停它: 前端菜单「关闭服务」（Ctrl+C 被忽略）'
Write-Host ''
Write-Host '⚠️ 首次运行前给 LLM key: 在 dist/Live2Be/ 放一个 .env, 内容 LLM_API_KEY=...' -ForegroundColor Yellow
Write-Host '   （或在设置页填; 没有 key 时聊天会报错，但页面能打开）' -ForegroundColor Yellow
Write-Host ''
Write-Host '素材包（立绘 / 背景）另外切 — 只有 -Slim 版才需要（约半分钟）:' -ForegroundColor Cyan
Write-Host ("  {0} packaging/make_packs.py --dst dist/packs" -f $Py) -ForegroundColor Cyan
Write-Host '  切好后把 dist/packs 传到你的静态托管，把 manifest.json 的地址填进「素材」页即可。' -ForegroundColor Cyan
