"""`fusion setup` — ilk kurulum.

Global kurulumdan (pipx/pip) sonra bir kez çalıştırılır: kullanıcı yapılandırma
dizinine `config.yaml` ve `.env` şablonu bırakır, sonra anahtar alınacak adresleri
gösterir.

Var olan dosyaların ÜZERİNE YAZMAZ. Kurulum sihirbazının kullanıcının anahtarlarını
silmesi kabul edilemez; mevcut dosya varsa yalnızca bildirilir.
"""

from __future__ import annotations

import getpass
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from rich.console import Console

from ..config.keys import detect
from ..config.loader import load_environment
from ..config.paths import bundled_defaults, memory_dir, user_config_dir
from ..tools.files import atomic_write
from ..ui import messages, theme

ENV_TEMPLATE = """# Fusion-CLI API anahtarları — en az birini doldur.

# NVIDIA NIM (ücretsiz geliştirici anahtarı): https://build.nvidia.com/
NVIDIA_NIM_API_KEY=
# Boş bırakılırsa NVIDIA'nın barındırdığı uç kullanılır.
NVIDIA_NIM_API_BASE=

# OpenRouter (ücretsiz katman): https://openrouter.ai/keys
OPENROUTER_API_KEY=

# Langfuse izleme (opsiyonel — boş bırakılırsa sessizce kapalı)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=
"""

#: Kullanıcı config'inde başlangıç olarak bırakılan açıklamalı şablon.
CONFIG_TEMPLATE = """# Fusion-CLI kullanıcı yapılandırması.
#
# Buraya YALNIZCA değiştirmek istediğin anahtarları yaz: bu dosya pakete gömülü
# varsayılanların ÜZERİNE derin birleştirilir, onların yerini almaz.
#
# Tüm varsayılanları görmek için:  fusion config show
# Kullanılabilir modelleri görmek için:  fusion models --fetch

# Örnek — daha uzun cevaplar:
# runtime:
#   max_tokens: 4096

# Örnek — agent modelini değiştir:
# agent:
#   name: kendi-modelim
#   model: openrouter/bir/model:free

# Örnek — havuza aday EKLE (mevcutları değiştirmeden):
# extra_candidates:
#   - name: yerel-qwen
#     model: ollama/qwen2.5-coder:7b
#     tags: [code]
"""


#: Anahtar sorma imzası. Enjekte edilir: gerçek terminal olmadan test edilebilsin.
Asker = Callable[[str], str]


def run_setup(console: Console, *, ask: Asker | None = None) -> None:
    """Yapılandırmayı kur: anahtarları al, dosyaları yaz, hazır dersleri yükle.

    `ask` verilmezse ve girdi bir terminal değilse anahtar SORULMAZ; yalnızca
    şablon bırakılır. Boru hattında ya da CI'da soru sormak kurulumu kilitlerdi.
    """
    directory = user_config_dir()
    directory.mkdir(parents=True, exist_ok=True)

    _create(console, directory / "config.yaml", CONFIG_TEMPLATE)
    sorucu = ask or (_gizli_soru if sys.stdin.isatty() else None)
    anahtar_alindi = False
    # Anahtar başka bir `.env`'de ya da kabukta zaten tanımlıysa sorulmaz: kurulumu
    # tekrar çalıştıran kullanıcıya aynı soruyu sormak onu şaşırtır.
    load_environment()
    zaten_var = detect().any_configured
    if sorucu is not None and not zaten_var and not (directory / ".env").exists():
        _ask_keys(console, directory / ".env", sorucu)
        anahtar_alindi = True
    else:
        _create(console, directory / ".env", ENV_TEMPLATE)

    _seed_lessons(console)
    _offer_path_setup(console, interaktif=ask is None and sys.stdin.isatty() and not anahtar_alindi)

    console.print()
    console.print(f"[bold]{messages.SETUP_NEXT_STEPS}[/bold]")
    if anahtar_alindi:
        # Anahtarlar az önce alındı; "anahtarlarını gir" demek kullanıcıyı
        # yaptığı işi tekrar yapmaya yollardı.
        console.print(f"  1. {messages.SETUP_STEP_RUN}")
    else:
        console.print(f"  1. {messages.SETUP_STEP_KEYS.format(path=directory / '.env')}")
        console.print(f"     [{theme.DIM}]OpenRouter  https://openrouter.ai/keys[/{theme.DIM}]")
        console.print(f"     [{theme.DIM}]NVIDIA NIM  https://build.nvidia.com/[/{theme.DIM}]")
        console.print(f"  2. {messages.SETUP_STEP_RUN}")
    console.print()
    console.print(f"[{theme.DIM}]{messages.SETUP_PATHS}[/{theme.DIM}]")
    console.print(f"[{theme.DIM}]  yapılandırma: {directory}[/{theme.DIM}]")
    console.print(f"[{theme.DIM}]  bellek:       {memory_dir()}[/{theme.DIM}]")
    console.print(f"[{theme.DIM}]  varsayılanlar:{bundled_defaults()}[/{theme.DIM}]")


def _ask_keys(console: Console, path: Path, ask: Asker) -> None:
    """Anahtarları sor ve `.env` olarak yaz.

    EN AZ BİR anahtar gerekir; hangisi olduğu fark etmez. Ölçüldü: readiness
    değerlendirmesi hem yalnız OpenRouter hem yalnız NIM ile READY diyor — ikisi
    de tüm zorunlu rolleri karşılıyor. Sihirbaz eskiden OpenRouter'ı zorunlu
    tutuyordu; bu kullanıcıyı ihtiyacı olmayan bir anahtarı almaya zorluyor ve
    ürünün kendi hazır-olma kararıyla çelişiyordu.

    OpenRouter önce sorulur çünkü önerilen tabandır, ama boş geçilebilir.
    """
    console.print()
    console.print(f"[bold]{messages.SETUP_WELCOME}[/bold]")
    console.print()

    openrouter = nim = ""
    while not (openrouter or nim):
        try:
            openrouter = _sor(ask, messages.SETUP_ASK_OPENROUTER)
            nim = _sor(ask, messages.SETUP_ASK_NIM)
        except _CancelledError:
            # Ctrl+C kurulumu İPTAL eder. Eskiden boş cevap sayılıp tekrar
            # soruluyordu; kullanıcı kurulumdan çıkamıyordu.
            console.print(f"[{theme.DIM}]{messages.SETUP_CANCELLED}[/{theme.DIM}]")
            return
        if not (openrouter or nim):
            console.print(f"[{theme.WARN}]{messages.SETUP_KEY_REQUIRED}[/{theme.WARN}]")

    icerik = ENV_TEMPLATE.replace("NVIDIA_NIM_API_KEY=", f"NVIDIA_NIM_API_KEY={nim}").replace(
        "OPENROUTER_API_KEY=", f"OPENROUTER_API_KEY={openrouter}"
    )
    try:
        atomic_write(path, icerik)
    except OSError as hata:
        # Anahtarın kendisi hata mesajına GİRMEZ; yalnızca yol ve sebep yazılır.
        console.print(
            f"[{theme.ERROR}]{messages.SETUP_WRITE_FAILED.format(path=path)}[/{theme.ERROR}]"
        )
        console.print(f"[{theme.DIM}]{hata}[/{theme.DIM}]")
        return
    # İzinler daraltılır: anahtar dosyasını başka kullanıcılar okuyabilmemeli.
    with suppress(OSError):
        path.chmod(0o600)
    console.print(
        f"[{theme.OK}]{theme.ICON_OK}[/{theme.OK}] {messages.SETUP_KEYS_SAVED.format(path=path)}"
    )


class _CancelledError(Exception):
    """Kullanıcı Ctrl+C ya da EOF ile çıktı. Boş cevaptan AYRI tutulur:
    boş cevap 'tekrar sor' demektir, vazgeçme 'kurulumu bitir' demektir."""


def _sor(ask: Asker, prompt: str) -> str:
    """Tek bir anahtarı al. Vazgeçilirse `_CancelledError` fırlatır."""
    try:
        return ask(prompt).strip()
    except (EOFError, KeyboardInterrupt) as hata:
        raise _CancelledError from hata


def _gizli_soru(prompt: str) -> str:
    """Anahtarı EKRANA BASMADAN al.

    `input()` yazılanı gösterir: omuz üstünden okunur ve terminal geçmişinde
    kalır. Anahtar bir sırdır, parolayla aynı muameleyi görür.
    """
    return getpass.getpass(prompt)


def _offer_path_setup(console: Console, *, interaktif: bool) -> None:
    """`fusion` PATH'te değilse ekleme TEKLİF ET; onay alınırsa ekle.

    Onaysız yazılmaz ve etkileşimsiz ortamda (CI, boru hattı) hiç sorulmaz:
    cevaplanamayacak bir soru kurulumu kilitler. O durumda kullanıcı komutu
    `fusion doctor` çıktısından alır.
    """
    import shutil

    from ..install import ensure_on_path

    if shutil.which("fusion") or not interaktif:
        return

    bin_dir = Path.home() / ".local" / "bin"
    config_file = _shell_config()
    console.print()
    console.print(f"[{theme.WARN}]{messages.PATH_MISSING.format(bin_dir=bin_dir)}[/{theme.WARN}]")
    console.print(messages.PATH_ASK.format(file=config_file))
    try:
        # Evet/hayır sorusu SIR DEĞİLDİR: `getpass` ile sorulursa kullanıcı
        # yazdığını göremez ve cevabının alınıp alınmadığını bilemez.
        cevap = input(messages.PATH_PROMPT).strip().lower()
    except (EOFError, KeyboardInterrupt):
        cevap = ""
    onaylandi = cevap in {"", "e", "evet", "y", "yes"}

    sonuc = ensure_on_path(bin_dir=bin_dir, config_file=config_file, approved=onaylandi)
    if sonuc.error:
        basarisiz = messages.PATH_FAILED.format(error=sonuc.error)
        console.print(f"[{theme.ERROR}]{basarisiz}[/{theme.ERROR}]")
        console.print(f"[{theme.DIM}]{sonuc.line}[/{theme.DIM}]")
    elif sonuc.changed:
        # Yapılan değişiklik AÇIKÇA bildirilir; kullanıcı neyi geri alacağını bilmeli.
        eklendi = messages.PATH_ADDED.format(file=config_file)
        console.print(f"[{theme.OK}]{theme.ICON_OK}[/{theme.OK}] {eklendi}")
        console.print(f"[{theme.DIM}]  {sonuc.line}[/{theme.DIM}]")
        console.print(f"[{theme.DIM}]{messages.PATH_RELOAD.format(file=config_file)}[/{theme.DIM}]")
    else:
        console.print(f"[{theme.DIM}]{messages.PATH_SKIPPED}[/{theme.DIM}]")
        console.print(f"[{theme.DIM}]  {sonuc.line}[/{theme.DIM}]")


def _shell_config() -> Path:
    """Kullanıcının kabuğuna karşılık gelen yapılandırma dosyası."""
    import os

    kabuk = Path(os.environ.get("SHELL", "sh")).name
    return {
        "zsh": Path.home() / ".zshrc",
        "bash": Path.home() / ".bashrc",
        "fish": Path.home() / ".config" / "fish" / "config.fish",
    }.get(kabuk, Path.home() / ".profile")


def _seed_lessons(console: Console) -> None:
    """Küratörlü dersleri belleğe yükle: indiren herkes eğitilmiş başlar.

    Bellek açılamazsa kurulum DÜŞMEZ — dersler bir iyileştirmedir, ürünün
    çalışması onlara bağlı değildir.
    """
    try:
        from ..config.loader import load_config
        from ..memory.factory import build_memory
        from ..memory.seed import seed

        memory = build_memory(load_config(), root=Path.cwd())
        if memory.unavailable_reason is not None:
            raise RuntimeError(memory.unavailable_reason)
        count = seed(memory.lessons)
    except Exception as exc:
        console.print(
            f"[{theme.DIM}]{messages.SETUP_LESSONS_SKIPPED.format(reason=exc)}[/{theme.DIM}]"
        )
        return
    console.print(
        f"[{theme.OK}]{theme.ICON_OK}[/{theme.OK}] "
        f"{messages.SETUP_LESSONS_SEEDED.format(count=count)}"
    )


def _create(console: Console, path: Path, content: str) -> None:
    if path.exists():
        console.print(f"[{theme.DIM}]{messages.SETUP_EXISTS.format(path=path)}[/{theme.DIM}]")
        return
    path.write_text(content, encoding="utf-8")
    console.print(
        f"[{theme.OK}]{theme.ICON_OK}[/{theme.OK}] {messages.SETUP_CREATED.format(path=path)}"
    )
