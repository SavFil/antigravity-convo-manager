# Antigravity Conversation Manager — Plugin Installer
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$configDir = Join-Path $env:USERPROFILE ".gemini\config"
$pluginsDir = Join-Path $configDir "plugins"
$targetPluginDir = Join-Path $pluginsDir "conversation-manager"
$mcpConfigFile = Join-Path $configDir "mcp_config.json"
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    $pythonExe = "python"
}

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " Installing Antigravity Conversation Manager Plugin" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Source directory: $scriptDir"
Write-Host "Config directory: $configDir"

# 1. Ensure config and plugins directories exist
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}
if (-not (Test-Path $pluginsDir)) {
    New-Item -ItemType Directory -Path $pluginsDir -Force | Out-Null
}

# 2. Link plugin to ~/.gemini/config/plugins/conversation-manager
if (Test-Path $targetPluginDir) {
    Write-Host "Removing existing plugin link: $targetPluginDir" -ForegroundColor Yellow
    cmd /c "rmdir `"$targetPluginDir`"" 2>$null
    if (Test-Path $targetPluginDir) {
        Remove-Item -Path $targetPluginDir -Recurse -Force
    }
}

Write-Host "Creating plugin junction: $targetPluginDir -> $scriptDir" -ForegroundColor Green
cmd /c "mklink /J `"$targetPluginDir`" `"$scriptDir`"" | Out-Null

# 3. Register MCP Server in mcp_config.json
$mcpJson = @{ mcpServers = @{} }
if (Test-Path $mcpConfigFile) {
    try {
        $raw = Get-Content $mcpConfigFile -Raw -Encoding UTF8
        if ($raw.Trim()) {
            $mcpJson = $raw | ConvertFrom-Json
            if (-not $mcpJson.mcpServers) {
                $mcpJson | Add-Member -MemberType NoteProperty -Name "mcpServers" -Value @{}
            }
        }
    } catch {
        Write-Warning "Could not parse existing mcp_config.json, creating backup."
        Copy-Item $mcpConfigFile "$mcpConfigFile.bak"
    }
}

$mcpServerPath = Join-Path $scriptDir "mcp_server.py"

$serverDef = [PSCustomObject]@{
    command = $pythonExe
    args = @($mcpServerPath)
}

if ($mcpJson.mcpServers -is [System.Management.Automation.PSCustomObject]) {
    $mcpJson.mcpServers | Add-Member -MemberType NoteProperty -Name "conversation-manager" -Value $serverDef -Force
} else {
    $mcpJson.mcpServers["conversation-manager"] = $serverDef
}

$updatedJson = $mcpJson | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($mcpConfigFile, $updatedJson, [System.Text.Encoding]::UTF8)

Write-Host "`nPlugin successfully installed!" -ForegroundColor Green
Write-Host "1. MCP Server registered in: $mcpConfigFile"
Write-Host "2. Plugin linked in: $targetPluginDir"
Write-Host "`nAntigravity agents can now use the 'conversation-manager' skill and tools."
Write-Host "You can also launch the Web GUI anytime by running: .\launch-web-ui.bat" -ForegroundColor Cyan
