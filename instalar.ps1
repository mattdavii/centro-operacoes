# Instala o Centro de Operações no Windows (rodar de dentro da pasta clonada do GitHub).
#   powershell -ExecutionPolicy Bypass -File instalar.ps1 -Nome "Fulano" [-Apelidos "Fulano Silva,Fulaninho"] [-Organizacao "O&M · EMPRESA"] [-Kmz C:\usinas.kmz]
# Sem os parâmetros, pergunta. Pode rodar de novo a qualquer momento.
param([string]$Nome = "", [string]$Apelidos = "", [string]$Organizacao = "", [string]$Kmz = "", [int]$Porta = 47900)
$ErrorActionPreference = "Stop"
$Pasta = Split-Path -Parent $MyInvocation.MyCommand.Path
function Ok($t) { Write-Host "  [ok] $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "  [!]  $t" -ForegroundColor Yellow }
function Erro($t) { Write-Host "  [x]  $t" -ForegroundColor Red; exit 1 }

Write-Host "== Centro de Operações · instalação (Windows) =="

# 1) requisitos
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { Erro "Python 3 não encontrado. Instale em python.org (marque 'Add python.exe to PATH')." }
& $py -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"; if ($LASTEXITCODE) { Erro "Precisa de Python 3.9 ou mais novo." }
$pyw = Join-Path (Split-Path $py) "pythonw.exe"; if (-not (Test-Path $pyw)) { $pyw = $py }
Ok "Python ($py)"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Erro "git não encontrado. Instale em git-scm.com." }
Ok "git"
$wa = & $py -c "import sys; sys.path.insert(0, r'$Pasta'); import config; print(config.wa_comando())"
& $wa estado --json *> $null
if ($LASTEXITCODE) { Erro "O comando 'wa' do wa-app não respondeu ($wa). Abra o wa-app e confira se o WhatsApp está conectado." }
Ok "wa-app respondendo ($wa)"
$ip = $null
if (Get-Command tailscale -ErrorAction SilentlyContinue) { $ip = (& tailscale ip -4 2>$null | Select-Object -First 1) }
if ($ip) { Ok "Tailscale conectado ($ip)" } else { Aviso "Tailscale não está instalado ou conectado: o celular só conecta com Tailscale (tailscale.com/download)." }

# 2) perfil do usuário (os valores vão por variáveis de ambiente, sem risco com aspas)
if (-not $Nome) { $Nome = Read-Host "  Seu nome, como te chamam nos grupos (ex.: Mateus)" }
if (-not $Organizacao) { $Organizacao = Read-Host "  Organização/equipe para o topo do painel (opcional)" }
$env:CO_PASTA = $Pasta; $env:CO_NOME = $Nome; $env:CO_APELIDOS = $Apelidos; $env:CO_ORG = $Organizacao
$env:CO_KMZ = $Kmz; $env:CO_PORTA = "$Porta"
$Dados = & $py "$Pasta\ferramentas\configurar.py"
if ($LASTEXITCODE) { Erro "Não consegui gravar a configuração." }
Ok "configuração em $Dados\config.json"

# 3) liga junto com o Windows (pasta Inicializar) e já sobe agora
$shell = New-Object -ComObject WScript.Shell
$startup = [Environment]::GetFolderPath("Startup")
$lnk = $shell.CreateShortcut((Join-Path $startup "Centro de Operações (servidor).lnk"))
$lnk.TargetPath = $pyw; $lnk.Arguments = "`"$Pasta\servidor.py`""; $lnk.WorkingDirectory = $Pasta; $lnk.WindowStyle = 7; $lnk.Save()
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like "*servidor.py*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Process -FilePath $pyw -ArgumentList "`"$Pasta\servidor.py`"" -WorkingDirectory $Pasta -WindowStyle Hidden
Ok "servidor ligado (e liga sozinho quando o Windows iniciar)"

# 4) backup diário às 03:30
schtasks /Create /F /SC DAILY /ST 03:30 /TN "CentroOperacoesBackup" /TR "`"$pyw`" `"$Pasta\backup.py`"" | Out-Null
Ok "backup diário às 03:30"

# 5) liberar o celular (Tailscale) no firewall do Windows: precisa de administrador
$regra = "Centro de Operações (Tailscale)"
try {
  if (-not (Get-NetFirewallRule -DisplayName $regra -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $regra -Direction Inbound -Protocol TCP -LocalPort $Porta -RemoteAddress 100.64.0.0/10 -Action Allow | Out-Null
  }
  Ok "firewall: liberado para o celular pelo Tailscale"
} catch {
  Aviso "Não consegui liberar no firewall (precisa de administrador). Abra o PowerShell como administrador e rode:"
  Write-Host "      New-NetFirewallRule -DisplayName '$regra' -Direction Inbound -Protocol TCP -LocalPort $Porta -RemoteAddress 100.64.0.0/10 -Action Allow"
}

# 6) atalho de app (PWA): janela própria no Edge ou Chrome
$url = "http://127.0.0.1:$Porta"
$nav = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
         "$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") |
       Where-Object { Test-Path $_ } | Select-Object -First 1
foreach ($dest in @([Environment]::GetFolderPath("Programs"), [Environment]::GetFolderPath("Desktop"))) {
  $a = $shell.CreateShortcut((Join-Path $dest "Centro de Operações.lnk"))
  if ($nav) { $a.TargetPath = $nav; $a.Arguments = "--app=$url" } else { $a.TargetPath = $url }
  $a.IconLocation = "$Pasta\pwa\icone.ico"; $a.Save()
}
Ok "atalho 'Centro de Operações' no menu Iniciar e na área de trabalho"

# 7) espera a primeira sincronização
Write-Host -NoNewline "  ... aguardando o painel ler o WhatsApp pela primeira vez"
for ($i = 0; $i -lt 60; $i++) {
  try { if ((Invoke-WebRequest -UseBasicParsing "$url/api/dados" -TimeoutSec 3).Content -match '"pronto": true') { Write-Host ""; Ok "painel no ar em $url"; break } } catch {}
  Write-Host -NoNewline "."; Start-Sleep 3
}
Write-Host ""
Write-Host "== Pronto! =="
Write-Host "  - Abra 'Centro de Operações' no menu Iniciar (ou $url)."
Write-Host "  - Celular (Android): no painel, toque em 'Conectar celular' e siga o QR."
Write-Host "  - Mapa: coloque o KMZ das suas usinas em $Dados\usinas.kmz (ou rode de novo com -Kmz)."
Write-Host "  - Atualizações: o painel avisa quando sair versão nova (botão ATUALIZAR AGORA)."
