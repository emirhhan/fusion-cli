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
import logging
import os
import re
import shutil
import sys
import uuid
from collections.abc import Callable
from dataclasses import astuple, dataclass, replace
from pathlib import Path

from ...config.models import Config
from ...core.artifact_kind import artifact_only
from ...core.constants import SHELL_TIMEOUT_S
from ...core.diagnosis import diagnose
from ...core.errors import CleanupFailedError
from ...core.evidence import (
    CriterionEvidence,
    EvidenceEnvironment,
    EvidenceEnvironmentSource,
    EvidenceStatus,
)
from ...core.execution_plan import VerificationCheckKind
from ...core.process_control import (
    process_group_options,
    terminate_async_process_tree,
    wait_for_shell_exit,
)
from ...core.remotion_contract import KitContractState
from ...core.repair_ledger import FailureEvidence, FailureOrigin, SourceFingerprint
from ...core.tools import ToolContext
from ...core.verification import (
    TIMEOUT_FINDING_PREFIX,
    UNVERIFIABLE_COMMAND_PREFIX,
    JavaScriptSyntaxChecker,
    VerificationResult,
    Verifier,
)
from ...core.workspace_fingerprint import content_digest
from ...tools.preview_launch import auto_verify_enabled
from ...tools.remotion_observe import observe_frame
from .artifact_verify import ArtifactChangeVerifier
from .browser_verify import BrowserVerifier
from .coverage_verify import EcosystemCoverageVerifier
from .domain_adapters.contract import ToolFailureMarkers
from .domain_adapters.defaults import default_domain_registry
from .domain_adapters.registry import DomainRegistry
from .game_verify import GameProbeVerifier
from .javascript_verify import (
    JavaScriptSyntaxVerifier,
    NodeJavaScriptSyntaxChecker,
    find_node_executable,
)
from .next_route_verify import NextRouteVerifier
from .output_verify import OutputPathVerifier
from .php_verify import PhpVerifier, find_php_executable
from .remotion_bridge import FrameTransport, KitVerificationPlan, RemotionRuntimeVerifier
from .remotion_deferred import DeferredRemotionVerifier
from .remotion_verify import RemotionCssVerifier
from .script_verify import ScriptPathVerifier
from .site_verify import SiteVerifier
from .verify_discovery import (
    command_environment,
    discover_auto_commands,
    evidence_environment,
    related_test_command,
    selected_runner_module,
    source_digest,
)
from .visual_verify import VisualVerifier
from .web_dependency import missing_local_dependencies
from .web_verify import inspect_web_output_by_severity

logger = logging.getLogger(__name__)

#: Web kapısının denetlediği dosya uzantıları.
WEB_SUFFIXES = frozenset({".html", ".htm", ".css", ".js", ".mjs", ".cjs"})


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
    config: Config,
    *,
    root: Path,
    tool_context: ToolContext | None,
    domains: DomainRegistry | None = None,
    remotion_contract: KitVerificationPlan | None = None,
    remotion_state: KitContractState | None = None,
    remotion_transport: FrameTransport | None = None,
    dev_server_allowed: Callable[[], bool] = lambda: True,
    runner_resolver: Callable[[str], str | None] = shutil.which,
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

    `tool_context` ZORUNLUDUR ve varsayılanı yoktur. Web, tarayıcı ve görsel
    kapıların üçü de ona bağlıdır; opsiyonel bırakıldığında REPL onu geçirmeyi
    unutmuş ve interaktif oturumda `web_verification: true` olmasına rağmen
    HİÇBİR kapı kurulmamıştı — üstelik bunu hiçbir şey söylemiyordu. Argümanı
    zorunlu yapmak bu hata sınıfını imkânsız kılar: çağıran ya bağlamı verir ya
    da None'ı bilerek yazar.

    `domains` alan kaydıdır: keşfedilen alan kapıları ve sıfır-çıkış işaretleri
    buradan gelir. Verilmezse varsayılan kayıt kurulur; kayıt değer nesnesi olduğu
    için `AgentDeps.domains` ile ayrışmaz.
    """
    verifiers: list[Verifier] = []
    registry = domains if domains is not None else default_domain_registry()
    transport = remotion_transport if remotion_transport is not None else observe_frame
    # Açık runtime planı yoksa genel Remotion projeleri mevcut davranışını korur.
    if remotion_contract is not None:
        verifiers.append(
            RemotionRuntimeVerifier(
                root,
                remotion_contract,
                transport=transport,
            )
        )
    elif remotion_state is not None:
        verifiers.append(
            DeferredRemotionVerifier(
                root,
                remotion_state,
                transport=transport,
            )
        )
    elif config.runtime.web_verification and tool_context is not None:
        verifiers.append(
            DeferredRemotionVerifier(
                root,
                tool_context.remotion_contract,
                transport=transport,
            )
        )
    # Yapılandırılmış komut varsa o kazanır; yoksa PROJEDEN KEŞFEDİLİR.
    #
    # Kapı eskiden tamamen opt-in'di ve pratikte hiç kurulmuyordu. Bedeli ölçüldü:
    # agent bir TSX dosyasının ortasına beş kapanış etiketi ekledi, dosya 12
    # sözdizimi hatasıyla bozuldu ve tur "tamamladım" diyerek kapandı. Bozuk kod
    # teslim edip başarı iddia etmek, hiç yazmamaktan kötüdür.
    #
    # Keşif komut UYDURMAZ: yalnızca projede kanıtı olanı önerir (var olan script,
    # tanımlı hedef) ve test paketini dışarıda bırakır — sorulan soru "kodu bozdum
    # mu", "tüm testler geçiyor mu" değil.
    configured = config.runtime.verification_commands
    commands = configured or discover_auto_commands(root, domains=registry)
    if commands and not configured:
        # Keşif tek ekosistem seçer; seçilmeyen (ör. `app/` TypeScript) denetimsiz kalır.
        # Kullanıcı komutları kendisi yazdıysa kapsamı o belirlemiştir; uyarılmaz (A4-66).
        verifiers.append(EcosystemCoverageVerifier(root, domains=registry))
    if commands:
        verifiers.append(
            CommandVerifier(
                commands,
                tool_context=tool_context,
                cwd=str(root),
                timeout_s=SHELL_TIMEOUT_S,
                failure_markers=registry.output_failure_markers(),
                runner_paths=_resolved_runners(root, commands, runner_resolver),
            )
        )
    # Betik-yol kapısı YALNIZCA `package.json` olan projede kurulur; başka yerde
    # zaten hiçbir şey söylemez ve "hiç kapı yok" durumunu bozmamalıdır. Komut
    # çalıştırmaz, dosya sistemine bakar: kardeş projeleri birbirine bağlayan bir
    # mega-app'te yanlış yol en sık ve en sessiz hata sınıfıdır ve derleme kapısı
    # onu göremez (o betik derleme sırasında çalışmaz).
    if (root / "package.json").is_file():
        verifiers.append(ScriptPathVerifier(root))
    if tool_context is not None and any(
        (root / name).is_file() for name in ("next.config.js", "next.config.mjs", "next.config.ts")
    ):
        verifiers.append(NextRouteVerifier(root, tool_context.changes))
    if config.runtime.web_verification and tool_context is not None:
        node_path = find_node_executable()
        javascript_checker = (
            NodeJavaScriptSyntaxChecker(node_path) if node_path is not None else None
        )
        php_path = find_php_executable()
        verifiers.append(
            WebVerifier(
                tool_context,
                javascript_checker=javascript_checker,
                # PHP ve WordPress teması da web çıktısıdır (bkz. `php_verify`).
                php=PhpVerifier(tool_context, php_path),
                # Sözdizimi temiz ≠ site açılıyor: PHP/WordPress sitesi çalıştırılıp ölçülür.
                site=SiteVerifier(tool_context, php_path),
            )
        )
    if config.runtime.web_verification and tool_context is not None:
        verifiers.append(ArtifactChangeVerifier(tool_context))
    # Çıktı/Remotion/oyun kapıları üretilen işi ölçer: web doğrulamasıyla birlikte açılır
    # ve onunla kapatılır ("tüm kapılar kapatılabilir" sözleşmesi).
    if config.runtime.web_verification and tool_context is not None:
        # İstenen çıktı dosyası istenen yolda mı (ölçüldü: Remotion videosu alt klasörde kaldı).
        verifiers.append(OutputPathVerifier(tool_context))
        # Remotion'da CSS animasyonu videoda oynamaz (ölçüldü: beceri yasaklasa da yazıldı).
        verifiers.append(RemotionCssVerifier(tool_context))
        # play_probe ile denenen oyun kapanışta yeniden oynatılır (ölçüldü: hata 15 kez görüldü).
        verifiers.append(GameProbeVerifier(tool_context))
    if (
        config.runtime.browser_verification
        and tool_context is not None
        # `.claude/launch.json` üst düzey `autoVerify: false` projede otomatik önizleme
        # doğrulamasını kapatır (Claude Code: varsayılan açık, #440).
        and auto_verify_enabled(root)
    ):
        # Playwright kurulu değilse bu kapı sessizce geçer; kendi içinde karar verir.
        verifiers.append(BrowserVerifier(tool_context, dev_server_allowed=dev_server_allowed))
    if config.runtime.visual_verification and tool_context is not None and config.vision:
        verifiers.append(VisualVerifier(tool_context, config))

    if not verifiers:
        return None
    return verifiers[0] if len(verifiers) == 1 else CompositeVerifier(tuple(verifiers))


class CompositeVerifier:
    """Birden çok doğrulayıcıyı önem derecesini kaybetmeden birleştirir."""

    def __init__(
        self,
        verifiers: tuple[Verifier, ...],
        *,
        attempt_identity: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._verifiers = verifiers
        self._attempt_identity = attempt_identity

    def evidence_environment(self) -> EvidenceEnvironment | None:
        """Alt kapıların komut ortamlarını önbellek için tek kimlikte birleştir."""
        environments = [
            verifier.evidence_environment()
            for verifier in self._verifiers
            if isinstance(verifier, EvidenceEnvironmentSource)
        ]
        if any(environment is None for environment in environments):
            return None
        known = [environment for environment in environments if environment is not None]
        if not known:
            return None
        return EvidenceEnvironment(
            *("\n".join(values) for values in zip(*(astuple(item) for item in known), strict=True))
        )

    async def verify(self) -> VerificationResult:
        ozetler: list[str] = []
        blocking: list[str] = []
        warnings: list[str] = []
        advisories: list[str] = []
        evidence: list[CriterionEvidence] = []
        failure_evidence: list[FailureEvidence] = []
        failed = False

        for verifier in self._verifiers:
            try:
                result = await verifier.verify()
            except Exception as error:  # sınır: tek kapının çöküşü tüm doğrulamayı düşürmesin
                # Çöken kapı "geçti" DEĞİL "doğrulanamadı"dır: uyarı olur, diğer kapılar sürer
                # (A4-24; iptal BaseException olarak yayılır).
                logger.warning("Doğrulama kapısı çöktü: %s", type(verifier).__name__, exc_info=True)
                warnings.append(
                    f"doğrulama kapısı çöktü ({type(verifier).__name__}: {error}); "
                    "bu kapının sonucu DOĞRULANAMADI"
                )
                continue

            warnings.extend(result.warnings)
            advisories.extend(result.advisories)
            evidence.extend(result.evidence)
            failure_evidence.extend(result.failure_evidence)

            if result.ok:
                continue

            failed = True
            if not result.failure_evidence:
                # Legacy kapının gerçek başarısızlığı sınıflandırılmamıştır; başka
                # kapının altyapı kanıtı bu bağımsız ürün düzeltmesi yolunu kapatamaz.
                failure_evidence.append(
                    FailureEvidence(
                        check_id=f"{type(verifier).__name__}/unclassified",
                        family="unclassified_verifier_failure",
                        attempt_id=self._attempt_identity(),
                    )
                )
            if result.summary:
                ozetler.append(result.summary)
            blocking.extend(result.findings)

        if not failed and not warnings and not advisories and not evidence:
            return VerificationResult(ok=True)

        return VerificationResult(
            ok=not failed,
            summary="; ".join(ozetler),
            findings=tuple(blocking),
            warnings=tuple(warnings),
            advisories=tuple(advisories),
            evidence=tuple(evidence),
            failure_evidence=tuple(failure_evidence),
        )


class WebVerifier:
    """Agent'ın yazdığı web dosyalarını önem derecesiyle mekanik olarak denetler."""

    def __init__(
        self,
        tool_context: ToolContext,
        *,
        javascript_checker: JavaScriptSyntaxChecker | None = None,
        php: PhpVerifier | None = None,
        site: SiteVerifier | None = None,
    ) -> None:
        self._context = tool_context
        self._javascript_checker = javascript_checker
        self._php = php
        self._site = site

    async def verify(self) -> VerificationResult:
        result = await self._verify_markup()
        for part in (self._php, self._site):
            if part is None:
                continue
            other = await part.verify()
            if other.ok and not other.warnings and not other.evidence:
                continue
            result = VerificationResult(
                ok=result.ok and other.ok,
                summary="; ".join(text for text in (result.summary, other.summary) if text),
                findings=(*result.findings, *other.findings),
                warnings=(*result.warnings, *other.warnings),
                advisories=(*result.advisories, *other.advisories),
                evidence=(*result.evidence, *other.evidence),
            )
        return result

    async def _verify_markup(self) -> VerificationResult:
        files: dict[str, str] = {}
        dependency_findings: list[str] = []
        root = self._context.root

        for path in self._context.touched:
            if path.suffix.lower() not in WEB_SUFFIXES:
                continue
            try:
                content = path.read_text(encoding="utf-8")
                # Anahtar köke göreli YOL: aynı adlı `a/index.html` ve `b/index.html`
                # birbirini ezmesin (A4-08; eskiden `path.name`).
                files[_web_key(path, root)] = content
                if path.suffix.lower() in (".html", ".htm"):
                    dependency_findings.extend(
                        missing_local_dependencies(content, document=path, root=root)
                    )
            except OSError:
                continue

        if not files:
            return VerificationResult(ok=True)

        blocking, warnings, advisories = inspect_web_output_by_severity(
            files, context=_project_web_files(root, exclude=frozenset(files))
        )
        blocking = (*blocking, *dependency_findings)
        if self._javascript_checker is not None:
            syntax_result = await JavaScriptSyntaxVerifier(
                self._context,
                self._javascript_checker,
            ).verify()
            blocking = (*blocking, *syntax_result.findings)

        if not blocking and not warnings and not advisories:
            return VerificationResult(ok=True)

        summary = f"web çıktısında {len(blocking)} engelleyici sorun" if blocking else ""

        return VerificationResult(
            ok=not blocking,
            summary=summary,
            findings=blocking,
            warnings=warnings,
            advisories=advisories,
        )


#: Başarısız komutun çıktısından modele taşınacak SON satır sayısı.
#
# Kuyruk tutulur, baş değil: derleyici ve test koşucuları özeti ve hatayı sona
# yazar (pytest'in "FAILED ..." satırları, mypy'ın "Found N errors"). Baş taraf
# tutulsaydı prompt'a ilerleme noktalarından başka bir şey girmezdi.
_OUTPUT_TAIL_LINES = 200

#: Süreç grubu öldükten sonra borudaki kalan çıktıyı okumak için tanınan azami süre.
_OKUYUCU_BOSALTMA_S = 2.0

#: Bulguya girecek en fazla karakter. Uzun tek satırlar (minified çıktı, uzun yol
# listeleri) satır sayısı sınırını delebilir; prompt bütçesi bunu kaldırmaz.
_OUTPUT_MAX_CHARS = 8_000


class CommandVerifier:
    """Yapılandırılmış kabuk komutlarını sırayla çalıştıran doğrulayıcı.

    Çıktı YUTULMAZ. Kapının işi "bir sorun var" demek değil, sorunun metnini
    modele taşımaktır: `findings` boş dönerse motor düzeltici turu hiç açmaz
    (bkz. `loop.run_agent`), yani kapı sessizce işlevsiz kalır.
    """

    def __init__(
        self,
        commands: tuple[str, ...],
        *,
        cwd: str,
        timeout_s: float,
        failure_markers: tuple[ToolFailureMarkers, ...] | None = None,
        runtime_identity: Callable[[], str] = lambda: sys.version,
        attempt_identity: Callable[[], str] = lambda: uuid.uuid4().hex,
        runner_paths: tuple[Path, ...] = (),
        tool_context: ToolContext | None = None,
    ) -> None:
        self._tool_context = tool_context
        self._commands = commands
        self._cwd = cwd
        self._timeout_s = timeout_s
        self._runtime_identity = runtime_identity
        self._attempt_identity = attempt_identity
        self._runner_paths = runner_paths
        # İşaretler alan kaydından gelir; verilmezse varsayılan kaydın işaretleri.
        # Tarama proje işaretinden bağımsızdır: hatayı basıp `0` dönen ARAÇTIR.
        self._failure_markers = (
            failure_markers
            if failure_markers is not None
            else default_domain_registry().output_failure_markers()
        )

    def evidence_environment(self) -> EvidenceEnvironment | None:
        """Dosya hashlerini her kapı sorgusunda yeniden ölç; ortamı tarama."""
        return evidence_environment(
            Path(self._cwd),
            self._commands,
            runtime=self._runtime_identity(),
            runner_paths=self._runner_paths,
        )

    async def verify_intermediate(self, changed: tuple[str, ...]) -> VerificationResult:
        """Ara kapıya özel seçimi bağımsız örnekte çalıştır; final komutlarını değiştirme."""
        commands = tuple(
            [
                await asyncio.to_thread(related_test_command, Path(self._cwd), command, changed)
                for command in self._commands
            ]
        )
        verifier = CommandVerifier(
            commands,
            cwd=self._cwd,
            timeout_s=self._timeout_s,
            failure_markers=self._failure_markers,
            runtime_identity=self._runtime_identity,
            attempt_identity=self._attempt_identity,
            runner_paths=self._runner_paths,
            tool_context=self._tool_context,
        )
        return await verifier.verify()

    async def verify(self) -> VerificationResult:
        if self._tool_context is not None and artifact_only(self._tool_context.changes.paths):
            return VerificationResult(ok=True)

        evidence: list[CriterionEvidence] = []
        warnings: list[str] = []
        failures: list[FailureEvidence] = []
        for command in self._commands:
            result = await self._run(command)
            evidence.extend(result.evidence)
            warnings.extend(result.warnings)
            failures.extend(result.failure_evidence)
            if not result.ok:
                return VerificationResult(
                    ok=False,
                    summary=result.summary,
                    findings=result.findings,
                    warnings=tuple(warnings),
                    advisories=result.advisories,
                    evidence=tuple(evidence),
                    failure_evidence=tuple(failures),
                )
        return VerificationResult(
            ok=True,
            warnings=tuple(warnings),
            evidence=tuple(evidence),
            failure_evidence=tuple(failures),
        )

    async def _run(self, command: str) -> VerificationResult:
        environment = await asyncio.to_thread(
            evidence_environment,
            Path(self._cwd),
            (command,),
            runtime=self._runtime_identity(),
            runner_paths=self._runner_paths,
        )
        before = await asyncio.to_thread(source_digest, Path(self._cwd))
        call_id = self._attempt_identity()
        warnings: list[str] = []
        result = await self._calistir(command, warnings)
        failures: tuple[FailureEvidence, ...] = ()
        if any(item.status is not EvidenceStatus.PASSED for item in result.evidence):
            output = "\n".join(item.output for item in result.evidence)
            origin, family = _command_failure(result, output, cwd=Path(self._cwd), command=command)
            sources = await asyncio.to_thread(_failure_sources, Path(self._cwd), output)
            failures = (
                FailureEvidence(
                    check_id=command,
                    family=family,
                    attempt_id=call_id,
                    sources=sources,
                    origin=origin,
                    environment=environment,
                ),
            )
        after = await asyncio.to_thread(source_digest, Path(self._cwd))
        current_environment = await asyncio.to_thread(
            evidence_environment,
            Path(self._cwd),
            (command,),
            runtime=self._runtime_identity(),
            runner_paths=self._runner_paths,
        )
        if current_environment != environment:
            environment = None
        measured = tuple(
            replace(
                item,
                source_digest=before,
                source_after_digest=after,
                environment=environment,
                call_id=call_id,
            )
            for item in result.evidence
        )
        return replace(
            result,
            evidence=measured,
            warnings=(*result.warnings, *warnings),
            failure_evidence=failures,
        )

    @staticmethod
    async def _okuyucuyu_bitir(okuyucu: asyncio.Future[None]) -> None:
        """Süreç grubu öldükten sonra borudaki kalan çıktıyı KISA süreyle boşalt."""
        try:
            await asyncio.wait_for(asyncio.shield(okuyucu), timeout=_OKUYUCU_BOSALTMA_S)
        except (TimeoutError, asyncio.CancelledError):
            pass
        finally:
            okuyucu.cancel()

    async def _calistir(self, command: str, uyarilar: list[str]) -> VerificationResult:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=self._cwd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **process_group_options(),
            )
        except OSError as exc:
            detay = f"komut başlatılamadı: {command} ({exc})"
            return VerificationResult(
                ok=False,
                summary=detay,
                findings=(detay,),
                evidence=(
                    CriterionEvidence(
                        criterion_id=command,
                        kind=VerificationCheckKind.COMMAND,
                        status=EvidenceStatus.UNVERIFIED,
                        summary=detay,
                        command=command,
                    ),
                ),
            )

        # Çıktı BİRİKTİREREK okunur, `communicate()` ile toplu değil.
        #
        # Sebep ölçüldü: bozuk bir Godot projesinde `godot --headless --quit`
        # gerçek sebebi basıyor ("Can't run project: no main scene defined in
        # the project") ve SONRA asılı kalıyor. `communicate()` zaman aşımına
        # uğradığında o çıktı kayboluyor ve kapı yalnızca "zaman aşımına uğradı"
        # diyordu; model neyi düzelteceğini öğrenemiyordu. Asılmadan önce
        # söylenen, kapının elindeki EN DEĞERLİ tanıdır.
        tampon = bytearray()

        async def _biriktir() -> None:
            akis = process.stdout
            if akis is None:
                return
            while parca := await akis.read(4096):
                tampon.extend(parca)

        okuyucu = asyncio.ensure_future(_biriktir())
        zaman_asimi = False
        try:
            await asyncio.wait_for(wait_for_shell_exit(process), timeout=self._timeout_s)
        except TimeoutError:
            zaman_asimi = True
        finally:
            # Her çıkış yolunda (normal, zaman aşımı, iptal) grup öldürülür: kabuk
            # çıksa bile arka plan çocuğu borunun ucunu tuttuğu için okuyucu EOF
            # görmez. Ölçüldü (29 Ekim): `sleep 300 & echo bitti` kapıyı sınırsız
            # bekletiyordu; `process.kill()` yalnız kabuğu öldürüp torunu bırakıyordu.
            try:
                await terminate_async_process_tree(process)
            except CleanupFailedError as exc:
                uyari = f"süreç ağacı temizliği doğrulanamadı: {command} ({exc})"
                logger.warning(uyari)
                uyarilar.append(uyari)
            await self._okuyucuyu_bitir(okuyucu)
        if zaman_asimi:
            detay = f"{TIMEOUT_FINDING_PREFIX} ({self._timeout_s}s): {command}"
            onceki = _tail(bytes(tampon)).strip()
            if onceki:
                detay = f"{detay}\nAsılmadan önce şunu söyledi:\n{onceki}"
            return VerificationResult(
                ok=False,
                summary=detay,
                findings=(detay,),
                evidence=(
                    CriterionEvidence(
                        criterion_id=command,
                        kind=VerificationCheckKind.COMMAND,
                        status=EvidenceStatus.FAILED,
                        summary=TIMEOUT_FINDING_PREFIX,
                        command=command,
                        output=onceki,
                    ),
                ),
            )
        ham = bytes(tampon)

        if process.returncode == 0:
            output = _tail(ham)
            bildirilen = _reported_failure(command, output, self._failure_markers)
            if bildirilen:
                ozet = f"komut sıfır döndü ama hata bildirdi ({bildirilen}): {command}"
                tani = diagnose(output)
                return VerificationResult(
                    ok=False,
                    summary=ozet,
                    findings=(ozet, *((tani.as_guidance(),) if tani else ()), output),
                    evidence=(
                        CriterionEvidence(
                            criterion_id=command,
                            kind=VerificationCheckKind.COMMAND,
                            status=EvidenceStatus.FAILED,
                            summary=ozet,
                            command=command,
                            output=output,
                        ),
                    ),
                )
            return VerificationResult(
                ok=True,
                evidence=(
                    CriterionEvidence(
                        criterion_id=command,
                        kind=VerificationCheckKind.COMMAND,
                        status=EvidenceStatus.PASSED,
                        summary="komut başarıyla çalıştı",
                        command=command,
                        output=output,
                    ),
                ),
            )
        if process.returncode == _COMMAND_NOT_FOUND:
            # Araç KURULU DEĞİL — bu bir kod hatası değildir. Ölçüldü: keşfedilen
            # kapı `ruff check .` çalıştırdı, ruff yalnızca sanal ortamda kuruluydu
            # ve PATH'te yoktu; kapı "doğrulama geçmedi" dedi, oysa kullanıcının
            # kodunda hiçbir sorun yoktu. Eksik araç yüzünden turu düşürmek, kapıyı
            # gürültüye çevirir ve gerçek hatalara olan güveni yok eder.
            logger.info("doğrulama komutu bulunamadı, doğrulanamadı: %s", command)
            detay = f"{UNVERIFIABLE_COMMAND_PREFIX}; sonuç doğrulanamadı: {command}"
            return VerificationResult(
                ok=True,
                warnings=(detay,),
                evidence=(
                    CriterionEvidence(
                        criterion_id=command,
                        kind=VerificationCheckKind.COMMAND,
                        status=EvidenceStatus.UNVERIFIED,
                        summary=detay,
                        command=command,
                        output=_tail(ham),
                    ),
                ),
            )

        ozet = f"komut başarısız (çıkış {process.returncode}): {command}"
        output = _tail(ham)
        # Tanı çıkarılabiliyorsa bulgunun BAŞINA konur: hem kullanıcı hem kurtarma
        # turu "hangi dosyanın hangi satırı" bilgisini ham çıktıyı taramadan görür.
        tani = diagnose(output)
        bulgular = (ozet, *((tani.as_guidance(),) if tani else ()), output)
        return VerificationResult(
            ok=False,
            summary=ozet,
            findings=bulgular,
            evidence=(
                CriterionEvidence(
                    criterion_id=command,
                    kind=VerificationCheckKind.COMMAND,
                    status=EvidenceStatus.FAILED,
                    summary=ozet,
                    command=command,
                    output=output,
                ),
            ),
        )


#: Proje bağlamı okunurken gezilmeyen dizinler (bağımlılık, derleme çıktısı, VCS).
_CONTEXT_SKIP_DIRS = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        "out",
        ".next",
        ".nuxt",
        ".venv",
        "venv",
        "__pycache__",
        "target",
        "vendor",
        ".cache",
        "coverage",
    }
)
#: Bağlam taramasının üst sınırları: dev bir kök (ev dizini gibi) kapıyı yavaşlatmasın.
_CONTEXT_MAX_FILES = 300
_CONTEXT_MAX_VISITED = 5000
_CONTEXT_MAX_BYTES = 512_000


def _web_key(path: Path, root: Path) -> str:
    """Web dosyasının anahtarı: köke göreli POSIX yol (kök dışındaysa tam yol)."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def _project_web_files(root: Path, *, exclude: frozenset[str]) -> dict[str, str]:
    """Dokunulmayan yerel web dosyalarını dizinden oku (dosyalar-arası kurallar için).

    Ölçüldü (29 Ekim): kapı yalnız dokunulanları gördüğü için çok sayfalı sitede
    `app.js`'i bağlayan dokunulmamış `index.html` ve ortak CSS yok sayılıyor, yanlış
    BLOCKING çıkıyordu (A4-07). Sınırlıdır; okunamayan dosya atlanır.
    """
    bulunan: dict[str, str] = {}
    ziyaret = 0
    try:
        for klasor, alt_klasorler, adlar in os.walk(root):
            alt_klasorler[:] = [
                ad
                for ad in alt_klasorler
                if ad not in _CONTEXT_SKIP_DIRS and not ad.startswith(".")
            ]
            for ad in adlar:
                ziyaret += 1
                if ziyaret > _CONTEXT_MAX_VISITED or len(bulunan) >= _CONTEXT_MAX_FILES:
                    return bulunan
                yol = Path(klasor) / ad
                if yol.suffix.lower() not in WEB_SUFFIXES:
                    continue
                anahtar = _web_key(yol, root)
                if anahtar in exclude:
                    continue
                try:
                    if yol.stat().st_size > _CONTEXT_MAX_BYTES:
                        continue
                    bulunan[anahtar] = yol.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
    except OSError:
        return bulunan
    return bulunan


#: Kabuk "komut bulunamadı" için bu çıkış kodunu verir (POSIX sözleşmesi).
_COMMAND_NOT_FOUND = 127


def _reported_failure(
    command: str, output: str, failure_markers: tuple[ToolFailureMarkers, ...]
) -> str:
    """Çıkış kodu sessiz kalsa da aracın kendi bildirdiği hatayı yakala.

    Ölçüldü: motor hem bozuk script'te hem çalışma zamanı hatasında `0` döndürüyor;
    çıkış koduna bakan kapı bunu "başarıyla çalıştı" sayıp kabul veriyordu. İşaretler
    alan kaydından gelir ve dar tutulur: yalnız aracın KENDİ hata satırında geçen
    ifadeler, yoksa kapı gürültüye döner.
    """
    lowered = output.casefold()
    for entry in failure_markers:
        if not re.search(rf"\b{re.escape(entry.tool)}\b", command, re.IGNORECASE):
            continue
        for marker in entry.markers:
            if marker in lowered:
                return marker
    return ""


def _tail(raw: bytes) -> str:
    """Çıktının son kısmını modele verilebilir tek bir metne indir."""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return "(komut hiç çıktı üretmedi)"
    tail = "\n".join(text.split("\n")[-_OUTPUT_TAIL_LINES:])
    return tail if len(tail) <= _OUTPUT_MAX_CHARS else tail[-_OUTPUT_MAX_CHARS:]


_PROVIDER_FAILURE = re.compile(
    r"\b(?:provider quota|quota exceeded|rate.?limit|insufficient_quota|HTTP\s+429)\b",
    re.IGNORECASE,
)
_ERROR_FAMILY = re.compile(r"\b([A-Za-z_][\w.]*(?:Error|Exception))\b")


def _command_failure(
    result: VerificationResult, output: str, *, cwd: Path, command: str
) -> tuple[FailureOrigin, str]:
    """Ölçülemeyen koşucuyu ve sağlayıcı kesintisini ürün arızasından ayır."""
    if any(item.status is EvidenceStatus.UNVERIFIED for item in result.evidence):
        return FailureOrigin.INFRASTRUCTURE, "runner_unavailable"
    environment = command_environment(cwd, command)
    module = selected_runner_module(environment) if environment is not None else None
    if (
        module is not None
        and "Traceback (most recent call last)" not in output
        and re.search(rf": No module named ['\"]?{re.escape(module)}['\"]?(?:\s|$)", output)
    ):
        return FailureOrigin.INFRASTRUCTURE, "runner_unavailable"
    if _PROVIDER_FAILURE.search(output):
        return FailureOrigin.PROVIDER, "provider_unavailable"
    if result.summary.startswith(TIMEOUT_FINDING_PREFIX):
        return FailureOrigin.INFRASTRUCTURE, "timeout"
    families = _ERROR_FAMILY.findall(output)
    return FailureOrigin.PRODUCT, families[-1] if families else "command_failed"


def _failure_sources(root: Path, output: str) -> tuple[SourceFingerprint, ...]:
    """Tanıdaki ilgili tek kaynak için içerik özeti; kaynak metni kayda taşınmaz."""
    diagnosis = diagnose(output)
    if diagnosis is None:
        return ()
    root = root.resolve()
    source = (root / diagnosis.path.removeprefix("res://")).resolve()
    if not source.is_relative_to(root) or source.name.startswith(".env") or not source.is_file():
        return ()
    return (SourceFingerprint(source.relative_to(root).as_posix(), content_digest((source,))),)


def _resolved_runners(
    root: Path, commands: tuple[str, ...], resolver: Callable[[str], str | None]
) -> tuple[Path, ...]:
    """Uygulama kurulum sınırında koşucu erişimini çöz ve kanıt yoluna enjekte et."""
    runners: set[Path] = set()
    for command in commands:
        environment = command_environment(root, command)
        if environment is None:
            continue
        program = environment.tokens[0]
        resolved = str(environment.cwd / program) if "/" in program else resolver(program)
        if resolved is not None:
            runners.add(Path(resolved).resolve())
    return tuple(sorted(runners))


async def verify_intermediate(verifier: Verifier, changed: tuple[str, ...]) -> VerificationResult:
    """Yalnız mevcut komut kapısını daralt; diğer kapılar normal çalışır."""
    if isinstance(verifier, CommandVerifier):
        return await verifier.verify_intermediate(changed)
    if isinstance(verifier, CompositeVerifier):
        selected = tuple(_IntermediateVerifier(item, changed) for item in verifier._verifiers)
        return await CompositeVerifier(selected).verify()
    return await verifier.verify()


@dataclass(frozen=True, slots=True)
class _IntermediateVerifier:
    """Bileşik kapının mevcut birleştirme davranışına ara seçim bağlar."""

    verifier: Verifier
    changed: tuple[str, ...]

    async def verify(self) -> VerificationResult:
        return await verify_intermediate(self.verifier, self.changed)
