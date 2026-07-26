# Fusion-CLI Windows kurulumu.
#
#   .\install.ps1          → KULLANICI kurulumu: izole, global `fusion` komutu
#   .\install.ps1 -Dev     → GELİŞTİRİCİ kurulumu: repo içinde .venv + editable
#
# Bu betik `setup.sh` ile AYNI kararları verir ama mantığı kopyalamaz: yöntem
# tespiti, PATH denetimi ve kurulum durumu Python tarafındadır (`fusion doctor`,
# `fusion_cli.install`). Buradaki iş yalnızca doğru kurucuyu seçmek ve çağırmak.
#
# Yeniden çalıştırmak güvenlidir: var olan yapılandırma ve API anahtarları
# HİÇBİR koşulda silinmez.

[CmdletBinding()]
param(
    [switch]$Dev
)

$ErrorActionPreference = 'Stop'

# Türkçe çıktı bozulmasın: PowerShell 5.1 varsayılan olarak UTF-8 kullanmaz.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

function Adim($mesaj)  { Write-Host "> $mesaj" -ForegroundColor DarkGray }
function Bitti($mesaj) { Write-Host "OK $mesaj" -ForegroundColor Green }
function Uyari($mesaj) { Write-Host "!  $mesaj" -ForegroundColor Yellow }
function Hata($mesaj)  { Write-Host "X  $mesaj" -ForegroundColor Red; exit 1 }

Set-Location -Path $PSScriptRoot

# --- 1. Uygun Python ---------------------------------------------------------- #
# Sürüm sabit çağrılmaz: makinede hangi 3.11+ varsa o kullanılır.
$python = $null
foreach ($aday in @('py -3.13', 'py -3.12', 'py -3.11', 'python', 'python3')) {
    $parcalar = $aday.Split(' ')
    $komut = $parcalar[0]
    if (-not (Get-Command $komut -ErrorAction SilentlyContinue)) { continue }
    $argumanlar = @($parcalar[1..($parcalar.Length - 1)]) + @(
        '-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
    )
    & $komut @argumanlar 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $aday; break }
}
if (-not $python) {
    Hata 'Python 3.11 veya üstü bulunamadi. Kur: https://www.python.org/downloads/'
}
Bitti "Python bulundu: $python"

$pyKomut = $python.Split(' ')[0]
$pyArg = @()
if ($python.Split(' ').Length -gt 1) { $pyArg = @($python.Split(' ')[1]) }

# --- 2a. KULLANICI kurulumu --------------------------------------------------- #
# Tercih sirasi uv -> pipx -> pip --user. Editable DEGILDIR: kullanici repo
# klasorunu silse bile `fusion` calismaya devam etmeli.
if (-not $Dev) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Adim 'uv ile kuruluyor (izole, global)...'
        uv tool install --force .
        if ($LASTEXITCODE -ne 0) { Hata 'uv ile kurulum basarisiz.' }
        $yontem = 'uv'
    }
    elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
        Adim 'pipx ile kuruluyor (izole, global)...'
        pipx install --force .
        if ($LASTEXITCODE -ne 0) { Hata 'pipx ile kurulum basarisiz.' }
        $yontem = 'pipx'
    }
    else {
        # `pip install --user` guvenilir degil: PEP 668 ile yonetilen Python
        # kurulumlarinda hata verir. Bunun yerine pipx'in yaptigi elle yapilir:
        # kullanici veri dizininde adanmis bir sanal ortam.
        Adim 'Izole sanal ortam kuruluyor (uv/pipx bulunamadi)...'
        Uyari 'Daha temiz kurulum icin onerilen: uv (https://docs.astral.sh/uv/) ya da pipx.'
        $veriDir = Join-Path $env:LOCALAPPDATA 'fusion-cli'
        $aracVenv = Join-Path $veriDir 'venv'
        & $pyKomut @pyArg -m venv $aracVenv
        if ($LASTEXITCODE -ne 0) { Hata 'Sanal ortam olusturulamadi.' }
        & "$aracVenv\Scripts\python.exe" -m pip install --quiet --upgrade pip
        & "$aracVenv\Scripts\python.exe" -m pip install --quiet .
        if ($LASTEXITCODE -ne 0) {
            Uyari 'Sessiz kurulum basarisiz; gercek hata asagida:'
            & "$aracVenv\Scripts\python.exe" -m pip install .
            if ($LASTEXITCODE -ne 0) { Hata 'Kurulum basarisiz.' }
        }
        $yontem = "izole venv ($aracVenv)"
        $script:fallbackBin = Join-Path $aracVenv 'Scripts\fusion.exe'
    }
    Bitti "Kuruldu ($yontem)."

    # `fusion` PATH'te mi? Degilse kullanici-local Scripts dizininden calistir;
    # PATH ipucunu `fusion doctor` uretir (mantik Python tarafinda, kopyalanmaz).
    $fusion = 'fusion'
    if (-not (Get-Command fusion -ErrorAction SilentlyContinue)) {
        if ($script:fallbackBin -and (Test-Path $script:fallbackBin)) {
            $fusion = $script:fallbackBin
        }
        else {
            $taban = & $pyKomut @pyArg -c 'import site; print(site.getuserbase())'
            $aday = Join-Path $taban 'Scripts\fusion.exe'
            if (Test-Path $aday) { $fusion = $aday }
        }
    }

    # Smoke test: "kuruldu" demek calistigini gostermez.
    Adim 'Kurulum dogrulaniyor...'
    & $fusion version | Out-Null
    if ($LASTEXITCODE -ne 0) { Hata "Kuruldu ama 'fusion version' calismiyor." }
    & $fusion --help | Out-Null
    if ($LASTEXITCODE -ne 0) { Hata "Kuruldu ama 'fusion --help' calismiyor." }
    Bitti 'Dogrulandi.'

    Write-Host ''
    & $fusion setup
    Write-Host ''
    & $fusion doctor
    if ($LASTEXITCODE -eq 0) {
        Write-Host ''
        Bitti 'Hazir. Baslatmak icin: fusion'
    }
    else {
        Write-Host ''
        Uyari 'Kurulum tamamlandi ama yapilandirma eksik. Yukaridaki satirlar ne yapilacagini soyluyor.'
    }
    exit 0
}

# --- 2b. GELİŞTİRİCİ kurulumu ------------------------------------------------- #
$venv = '.venv'
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Adim 'Sanal ortam olusturuluyor...'
    & $pyKomut @pyArg -m venv $venv
    if ($LASTEXITCODE -ne 0) { Hata 'venv olusturulamadi.' }
}
Bitti "Sanal ortam hazir: $venv"

$venvPy = "$venv\Scripts\python.exe"
Adim 'Bagimliliklar kuruluyor (chromadb buyuk; ilk kurulum birkac dakika surebilir)...'
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    # Sessiz kurulum basarisizsa gercek pip hatasini goster: "basarisiz" cumlesi
    # tek basina kullaniciyi ileri goturmez.
    Uyari 'Sessiz kurulum basarisiz; gercek hata asagida:'
    & $venvPy -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { Hata 'Kurulum basarisiz.' }
}
Bitti 'Paket ve gelistirme araclari kuruldu (editable).'

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Bitti '.env olusturuldu (proje bazli override).'
}
else {
    Bitti '.env zaten var, dokunulmadi.'
}

Write-Host ''
& "$venv\Scripts\fusion.exe" setup
Write-Host ''
& "$venv\Scripts\fusion.exe" doctor
Write-Host ''
Bitti "Gelistirici kurulumu hazir. Baslatmak icin: .\$venv\Scripts\fusion.exe"
