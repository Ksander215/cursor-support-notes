param(
  [string]$ProdUser = $env:PROD_USER,
  [string]$ProdHost = $(if ($env:PROD_HOST) { $env:PROD_HOST } else { "sec-scanner.pro" }),
  [int]$ProdPort = $(if ($env:PROD_PORT) { [int]$env:PROD_PORT } else { 22 }),
  [string]$ProdPath = $(if ($env:PROD_PATH) { $env:PROD_PATH } else { "/opt/sec-scanner" }),
  [string]$DestDir = $(if ($env:DEST_DIR) { $env:DEST_DIR } else { ".\_prod_dump" })
)

if (-not $ProdUser) { $ProdUser = "root" }

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

function Test-Command($name) {
  $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

if (Test-Command "rsync") {
  Write-Host "Using rsync..."
  $ssh = "ssh -p $ProdPort -o StrictHostKeyChecking=accept-new"
  rsync -avz --delete -e $ssh "$ProdUser@$ProdHost`:$ProdPath/" "$DestDir\$(Split-Path -Leaf $ProdPath)\" 
  exit 0
}

if (-not (Test-Command "scp")) {
  throw "Не найдено ни rsync, ни scp. Установи OpenSSH Client (Windows Features) или используй WSL."
}

Write-Host "Using scp (без delete/инкрементальности)..."
scp -P $ProdPort -r "$ProdUser@$ProdHost`:$ProdPath" $DestDir

