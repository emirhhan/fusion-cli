"""Site kapısı: PHP/WordPress işi bittiğinde siteyi ÇALIŞTIRIP aç ve ölç.

Ölçüldü (2 Ekim 2026): rapor "✓ Doğrulandı: php -l 12 dosyada temiz" dedi; site
hiç çalıştırılmamıştı ve tema WordPress'te açılmıyordu. Sözdizimi kanıtı işin
çalıştığını göstermez; çalıştığını gösteren tek şey sayfanın kendisidir.

Kapı şu sırayla karar verir:

1. Ajan `start_preview` ile bir sunucu başlattıysa son değişiklikten SONRA aynı
   adresi yeniden ölçer.
2. Yoksa ve proje kendi başına çalışabiliyorsa (çekirdeği kurulu WordPress ya da
   `index.php`'li PHP) geçici bir `php -S` açar, ölçer, kapatır.
3. Çalıştırılamıyorsa (yalnız tema, çekirdek yok) bunu söyler; "doğrulandı" demez.

Statik HTML ve Node projeleri `browser_verify`'ın işidir; burada ölçülmez.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import VerificationCheckKind
from ...core.tools import ToolContext
from ...core.verification import VerificationResult
from ...tools import preview_server
from ...tools.preview_probe import PageProbe, probe
from ...tools.preview_server import PreviewKind
from ...tools.wordpress_setup import has_core

#: Bu uzantılardan biri değiştiyse site yeniden ölçülür.
SITE_SUFFIXES = frozenset({".php", ".css", ".js", ".html", ".twig", ".json"})

#: Yalnız tema yazıldığında kullanıcıya/modele söylenen not.
NOT_RUNNABLE_NOTE = (
    "Site ÇALIŞTIRILMADI: WordPress çekirdeği yok, yalnız tema/eklenti dosyaları var. "
    "Çalıştığı doğrulanmadı — start_preview çekirdeği SQLite ile kurup siteyi açar."
)


class SiteVerifier:
    """Değişen PHP/WordPress sitesini açıp ölçer."""

    def __init__(self, context: ToolContext, php: str | None) -> None:
        self._context = context
        self._php = php

    async def verify(self) -> VerificationResult:
        if not any(path.suffix.lower() in SITE_SUFFIXES for path in self._context.touched):
            return VerificationResult(ok=True)
        root = self._context.root
        kind = await asyncio.to_thread(preview_server.detect_kind, root)
        if kind not in (PreviewKind.WORDPRESS, PreviewKind.PHP):
            return VerificationResult(ok=True)
        running = preview_server.running(root)
        if running is not None:
            # Tarayıcıyla ölçülür: yüklenemeyen görsel/video ancak orada görünür. Ölçüldü
            # (3 Ekim 2026, 10. kabul koşusu): 18 ürün görseli 404 veriyordu, kapı yalnız
            # HTTP'ye baktığı için "✓ Doğrulandı" dedi ve model işi bitti ilan etti.
            url = str(running.last_probe.get("url") or running.url)
            return _result(await probe(url))
        if kind is PreviewKind.WORDPRESS and not _runnable_wordpress(root):
            return VerificationResult(ok=True, warnings=(NOT_RUNNABLE_NOTE,))
        if self._php is None:
            return VerificationResult(ok=True)
        return await self._temporary(root, kind)

    async def _temporary(self, root: Path, kind: PreviewKind) -> VerificationResult:
        """Geçici sunucu: ölç ve HER yolda kapat (kapı arkasında süreç bırakmaz)."""
        try:
            preview = await preview_server.start(
                root, kind, preview_server.free_port(), php=self._php
            )
        except preview_server.PreviewError as error:
            return VerificationResult(
                ok=False, summary="site açılmadı", findings=(f"Site başlatılamadı: {error}",)
            )
        try:
            return _result(await probe(preview.url, browser=False))
        finally:
            with contextlib.suppress(Exception):
                preview_server.stop(preview)


def _runnable_wordpress(root: Path) -> bool:
    return has_core(root) and (root / "wp-config.php").is_file()


def _result(sonuc: PageProbe) -> VerificationResult:
    problems = sonuc.problems
    evidence = CriterionEvidence(
        criterion_id="site_acildi",
        kind=VerificationCheckKind.TOOL,
        status=EvidenceStatus.FAILED if problems else EvidenceStatus.PASSED,
        summary=f"site çalıştırılıp açıldı: {sonuc.url} ({sonuc.summary()})",
    )
    if not problems:
        return VerificationResult(ok=True, evidence=(evidence,))
    return VerificationResult(
        ok=False,
        summary=f"çalışan sitede {len(problems)} sorun",
        findings=tuple(f"{sonuc.url}: {problem}" for problem in problems),
        evidence=(evidence,),
    )
