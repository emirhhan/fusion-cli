"""Doğrulama kapısını çalıştıran ve sonucu decay'e bağlayan katman.

İki parça:

- `resolve_turn_success` — saf karar: turun "başarılı" sayılıp sayılmayacağını
  turun kendi durumu (model hata verdi mi, adım sınırına dayanıldı mı) ile
  doğrulama sonucundan (varsa) birleştirir. Bu sonuç ders güvenini besler.
- `CommandVerifier` — yapılandırılmış komutları (ruff/mypy/pytest ya da alt kümesi)
  sırayla çalıştıran concrete doğrulayıcı. İlk başarısız komut kapıyı düşürür.
- `WebVerifier` — agent'ın yazdığı HTML/CSS/JS'i mekanik olarak denetler.

Komut kapısı OPT-IN'dir (komut yazılmadıkça çalışmaz); web kapısı varsayılan AÇIKTIR.
İkisi de varsa `CompositeVerifier` bulgularını birleştirir.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ...config.models import Config
from ...core.constants import SHELL_TIMEOUT_S
from ...core.tools import ToolContext
from ...core.verification import VerificationResult, Verifier
from .browser_verify import BrowserVerifier
from .visual_verify import VisualVerifier
from .web_verify import inspect_web_output

#: Web kapısının denetlediği dosya uzantıları.
WEB_SUFFIXES = frozenset({".html", ".htm", ".css", ".js"})


def resolve_turn_success(
    *, outcome_ok: bool, hit_step_limit: bool, verification: VerificationResult | None
) -> bool:
    """Tur ders güvenini artıracak kadar başarılı mı.

    Temel sinyal: model temiz bitmiş ve adım sınırına dayanılmamış olmalı. Doğrulama
    kapısı devredeyse ayrıca geçmiş olmalı — böylece "test çalıştırmadan bitirme" gibi
    dersler gerçekten uygulanır: kapı kırıksa tur başarısız sayılır ve ders sönmez/güç
    kazanmaz, tersine ilgili ders cezalanır.
    """

    base = outcome_ok and not hit_step_limit
    if verification is None:
        return base
    return base and verification.ok


def build_verifier(
    config: Config, *, root: Path, tool_context: ToolContext | None = None
) -> Verifier | None:
    """Etkin doğrulayıcıları kur; hiçbiri yoksa None.

    İki kaynak birleşir:

    - **Komut kapısı** — yapılandırılmış `verification_commands` (ruff/mypy/pytest).
      Opt-in kalır: komut yazılmadıkça çalışmaz.
    - **Web kapısı** — üretilen HTML/CSS/JS'i METİN olarak denetler. Varsayılan
      AÇIKTIR. Opt-in bırakılsaydı kimse doldurmadığı için hiçbir şey değişmezdi;
      ölçtüğümüz hatalar (kırık görsel, boş bağlantı) her koşuda tekrarlıyordu.
    - **Tarayıcı kapısı** — sayfayı gerçekten açıp ÖLÇER (konsol hatası, yüklenemeyen
      kaynak, yatay taşma). Playwright opsiyonel ekstradır; kurulu değilse sessizce
      geçer, zorunlu bağımlılık eklenmez.

    None döndürmek doğrulamanın tamamen kapalı olması demektir.
    """
    verifiers: list[Verifier] = []
    if config.runtime.verification_commands:
        verifiers.append(
            CommandVerifier(
                config.runtime.verification_commands, cwd=str(root), timeout_s=SHELL_TIMEOUT_S
            )
        )
    if config.runtime.web_verification and tool_context is not None:
        verifiers.append(WebVerifier(tool_context))
    if config.runtime.browser_verification and tool_context is not None:
        # Playwright kurulu değilse bu kapı sessizce geçer; kendi içinde karar verir.
        verifiers.append(BrowserVerifier(tool_context))
    if config.runtime.visual_verification and tool_context is not None and config.vision:
        verifiers.append(VisualVerifier(tool_context, config))

    if not verifiers:
        return None
    return verifiers[0] if len(verifiers) == 1 else CompositeVerifier(tuple(verifiers))


class CompositeVerifier:
    """Birden çok doğrulayıcıyı sırayla çalıştırır ve bulgularını birleştirir."""

    def __init__(self, verifiers: tuple[Verifier, ...]) -> None:
        self._verifiers = verifiers

    async def verify(self) -> VerificationResult:
        ozetler: list[str] = []
        bulgular: list[str] = []
        for verifier in self._verifiers:
            result = await verifier.verify()
            if result.ok:
                continue
            if result.summary:
                ozetler.append(result.summary)
            bulgular.extend(result.findings)
        if not ozetler and not bulgular:
            return VerificationResult(ok=True)
        return VerificationResult(ok=False, summary="; ".join(ozetler), findings=tuple(bulgular))


class WebVerifier:
    """Agent'ın yazdığı web dosyalarını mekanik olarak denetler.

    Yalnızca `tool_context.touched` içindeki dosyalara bakar: kök dizini taramak,
    agent'ın hiç dokunmadığı dosyalar hakkında bulgu üretirdi.
    """

    def __init__(self, tool_context: ToolContext) -> None:
        self._context = tool_context

    async def verify(self) -> VerificationResult:
        files: dict[str, str] = {}
        for path in self._context.touched:
            if path.suffix.lower() not in WEB_SUFFIXES:
                continue
            try:
                files[path.name] = path.read_text(encoding="utf-8")
            except OSError:
                # Agent yazıp sonra silmiş ya da dosya okunamıyor: kapı bunun
                # yüzünden düşmemeli, denetleyecek bir şey yok demektir.
                continue

        findings = inspect_web_output(files) if files else ()
        if not findings:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False, summary=f"web çıktısında {len(findings)} sorun", findings=findings
        )


class CommandVerifier:
    """Yapılandırılmış kabuk komutlarını sırayla çalıştıran doğrulayıcı."""

    def __init__(self, commands: tuple[str, ...], *, cwd: str, timeout_s: float) -> None:
        self._commands = commands
        self._cwd = cwd
        self._timeout_s = timeout_s

    async def verify(self) -> VerificationResult:
        for command in self._commands:
            result = await self._run(command)
            if not result.ok:
                return result
        return VerificationResult(ok=True)

    async def _run(self, command: str) -> VerificationResult:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=self._cwd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            return VerificationResult(ok=False, summary=f"komut başlatılamadı: {command} ({exc})")

        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=self._timeout_s)
        except TimeoutError:
            process.kill()
            await process.wait()
            return VerificationResult(ok=False, summary=f"komut zaman aşımına uğradı: {command}")

        if return_code != 0:
            return VerificationResult(
                ok=False, summary=f"komut başarısız (çıkış {return_code}): {command}"
            )
        return VerificationResult(ok=True)
