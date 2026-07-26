#!/bin/sh
# Fusion-CLI tek adımlık kurulum.
#
#   ./setup.sh          → çalıştırmak için gerekenler
#   ./setup.sh --dev    → geliştirme araçları da (ruff, mypy, pytest)
#
# Yeniden çalıştırmak güvenlidir: var olan .venv ve .env'e dokunulmaz, eksik olan
# tamamlanır. Anahtarların bulunduğu .env HİÇBİR koşulda üzerine yazılmaz.
#
# POSIX sh: bash olmayan sistemlerde de çalışsın. `set -e` ile ilk hatada durur;
# yarım kurulumla "neden çalışmıyor" aramak en kötü senaryo.
set -eu

MIN_MINOR=11
VENV=.venv
DEV=0
[ "${1:-}" = "--dev" ] && DEV=1

# Renkler yalnızca gerçek terminalde; boruya yönlendirilince kaçış kodu bırakmaz.
if [ -t 1 ]; then
    OK=$(printf '\033[32m'); WARN=$(printf '\033[33m')
    ERR=$(printf '\033[31m'); DIM=$(printf '\033[2m'); OFF=$(printf '\033[0m')
else
    OK=''; WARN=''; ERR=''; DIM=''; OFF=''
fi

adim() { printf '%s▸%s %s\n' "$DIM" "$OFF" "$1"; }
bitti() { printf '%s✓%s %s\n' "$OK" "$OFF" "$1"; }
uyari() { printf '%s!%s %s\n' "$WARN" "$OFF" "$1"; }
hata() { printf '%s✗%s %s\n' "$ERR" "$OFF" "$1" >&2; exit 1; }

cd "$(dirname "$0")"

# --- 1. Uygun Python ---------------------------------------------------------- #
# Sürüm sabit çağrılmaz: makinede hangi 3.11+ varsa o kullanılır.
uygun_mu() {
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= (3, $MIN_MINOR) else 1)" 2>/dev/null
}

PYTHON=''
for aday in python3.13 python3.12 python3.11 python3 python; do
    if uygun_mu "$aday"; then PYTHON=$aday; break; fi
done
[ -n "$PYTHON" ] || hata "Python 3.$MIN_MINOR veya üstü bulunamadı. Kur: https://www.python.org/downloads/"
bitti "Python: $($PYTHON -V 2>&1) ($(command -v "$PYTHON"))"

# --- 2. Sanal ortam ------------------------------------------------------------ #
if [ -x "$VENV/bin/python" ]; then
    bitti "Sanal ortam zaten var: $VENV"
else
    adim "Sanal ortam oluşturuluyor…"
    "$PYTHON" -m venv "$VENV" || hata "venv oluşturulamadı. Debian/Ubuntu'da: sudo apt install python3-venv"
    bitti "Sanal ortam hazır: $VENV"
fi
PIP="$VENV/bin/python -m pip"

# --- 3. Bağımlılıklar ----------------------------------------------------------- #
# chromadb büyük; ilk kurulum birkaç dakika sürebiliyor, kullanıcı boş ekrana bakmasın.
adim "Bağımlılıklar kuruluyor (ilk kurulum birkaç dakika sürebilir)…"
$PIP install --quiet --upgrade pip
if [ "$DEV" -eq 1 ]; then
    $PIP install --quiet -e ".[dev]" || hata "Kurulum başarısız."
    bitti "Paket ve geliştirme araçları kuruldu."
else
    $PIP install --quiet -e . || hata "Kurulum başarısız."
    bitti "Paket kuruldu."
fi

# --- 4. .env ------------------------------------------------------------------- #
# Var olan .env'in üzerine YAZILMAZ: içinde kullanıcının anahtarları var.
if [ -f .env ]; then
    bitti ".env zaten var, dokunulmadı."
else
    cp .env.example .env
    bitti ".env oluşturuldu (.env.example'dan kopyalandı)."
fi

# --- 5. Kullanıcı dizini şablonları --------------------------------------------- #
# Çıktı BASTIRILMAZ: kurulum anahtarları interaktif sorar, bastırılırsa soru
# görünmez ve betik sessizce kilitlenir.
"$VENV/bin/fusion" setup || uyari "Kullanıcı dizini şablonları bırakılamadı (kritik değil)."

# --- 6. Doğrulama --------------------------------------------------------------- #
"$VENV/bin/fusion" version >/dev/null 2>&1 || hata "Kurulum tamamlandı ama 'fusion' çalışmıyor."
bitti "Doğrulandı: $("$VENV/bin/fusion" version)"

# --- 7. Sırada ne var ----------------------------------------------------------- #
# Anahtar yoksa CLI açılır ama tur atamaz; bunu şimdi söylemek sonra aramaktan iyi.
if grep -Eq '^(NVIDIA_NIM_API_KEY|OPENROUTER_API_KEY)=.+' .env; then
    printf '\n%sHazır.%s Başlatmak için:\n\n    ./%s/bin/fusion\n\n' "$OK" "$OFF" "$VENV"
else
    cat <<TXT

$(uyari "Henüz API anahtarı yok. .env dosyasına en az birini gir:")

    NVIDIA NIM (ücretsiz)   https://build.nvidia.com/
    OpenRouter (ücretsiz)   https://openrouter.ai/keys

Sonra başlat:

    ./$VENV/bin/fusion

TXT
fi
printf '%sHer dizinden "fusion" yazabilmek için: source %s/bin/activate%s\n' "$DIM" "$VENV" "$OFF"
