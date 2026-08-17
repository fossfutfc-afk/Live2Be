# DeepSeek API 连通性测试脚本 (修复编码/引号问题)
$API_KEY = "sk-c9868b0154694732bf0388666a04a8a7"   # 替换为你的真实Key
$BASE_URL = "https://api.deepseek.com"
$MODEL = "deepseek-v4-flash"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  DeepSeek API Connectivity Test" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Test 1: List models
Write-Host "[1] Testing GET /models ..." -ForegroundColor Yellow
try {
    $headers = @{ "Authorization" = "Bearer $API_KEY"; "Accept" = "application/json" }
    $response = Invoke-RestMethod -Uri "$BASE_URL/models" -Method Get -Headers $headers -TimeoutSec 10
    Write-Host "SUCCESS - API key is valid." -ForegroundColor Green
    Write-Host "Available models:" -ForegroundColor Gray
    $response.data | ForEach-Object { Write-Host "  - $($_.id)" -ForegroundColor Gray }
    Write-Host ""
} catch {
    Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check: API key, network, or balance." -ForegroundColor Yellow
    exit 1
}

# Test 2: Chat completion
Write-Host "[2] Testing POST /chat/completions ..." -ForegroundColor Yellow
try {
    $headers = @{ "Authorization" = "Bearer $API_KEY"; "Content-Type" = "application/json" }
    $body = @{
        model = $MODEL
        messages = @( @{ role = "user"; content = "Reply with exactly: API_OK" } )
        thinking = @{ type = "disabled" }
        max_tokens = 16
    } | ConvertTo-Json -Depth 10

    $response = Invoke-RestMethod -Uri "$BASE_URL/chat/completions" -Method Post -Headers $headers -Body $body -TimeoutSec 30
    $reply = $response.choices[0].message.content
    Write-Host "SUCCESS - Reply: $reply" -ForegroundColor Green
    if ($reply -eq "API_OK") { Write-Host "All good! API is ready." -ForegroundColor Green }
} catch {
    Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Test completed." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan