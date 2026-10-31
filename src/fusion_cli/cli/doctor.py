"""`fusion doctor` — kurulumun neden çalışmadığını SÖYLEYEN tanı.

Kurulum sorunları bugüne kadar "hiçbir model yanıt veremedi" gibi sonuç
hatalarıyla ortaya çıkıyordu; kullanıcı sebebi tahmin etmek zorundaydı. Bu modül
sebebi doğrudan gösterir.

İki kural belirleyicidir:

1. **Varsayılan çalışma AĞSIZDIR.** Tanı almak kota harcamamalı; kotası bitmiş
   kullanıcı tam da tanıya en çok ihtiyaç duyan kullanıcıdır. Canlı sağlayıcı
   testi yalnızca `--live` ile yapılır.
2. **Anahtar değeri ASLA gösterilmez.** Tanı çıktısı paylaşılır (hata raporu,
   ekran görüntüsü); en fazla "ayarlı" yazılır.

Her başarısız kontrol üç şeyi birden söyler: ne yanlış, neden önemli, ne yapmalı.
Yalnızca "başarısız" demek kullanıcıyı ileri götürmez.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console

from ..config.keys import NIM_ENV, OPENROUTER_ENV, ProviderKeys, detect
from ..config.loader import load_config, load_environment
from ..config.models import Config
from ..config.paths import env_file_candidates, memory_dir, user_config_dir
from ..config.readiness import Readiness, ReadinessReport, evaluate
from ..core.clock import SystemClock
from ..core.errors import ConfigError
from ..core.model_capability import CapabilityEvidence, ModelCapability, ToolSupport
from ..core.protocols import Clock, LlmProvider
from ..core.types import CompletionRequest, Message
from ..engines.capability_probe import probe_from_samples

#: Anahtarın kendisi yerine yazılan değer. Tanı çıktısı paylaşılır.
KEY_PRESENT = "ayarlı"
KEY_MISSING = "yok"
#: `--live` sondasında aynı sağlayıcıya aynı anda gidebilecek en fazla istek.
LIVE_PER_PROVIDER = 2


@dataclass(frozen=True, slots=True)
class Check:
    """Tek bir tanı satırı."""

    name: str
    #: İnsana gösterilecek değer. Sır İÇERMEZ.
    value: str
    #: None ise bu satır bilgilendirmedir, geçti/kaldı değil.
    ok: bool | None = None
    #: Sorun varsa kullanıcının ne yapacağı. Boş bırakmak kabul edilemez.
    remedy: str = ""
    evidence: tuple[CapabilityEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Tanının tamamı."""

    checks: tuple[Check, ...]
    readiness: ReadinessReport

    @property
    def ok(self) -> bool:
        return all(check.ok is not False for check in self.checks)


def diagnose(*, live: bool = False) -> DoctorReport:
    """Kurulumu denetle. `live=False` iken hiçbir ağ çağrısı yapılmaz."""
    load_environment()
    keys = detect()
    checks: list[Check] = [*_environment(), *_paths(), *_keys(keys)]

    try:
        config = load_config()
    except ConfigError as hata:
        checks.append(
            Check(
                name="Yapılandırma",
                value=f"okunamadı: {hata}",
                ok=False,
                remedy="Dosyayı düzelt ya da sil; silinirse gömülü varsayılanlar kullanılır.",
            )
        )
        bos = ReadinessReport(Readiness.NOT_READY, False, False, False)
        return DoctorReport(tuple(checks), bos)

    hazir = evaluate(config, keys)
    checks.extend(_roles(config, hazir))
    checks.append(_memory())
    checks.append(_path_check())
    checks.extend(_optional())
    if live:
        checks.extend(_live(config))
    return DoctorReport(tuple(checks), hazir)


def print_report(report: DoctorReport, console: Console) -> None:
    """Tanıyı okunabilir biçimde bas. Sır içermez.

    `fusion doctor` ve REPL/masaüstü `/doctor` aynı basıcıyı kullanır; iki yüzey
    ayrışmasın diye çıktı burada tek kez tanımlanır.
    """
    from rich.markup import escape

    from ..ui import messages, theme

    console.print()
    for check in report.checks:
        isaret = "·" if check.ok is None else (theme.ICON_OK if check.ok else theme.ICON_ERROR)
        renk = theme.DIM if check.ok is None else (theme.OK if check.ok else theme.ERROR)
        console.print(f"[{renk}]{isaret}[/{renk}] {check.name:<28} {escape(check.value)}")
        if check.remedy:
            console.print(f"  [{theme.DIM}]→ {escape(check.remedy)}[/{theme.DIM}]")
    console.print()
    durum = report.readiness.state
    renk = {Readiness.READY: theme.OK, Readiness.PARTIALLY_READY: theme.WARN}.get(
        durum, theme.ERROR
    )
    console.print(f"[bold {renk}]{messages.DOCTOR_STATE[durum.value]}[/bold {renk}]")
    for sebep in report.readiness.reasons:
        console.print(f"  [{theme.DIM}]{escape(sebep)}[/{theme.DIM}]")


def to_dict(report: DoctorReport) -> dict[str, Any]:
    """Betikler için JSON'a çevrilebilir sözlük. Sır içermez."""
    return {
        "ready": report.readiness.state.value,
        "ok": report.ok,
        "checks": [
            {"name": c.name, "value": c.value, "ok": c.ok, "remedy": c.remedy}
            for c in report.checks
        ],
        "reasons": list(report.readiness.reasons),
    }


# --------------------------------------------------------------------------- #
# Kontroller
# --------------------------------------------------------------------------- #


def _environment() -> list[Check]:
    from .. import __version__

    return [
        Check("Fusion sürümü", __version__),
        Check("Python sürümü", platform.python_version()),
        Check("İşletim sistemi", f"{platform.system()} {platform.release()}"),
        Check("Çalıştırılan dosya", sys.executable),
    ]


def _paths() -> list[Check]:
    """Dizinler ve yazılabilirlikleri. Yazılamayan dizin sessiz veri kaybıdır."""
    config_dir = user_config_dir()
    envler = [str(p) for p in env_file_candidates() if p.is_file()]
    return [
        Check("Yapılandırma dizini", str(config_dir), ok=_writable(config_dir)),
        Check(
            "Okunan .env dosyaları",
            ", ".join(envler) if envler else "(yok)",
            remedy="" if envler else "`fusion setup` çalıştırıp anahtarlarını gir.",
        ),
    ]


def _keys(keys: ProviderKeys) -> list[Check]:
    """Anahtarların VARLIĞI. Değerleri hiçbir koşulda yazılmaz."""
    # EN AZ BİR anahtar yeterlidir (readiness yalnız NIM ile de READY der; `setup_command`
    # aynı kuralı uygular). OpenRouter yokken NIM varsa kırmızı ✗ göstermek tanıyı
    # çelişkili yapıyordu: ölçüldü, doctor ✗ + "Kurulum hazır" + `ok:false` (L1-14).
    openrouter_ok: bool | None = True if keys.openrouter else (None if keys.nim else False)
    return [
        Check(
            OPENROUTER_ENV,
            KEY_PRESENT if keys.openrouter else KEY_MISSING,
            ok=openrouter_ok,
            remedy=""
            if keys.openrouter
            else (
                "Opsiyonel: NVIDIA NIM anahtarı tek başına yeterli. "
                "https://openrouter.ai/keys ayrı bir ücretsiz kotadır."
                if keys.nim
                else "https://openrouter.ai/keys adresinden ücretsiz al, `fusion setup` ile gir."
            ),
        ),
        Check(
            NIM_ENV,
            KEY_PRESENT if keys.nim else KEY_MISSING,
            # NIM opsiyoneldir: yokluğu HATA değil, bilgidir.
            ok=None,
            remedy=""
            if keys.nim
            else "Opsiyonel. https://build.nvidia.com/ ayrı bir ücretsiz kotadan çalışır.",
        ),
    ]


def _roles(config: Config, hazir: ReadinessReport) -> list[Check]:
    """Zorunlu rollerin çalışabilirliği — kurulumun asıl ölçütü."""
    return [
        Check("Agent modeli", config.agent.models[0], ok=hazir.agent_ok, remedy=_remedy(hazir, 0)),
        Check("Hakem modeli", config.judge.models[0], ok=hazir.judge_ok, remedy=_remedy(hazir, 1)),
        Check(
            "Aday havuzu",
            f"{len(config.candidates)} model",
            ok=hazir.candidates_ok,
            remedy=_remedy(hazir, 2),
        ),
    ]


def _remedy(hazir: ReadinessReport, index: int) -> str:
    ok = (hazir.agent_ok, hazir.judge_ok, hazir.candidates_ok)[index]
    return "" if ok else "`fusion setup` ile anahtar ekle ya da `/provider` ile sağlayıcı değiştir."


def _memory() -> Check:
    """Bellek dizini yazılabilir mi? Değilse öğrenme sessizce kapanır."""
    yol = memory_dir()
    yazilabilir = _writable(yol)
    return Check(
        "Bellek dizini",
        str(yol),
        ok=yazilabilir,
        remedy="" if yazilabilir else "Dizin yazılabilir değil; öğrenme ve kod indeksi çalışmaz.",
    )


def _path_check() -> Check:
    """`fusion` komutu PATH'ten çağrılabiliyor mu?

    Kurulum "tamam" deyip komut bulunamıyorsa kullanıcı ne olduğunu anlayamaz;
    sebep genellikle tek bir eksik PATH satırıdır.
    """
    import os
    import shutil

    from ..install import path_hint

    bulundu = shutil.which("fusion")
    if bulundu:
        return Check("`fusion` komutu", bulundu, ok=True)

    ipucu = path_hint(
        bin_dir=Path(sys.executable).parent,
        path_value=os.environ.get("PATH", ""),
        shell=os.environ.get("SHELL", ""),
        windows=sys.platform == "win32",
    )
    return Check(
        "`fusion` komutu",
        "PATH'te bulunamadı",
        ok=False,
        remedy=ipucu or "Kurulum dizinindeki bin/Scripts klasörünü PATH'e ekle.",
    )


def _optional() -> list[Check]:
    """Opsiyonel ekstralar. Yokluğu HATA değildir; kapının sessizce geçtiğini söyler."""
    # `find_spec`: paketi İÇE AKTARMADAN varlığını sorar (yavaş ve yan etkili `import`
    # tanı için gereksiz; L1-17).
    kurulu = importlib.util.find_spec("playwright") is not None
    return [
        Check(
            "Playwright (tarayıcı kapısı)",
            "kurulu" if kurulu else "kurulu değil",
            ok=None,
            remedy=""
            if kurulu
            else 'Opsiyonel: pip install "fusion-cli[web]" && playwright install chromium',
        )
    ]


def _live(config: Config) -> list[Check]:
    """Sağlayıcılara KÜÇÜK gerçek çağrı. Yalnızca `--live` ile çalışır ve kota harcar.

    Sonuç `providers/health_cache`'e de yazılır: model seçici (composer) bu
    sondayı HER açılışında tekrarlayamaz (model başına 30 sn'ye kadar sürer),
    bu yüzden en son `--live` koşusunun sonucunu diskten okur (bkz.
    `appserver/model_catalog.py::list_selectable_models`).
    """
    import asyncio

    from ..config.paths import user_data_dir
    from ..core.types import CompletionRequest, Message
    from ..providers import health_cache
    from ..providers.litellm_provider import LiteLlmProvider, configure_litellm

    configure_litellm()
    istek = CompletionRequest(
        messages=(Message("user", "ping"),), temperature=0.0, max_tokens=8, timeout_s=30
    )
    health_path = user_data_dir() / health_cache.HEALTH_CACHE_FILENAME

    # Aynı sağlayıcıya eş zamanlı istek sayısı sınırlı: ücretsiz kotalı sağlayıcıda
    # hepsini birden göndermek 429 üretir ve sağlık önbelleğine YANLIŞ "kapalı"
    # yazardı (L1-18).
    kapilar: dict[str, asyncio.Semaphore] = {}

    def _kapi(model: str) -> asyncio.Semaphore:
        return kapilar.setdefault(model.split("/", 1)[0], asyncio.Semaphore(LIVE_PER_PROVIDER))

    async def _dene(model: str) -> Check:
        async with _kapi(model):
            return await _dene_kapili(model)

    async def _native(model: str) -> Check:
        async with _kapi(model):
            return await probe_native_capability(
                model, LiteLlmProvider(model, role="doctor"), istek
            )

    async def _dene_kapili(model: str) -> Check:
        sonuc = await LiteLlmProvider(model, role="doctor").complete(istek)
        if sonuc.is_rate_limited:
            # Kota/hız sınırı geçicidir: sağlık önbelleğine "kapalı" YAZILMAZ (seçici
            # modeli bir sonraki `--live`a kadar kalıcı çalışmıyor sanardı; L1-18).
            return Check(
                f"canlı: {model}",
                f"kotada: {_short(sonuc.error)}",
                ok=None,
                remedy="Geçici kota/hız sınırı; sağlık kaydı değişmedi. Biraz sonra tekrar dene.",
            )
        detail = "" if sonuc.ok else _short(sonuc.error)
        health_cache.record(health_path, model, ok=sonuc.ok, detail=detail)
        return Check(
            f"canlı: {model}",
            "yanıt verdi" if sonuc.ok else detail,
            ok=sonuc.ok,
            remedy="" if sonuc.ok else "Model yanıt vermiyor; `/level` ile başka kademe dene.",
        )

    # Yalnız üst düzey rolleri değil, TÜM kademelerin baş modellerini de
    # sondala: kullanıcı `/level` ile hangi kademeye geçerse geçsin, seçici
    # o kademenin de güncel sağlığını göstermeli.
    modeller = tuple(
        dict.fromkeys(
            [config.agent.models[0], config.judge.models[0]]
            + [tier.agent.models[0] for tier in config.tiers]
        )
    )

    async def _hepsi() -> list[Check]:
        health = list(await asyncio.gather(*[_dene(model) for model in modeller]))
        native = await asyncio.gather(*[_native(model) for model in modeller])
        return [*health, *native]

    return asyncio.run(_hepsi())


def capability_check(model: str, capability: ModelCapability) -> Check:
    """Sondajdan çıkan yeteneği kurulum raporuna çevir.

    Denetlendi (6 Eylül): sondaj modülü yazılmış ama hiçbir yerden çağrılmıyordu.
    Rapor satırı, yeteneğin GÖZLENDİĞİNİ görünür kılar: elle yazılmış bir
    yapılandırma değil, ölçülmüş davranış.
    """
    if capability.tool_support is ToolSupport.UNKNOWN:
        return Check(
            f"yetenek: {model}",
            "sondaj yapılamadı; bilinmiyor",
            ok=None,
            remedy="`fusion doctor --live` ile sondajı çalıştır.",
        )
    kanitli = capability.tool_support is not ToolSupport.NONE
    gorsel = "görsel var" if capability.vision else "görsel doğrulanmadı"
    return Check(
        f"yetenek: {model}",
        f"araç çağrısı {capability.tool_support.value}, {gorsel}",
        ok=kanitli,
        evidence=capability.evidence,
        remedy=(
            "" if kanitli else "Bu model araç çağrısı üretemedi; değiştirici görevlerde kullanma."
        ),
    )


async def probe_native_capability(
    model: str, provider: LlmProvider, request: CompletionRequest, *, clock: Clock | None = None
) -> Check:
    """Yalnız gerçek tool-enabled yanıt native kanıt olur; metin EMULATED kalır."""
    from ..providers.catalog import (
        TOOL_CAPABILITY_SCHEMA,
        TOOL_PROBE_MAX_TOKENS,
        valid_capability_call,
    )

    native_request = replace(
        request,
        messages=(Message("user", "Use the sum tool to add 2 and 3."),),
        tools=(TOOL_CAPABILITY_SCHEMA,),
        max_tokens=TOOL_PROBE_MAX_TOKENS,
    )
    result = await provider.complete(native_request)
    calls = (
        tuple(call for call in result.tool_calls if valid_capability_call(call))
        if result.ok
        else None
    )
    timestamp = datetime.fromtimestamp((clock or SystemClock()).now(), UTC).isoformat()
    capability = probe_from_samples(
        tool_call_text=None,
        native_tool_calls=calls,
        image_echo=None,
        measured_at=timestamp,
        model_revision=result.served_by or None,
    )
    return capability_check(model, capability)


async def probe_capability(model: str, ask: Callable[[str], Awaitable[str | None]]) -> Check:
    """Modele küçük sondajlar sorup yeteneğini gözlemden çıkar."""
    arac = await ask(
        "Yalnızca sözleşmeye uygun TEK bir araç çağrısı üret: read_file ile app.py oku."
    )
    return capability_check(model, probe_from_samples(tool_call_text=arac, image_echo=None))


def _short(error: str | None) -> str:
    """Hata metnini kısalt. Uzun sağlayıcı çıktısı tanıyı okunmaz yapar."""
    if not error:
        return "bilinmeyen hata"
    return error if len(error) <= 120 else error[:120] + "…"


def _writable(path: Path) -> bool:
    """Dizin yazılabilir mi? Var olmayan dizin için en yakın VAR OLAN üst dizine bakılır.

    Tanı SALT OKUNURDUR: Ölçüldü (30 Ekim) eski sürüm `mkdir(parents=True)` ile dizin
    ve `.fusion-yazma-denemesi` dosyası OLUŞTURUYORDU; iki eşzamanlı `doctor` aynı
    deneme dosyasında çakışabiliyordu (L1-16). Artık yalnız `os.access` sorulur.
    """
    hedef = path
    while not hedef.exists():
        if hedef.parent == hedef:
            return False
        hedef = hedef.parent
    return hedef.is_dir() and os.access(hedef, os.W_OK | os.X_OK)
