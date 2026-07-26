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

import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.keys import NIM_ENV, OPENROUTER_ENV, ProviderKeys, detect
from ..config.loader import load_config, load_environment
from ..config.models import Config
from ..config.paths import env_file_candidates, memory_dir, user_config_dir
from ..config.readiness import Readiness, ReadinessReport, evaluate
from ..core.errors import ConfigError

#: Anahtarın kendisi yerine yazılan değer. Tanı çıktısı paylaşılır.
KEY_PRESENT = "ayarlı"
KEY_MISSING = "yok"


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
    checks.extend(_optional())
    if live:
        checks.extend(_live(config))
    return DoctorReport(tuple(checks), hazir)


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
    return [
        Check(
            OPENROUTER_ENV,
            KEY_PRESENT if keys.openrouter else KEY_MISSING,
            ok=keys.openrouter,
            remedy=""
            if keys.openrouter
            else "https://openrouter.ai/keys adresinden ücretsiz al, `fusion setup` ile gir.",
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


def _optional() -> list[Check]:
    """Opsiyonel ekstralar. Yokluğu HATA değildir; kapının sessizce geçtiğini söyler."""
    try:
        import playwright  # noqa: F401

        kurulu = True
    except ImportError:
        kurulu = False
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
    """Sağlayıcılara KÜÇÜK gerçek çağrı. Yalnızca `--live` ile çalışır ve kota harcar."""
    import asyncio

    from ..core.types import CompletionRequest, Message
    from ..providers.litellm_provider import LiteLlmProvider, configure_litellm

    configure_litellm()
    istek = CompletionRequest(
        messages=(Message("user", "ping"),), temperature=0.0, max_tokens=8, timeout_s=30
    )

    async def _dene(model: str) -> Check:
        sonuc = await LiteLlmProvider(model, role="doctor").complete(istek)
        return Check(
            f"canlı: {model}",
            "yanıt verdi" if sonuc.ok else _short(sonuc.error),
            ok=sonuc.ok,
            remedy="" if sonuc.ok else "Model yanıt vermiyor; `/level` ile başka kademe dene.",
        )

    modeller = tuple(dict.fromkeys([config.agent.models[0], config.judge.models[0]]))

    async def _hepsi() -> list[Check]:
        return list(await asyncio.gather(*[_dene(model) for model in modeller]))

    return asyncio.run(_hepsi())


def _short(error: str | None) -> str:
    """Hata metnini kısalt. Uzun sağlayıcı çıktısı tanıyı okunmaz yapar."""
    if not error:
        return "bilinmeyen hata"
    return error if len(error) <= 120 else error[:120] + "…"


def _writable(path: Path) -> bool:
    """Dizin oluşturulabilir/yazılabilir mi? Var olmayan dizin sorun değildir."""
    hedef = path if path.exists() else path.parent
    try:
        hedef.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    deneme = hedef / ".fusion-yazma-denemesi"
    try:
        deneme.touch()
        deneme.unlink()
    except OSError:
        return False
    return True
