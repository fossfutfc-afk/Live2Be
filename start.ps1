<#
  start.ps1 — 一键起本机开发栈（LM Studio 的 embedding 服务 + Live2Be WebGUI）

  它做三件事，**都不碰 data/**（数据只由应用自己按正常流程写）:
    1. embedding 服务: 1235 没人在听时 → `lms server start --port 1235`
       （起不来**只警告不拦** —— 项目对 embed 缺失本来就是静默降级: digest 语义召回
        退化成字面命中 `digest_embed fn=none reason=model_missing`）
    2. 用**项目自己的体检命令**验一次（抄 settings.toml 里那条排查注释）——
       名字打错 / 模型没加载会在这里现形，而不是每轮 digest 悄悄降级
    3. 前台起应用（Ctrl+C 停）: 默认 WebGUI，`-Cli` 换终端版

  用法（在本目录，或任意目录用全路径）:
    pwsh -File start.ps1                    # WebGUI :8000 + embed :1235
    pwsh -File start.ps1 -Port 8080         # 换 WebGUI 端口
    pwsh -File start.ps1 -NoEmbed           # 不起 lms（纯文字降级照跑）
    pwsh -File start.ps1 -EmbedOnly         # 只把 embedding 服务弄好就退出
    pwsh -File start.ps1 -Cli               # 起终端版 MMT（cli.main）
    start.cmd                               # 双击也行（它会转调本脚本）

  ⚠️ Ctrl+C 只停**应用**；LM Studio 的服务还在。要停它: `lms server stop`
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [int]$EmbedPort = 1235,
    [string]$EmbedModel = "text-embedding-qwen3-embedding-0.6b",
    [switch]$NoEmbed,
    [switch]$EmbedOnly,
    [switch]$Cli
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root

# python: 优先本机 live2be 环境（与 tools/*.cmd 同一写法），找不到再用 PATH 上的
$Py = 'C:\Users\johnf\miniconda3\envs\live2be\python.exe'
if (-not (Test-Path $Py)) { $Py = 'python' }

function Test-Port([int]$P) {
    [bool](Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue)
}

function Get-PortOwner([int]$P) {
    $c = Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue |
         Select-Object -First 1
    if (-not $c) { return $null }
    $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    if (-not $proc) { return "PID $($c.OwningProcess)" }
    "{0} (PID {1}, 启动于 {2})" -f $proc.ProcessName, $proc.Id,
        $proc.StartTime.ToString('MM-dd HH:mm:ss')
}

function Get-Lms {
    $c = Get-Command lms -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $guess = Join-Path $env:USERPROFILE '.lmstudio\bin\lms.exe'
    if (Test-Path $guess) { return $guess }
    $null
}

Write-Host ''
Write-Host '== Live2Be 启动 ==' -ForegroundColor Cyan
Write-Host ("   仓库   : {0}" -f $Root)
Write-Host ("   python : {0}" -f $Py)

# ── 1/2. embedding 服务 ────────────────────────────────────────────────
if ($NoEmbed) {
    Write-Host '[1-2/3] embedding: 按 -NoEmbed 跳过（digest/召回会退化成字面命中）' -ForegroundColor Yellow
} else {
    if (Test-Port $EmbedPort) {
        Write-Host ("[1/3] embedding: {0} 已在听 ✓（跳过启动）" -f $EmbedPort) -ForegroundColor Green
    } else {
        $lms = Get-Lms
        if (-not $lms) {
            Write-Host '[1/3] embedding: 找不到 lms（LM Studio CLI）⇒ 跳过（不影响剧情，只影响召回质量）' -ForegroundColor Yellow
        } else {
            Write-Host ("[1/3] embedding: 起 LM Studio 服务，端口 {0} …" -f $EmbedPort)
            Start-Process -FilePath $lms -WindowStyle Hidden `
                -ArgumentList @('server', 'start', '--port', "$EmbedPort") | Out-Null
            for ($i = 0; $i -lt 30 -and -not (Test-Port $EmbedPort); $i++) {
                Start-Sleep -Milliseconds 500
            }
            if (Test-Port $EmbedPort) {
                Write-Host ("      端口 {0} 起来了 ✓" -f $EmbedPort) -ForegroundColor Green
            } else {
                Write-Host ("      ⚠ 端口 {0} 仍没在听 —— 手动跑: lms server start --port {0}" -f $EmbedPort) -ForegroundColor Yellow
            }
        }
    }
    if (Test-Port $EmbedPort) {
        Write-Host '[2/3] embedding 体检（与每轮 digest 走同一条路）:'
        & $Py -c 'from core.rag.embedder import LocalEmbedder as L; e = L(); print("      base_url =", e.base_url); print("      model    =", e.model); ok = e.health(); print("      health   =", ok); raise SystemExit(0 if ok else 3)'
        if ($LASTEXITCODE -ne 0) {
            Write-Host ("      ⚠ health 不过 ⇒ digest 会静默降级成字面命中。模型没加载就: lms load {0}" -f $EmbedModel) -ForegroundColor Yellow
        }
    }
}
if ($EmbedOnly) {
    Write-Host '(-EmbedOnly) 到此为止。'
    exit 0
}

# ── 3. 应用（前台）──────────────────────────────────────────────────────
if (Test-Port $Port) {
    Write-Host ("⚠ 端口 {0} 已被占用: {1}" -f $Port, (Get-PortOwner $Port)) -ForegroundColor Yellow
    Write-Host '   多半是上一次没关掉的实例（旧进程会继续吃旧代码）——换端口用 -Port，或先停它。' -ForegroundColor Yellow
}

Write-Host ("   诊断日志（应用自己写）: {0}" -f (Join-Path $Root 'data\diag\live2be.log'))
Write-Host ''

if ($Cli) {
    Write-Host '[3/3] 终端版 MMT（cli.main）—— Ctrl+C 退出' -ForegroundColor Green
    & $Py -m cli.main
} else {
    Write-Host ("[3/3] WebGUI → http://127.0.0.1:{0}   （Ctrl+C 停）" -f $Port) -ForegroundColor Green
    Write-Host '   ⚠ Ctrl+C 只停应用；embedding 服务还在 —— 要停: lms server stop' -ForegroundColor DarkGray
    & $Py -m uvicorn webgui.app:app --host 127.0.0.1 --port "$Port"
}
exit $LASTEXITCODE
