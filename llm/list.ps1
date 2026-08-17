$headers = New-Object "System.Collections.Generic.Dictionary[[String],[String]]"
$headers.Add("Accept", "application/json")
$headers.Add("Authorization", "Bearer sk-c9868b0154694732bf0388666a04a8a7")

$response = Invoke-RestMethod 'https://api.deepseek.com/models' -Method 'GET' -Headers $headers
$response | ConvertTo-Json