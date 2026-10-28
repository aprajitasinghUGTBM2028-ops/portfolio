# Litmus MCP Server — one-shot installer for Claude Desktop (Windows)
# Paste this entire script into PowerShell and press Enter.

Write-Host "=== Litmus MCP Installer ===" -ForegroundColor Cyan

# 1. Install Python dependencies
Write-Host "`n[1/4] Installing Python dependencies..." -ForegroundColor Yellow
pip install openai requests beautifulsoup4 mcp
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip failed. Try: py -m pip install openai requests beautifulsoup4 mcp" -ForegroundColor Red
    exit 1
}

# 2. Clone or update repo
$repoDir = "$HOME\Documents\portfolio"
if (Test-Path "$repoDir\.git") {
    Write-Host "`n[2/4] Updating existing repo..." -ForegroundColor Yellow
    Push-Location $repoDir
    git pull origin main
    Pop-Location
} else {
    Write-Host "`n[2/4] Cloning repo..." -ForegroundColor Yellow
    git clone https://github.com/aprajitasinghUGTBM2028-ops/portfolio.git $repoDir
}

# 3. Prompt for API key
Write-Host "`n[3/4] OpenAI API key needed." -ForegroundColor Yellow
$apiKey = Read-Host "Paste your OpenAI API key (starts with sk-)"

# 4. Write Claude Desktop config
$configDir = "$env:APPDATA\Claude"
$configFile = "$configDir\claude_desktop_config.json"
$serverPath = "$repoDir\claim-checker\mcp_server.py" -replace '\\', '\\\\'

Write-Host "`n[4/4] Configuring Claude Desktop..." -ForegroundColor Yellow

if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

if (Test-Path $configFile) {
    # Read existing config and merge
    $config = Get-Content $configFile -Raw | ConvertFrom-Json
    if (-not $config.mcpServers) {
        $config | Add-Member -NotePropertyName mcpServers -NotePropertyValue @{} -Force
    }
} else {
    $config = @{ mcpServers = @{} } | ConvertTo-Json | ConvertFrom-Json
}

# Build the litmus server entry
$litmusEntry = @{
    command = "python"
    args = @(($repoDir + "\claim-checker\mcp_server.py"))
    env = @{
        OPENAI_API_KEY = $apiKey
    }
}

# Add or overwrite the litmus entry
if ($config.mcpServers -is [PSCustomObject]) {
    $config.mcpServers | Add-Member -NotePropertyName "litmus" -NotePropertyValue $litmusEntry -Force
} else {
    $config.mcpServers["litmus"] = $litmusEntry
}

$config | ConvertTo-Json -Depth 10 | Set-Content $configFile -Encoding UTF8
Write-Host "`nConfig written to: $configFile" -ForegroundColor Green

Write-Host "`n=== Done! ===" -ForegroundColor Cyan
Write-Host "Now restart Claude Desktop completely (quit from system tray, then reopen)."
Write-Host "The 'litmus_test' tool will appear in Claude Desktop."
Write-Host "`nTest it by asking Claude: 'Analyze this tool: https://github.com/anthropics/knowledge-work-plugins'"
