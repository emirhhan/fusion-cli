#!/bin/sh
# Fusion-CLI tek adımlık kurulum.
#
#   ./setup.sh          → KULLANICI kurulumu: izole, global `fusion` komutu
#   ./setup.sh --dev    → GELİŞTİRİCİ kurulumu: repo içinde .venv + editable
#
# İkisi bilinçli olarak farklıdır. Kullanıcı repo klasörüne girmek, .venv yolu
# yazmak ya da her terminalde `activate` çalıştırmak zorunda kalmamalı; geliştirici
# ise kodda yaptığı değişikliği anında görebilmeli (editable).
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

# --- 2a. KULLANICI kurulumu: izole ve global --------------------------------- #
# Tercih sırası uv → pipx → pip --user. İlk ikisi aracı KENDİ izole ortamına kurar
# ve bin dizinini PATH'e ekler; kullanıcının sistem Python'ı kirlenmez.
#
# Editable DEĞİLDİR: kullanıcı repo klasörünü silse ya da taşısa bile `fusion`
# çalışmaya devam etmeli.
if [ "$DEV" -eq 0 ]; then
    if command -v uv >/dev/null 2>&1; then
        adim "uv ile kuruluyor (izole, global)…"
        uv tool install --force . || hata "uv ile kurulum başarısız."
        YONTEM=uv
    elif command -v pipx >/dev/null 2>&1; then
        adim "pipx ile kuruluyor (izole, global)…"
        pipx install --force . || hata "pipx ile kurulum başarısız."
        YONTEM=pipx
    else
        # `pip install --user` GÜVENİLİR DEĞİL: PEP 668 ile yönetilen Python
        # kurulumlarında (Homebrew, uv, dağıtım paketleri) "externally-managed-
        # environment" hatası verir — ölçüldü. `--break-system-packages` ise tam
        # da bu korumayı deldiği için kullanılmaz.
        #
        # Bunun yerine pipx'in yaptığı elle yapılır: kullanıcı veri dizininde
        # ADANMIŞ bir sanal ortam kurulur ve ikili ~/.local/bin'e bağlanır.
        # İzole, kullanıcı-local, sistem Python'ını kirletmez.
        adim "İzole sanal ortam kuruluyor (uv/pipx bulunamadı)…"
        uyari "Daha temiz kurulum için önerilen: uv (https://docs.astral.sh/uv/) ya da pipx."
        VERI_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fusion-cli"
        ARAC_VENV="$VERI_DIR/venv"
        BIN_DIR="$HOME/.local/bin"
        "$PYTHON" -m venv "$ARAC_VENV" || hata "Sanal ortam oluşturulamadı."
        "$ARAC_VENV/bin/python" -m pip install --quiet --upgrade pip
        if ! "$ARAC_VENV/bin/python" -m pip install --quiet .; then
            uyari "Sessiz kurulum başarısız; gerçek hata aşağıda:"
            "$ARAC_VENV/bin/python" -m pip install . || hata "Kurulum başarısız."
        fi
        mkdir -p "$BIN_DIR"
        ln -sf "$ARAC_VENV/bin/fusion" "$BIN_DIR/fusion"
        YONTEM="izole venv ($ARAC_VENV)"
    fi
    bitti "Kuruldu ($YONTEM)."

    # `fusion` PATH'te mi? Değilse doğrudan çalıştırıp doctor'un PATH ipucunu göster.
    if command -v fusion >/dev/null 2>&1; then
        FUSION=fusion
    else
        FUSION="$HOME/.local/bin/fusion"
        [ -x "$FUSION" ] || FUSION="${XDG_DATA_HOME:-$HOME/.local/share}/fusion-cli/venv/bin/fusion"
        [ -x "$FUSION" ] || hata "Kurulum tamamlandı ama 'fusion' ikilisi bulunamadı."
    fi

    printf '\n'
    "$FUSION" setup || uyari "Kurulum sihirbazı tamamlanamadı."
    printf '\n'
    if "$FUSION" doctor; then
        printf '\n%sHazır.%s Başlatmak için:\n\n    fusion\n\n' "$OK" "$OFF"
    else
        printf '\n%s Kurulum tamamlandı ama yapılandırma eksik.%s\n' "$WARN" "$OFF"
        printf 'Yukarıdaki satırlar ne yapılacağını söylüyor.\n\n'
    fi
    exit 0
fi

# --- 2b. GELİŞTİRİCİ kurulumu: repo içinde .venv ------------------------------ #
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
# `--quiet` yalnızca BAŞARIDA sessizdir: hata olursa pip'in gerçek çıktısı
# gösterilir, yoksa kullanıcı "Kurulum başarısız" cümlesiyle baş başa kalır.
adim "Bağımlılıklar kuruluyor (chromadb büyük; ilk kurulum birkaç dakika sürebilir)…"
$PIP install --quiet --upgrade pip
if ! $PIP install --quiet -e ".[dev,mcp,web]"; then
    uyari "Sessiz kurulum başarısız; gerçek hata aşağıda:"
    $PIP install -e ".[dev,mcp,web]" || hata "Kurulum başarısız."
fi
bitti "Paket, MCP, web ve geliştirme araçları kuruldu (editable)."

adim "Playwright Chromium kuruluyor…"
"$VENV/bin/python" -m playwright install chromium || hata "Playwright Chromium kurulamadı."
bitti "Playwright Chromium hazır."

# --- 4. .env (yalnızca geliştirici kurulumu) ------------------------------------ #
# Normal kullanıcının anahtarları KULLANICI DİZİNİNDE tutulur (`fusion setup`).
# Repo köküne de .env bırakmak iki doğruluk kaynağı yaratıyordu: kullanıcı hangisini
# düzenleyeceğini bilemiyor, üstelik repo kopyası 0644 (herkes okuyabilir) oluyordu.
if [ -f .env ]; then
    bitti ".env zaten var, dokunulmadı."
else
    cp .env.example .env
    chmod 600 .env 2>/dev/null || true
    bitti ".env oluşturuldu (proje bazlı override; anahtarlar buraya da yazılabilir)."
fi

# --- 5. Kullanıcı dizini şablonları --------------------------------------------- #
# Çıktı BASTIRILMAZ: kurulum anahtarları interaktif sorar, bastırılırsa soru
# görünmez ve betik sessizce kilitlenir.
"$VENV/bin/fusion" setup || uyari "Kullanıcı dizini şablonları bırakılamadı (kritik değil)."

# --- 6. Doğrulama --------------------------------------------------------------- #
"$VENV/bin/fusion" version >/dev/null 2>&1 || hata "Kurulum tamamlandı ama 'fusion' çalışmıyor."
bitti "Doğrulandı: $("$VENV/bin/fusion" version)"

# --- 7. Sırada ne var ----------------------------------------------------------- #
# Anahtar kontrolü BURADA TEKRAR YAZILMAZ. Eskiden repo kökündeki .env `grep`
# ediliyordu; kullanıcı anahtarını sihirbazda girse bile "anahtar yok" deniyordu
# çünkü anahtar KULLANICI dizinine yazılıyordu. Tek doğruluk kaynağı `fusion doctor`.
printf '\n'
if "$VENV/bin/fusion" doctor; then
    printf '\n%sHazır.%s Başlatmak için:\n\n    ./%s/bin/fusion\n\n' "$OK" "$OFF" "$VENV"
else
    printf '\n%s Kurulum tamamlandı ama yapılandırma eksik.%s\n' "$WARN" "$OFF"
    printf 'Yukarıdaki satırlar ne yapılacağını söylüyor.\n\n'
fi
printf '%sHer dizinden "fusion" yazabilmek için: source %s/bin/activate%s\n' "$DIM" "$VENV" "$OFF"
