# Escenarios de la sonda en Windows nativo (spec 001 · 04 §2). Equivalente a run.sh.
# Uso: powershell -ExecutionPolicy Bypass -File tools\probe\run.ps1 -HostName codex|antigravity|opencode
param(
  [Parameter(Mandatory = $true)][ValidateSet('codex', 'antigravity', 'opencode')][string]$HostName,
  [string]$Work = (Join-Path $env:TEMP 'agent-plugins-probe'),
  [string]$CodexHooks = 'codex-hooks.json',
  [string]$Sandbox = 'workspace-write',
  [string]$Prompt = ''
)
$ErrorActionPreference = 'Continue'
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Src = Join-Path $Work 'src'
$Repo = Join-Path $Work "repo-$HostName"

New-Item -ItemType Directory -Force -Path $Work | Out-Null
Remove-Item -Recurse -Force $Src, $Repo -ErrorAction SilentlyContinue
Copy-Item -Recurse (Join-Path $Root 'tools\probe') $Src
Copy-Item -Recurse (Join-Path $Root 'tools\fake-llm') (Join-Path $Work 'fake-llm') -Force
New-Item -ItemType Directory -Force -Path $Repo | Out-Null
Set-Location $Repo
git init -q
"# Repo de prueba`n`nContenido de ejemplo.`n" | Set-Content -Encoding ascii README.md
git add README.md
git -c user.name=probe -c user.email=probe@example.invalid commit -q -m init

if ($CodexHooks -ne 'codex-hooks.json') {
  Copy-Item -Force (Join-Path $Src "plugin\$CodexHooks") (Join-Path $Src 'plugin\codex-hooks.json')
}
$Tools = if ($Prompt) { $Prompt } else { "Do these steps in order, one tool call each, without asking me anything: 1) run the shell command 'Get-ChildItem'. 2) read the file README.md with your file-reading tool. 3) create the file a.txt containing 'hola'. 4) edit a.txt replacing 'hola' with 'chau'. 5) run the shell command 'Remove-Item a.txt'. Then reply DONE." }

switch ($HostName) {
  'codex' {
    $env:CODEX_HOME = Join-Path $Work 'codex-home'
    Remove-Item -Recurse -Force $env:CODEX_HOME -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $env:CODEX_HOME | Out-Null
    Copy-Item (Join-Path $env:USERPROFILE '.codex\auth.json') $env:CODEX_HOME
    codex plugin marketplace add $Src | Out-Null
    codex plugin add probe@probe-market | Out-Null
    codex exec --json --skip-git-repo-check --dangerously-bypass-hook-trust -s $Sandbox $Tools *> tmp-tools.jsonl
  }
  'antigravity' {
    New-Item -ItemType Directory -Force -Path (Join-Path $Repo '.agents\plugins') | Out-Null
    Copy-Item -Recurse (Join-Path $Src 'plugin') (Join-Path $Repo '.agents\plugins\probe')
    agy -p $Tools --dangerously-skip-permissions --output-format json *> tmp-tools.json
  }
  'opencode' {
    $OcHome = Join-Path $Work 'oc-home'
    Remove-Item -Recurse -Force $OcHome -ErrorAction SilentlyContinue
    foreach ($d in 'config', 'data', 'state', 'cache') { New-Item -ItemType Directory -Force -Path (Join-Path $OcHome $d) | Out-Null }
    $env:XDG_CONFIG_HOME = Join-Path $OcHome 'config'; $env:XDG_DATA_HOME = Join-Path $OcHome 'data'
    $env:XDG_STATE_HOME = Join-Path $OcHome 'state'; $env:XDG_CACHE_HOME = Join-Path $OcHome 'cache'; $env:FAKE_LLM_KEY = 'x'
    $plugin = (Join-Path $Src 'plugin').Replace('\', '/')
    (Get-Content (Join-Path $Work 'fake-llm\opencode.template.json') -Raw).Replace('@PLUGINS@', "[`"$plugin`"]") |
      Set-Content -Encoding ascii opencode.json
    $script = if ($env:FAKE_SCRIPT) { $env:FAKE_SCRIPT } else { Join-Path $Work 'fake-llm\probe-tools-windows.json' }
    $fake = Start-Process python -ArgumentList @((Join-Path $Work 'fake-llm\server.py'), '--port', '18080', '--script', $script, '--log', (Join-Path $Repo 'fake-llm.jsonl')) -PassThru -WindowStyle Hidden
    Start-Sleep 2
    opencode run --standalone --auto --format json go *> tmp-tools.json
    Stop-Process -Id $fake.Id -ErrorAction SilentlyContinue
  }
}
$count = (Get-ChildItem -Recurse -File (Join-Path $Repo "tmp\probe") -ErrorAction SilentlyContinue).Count
"capturas: $count en $Repo\tmp\probe"
