"""Öneriyi uygula ve geri al — istem dosyasına YALNIZ burada, kullanıcı komutuyla yazılır.

Sürümleme `PromptStore` ile yapılır ve geri alma bunun üstüne kuruludur:

- uygulamadan önce istemin o anki hâli (dosyadaki) bir sürüm olarak kaydedilir; böylece
  geri alınacak yer HER ZAMAN depodadır, dosyada değil;
- sonra aday yayımlanır ve dosyaya yazılır;
- dosya yazımı düşerse yayımlanan aday geri alınır (depo ile dosya ayrışmaz).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from evals.dongu_kaydi import OLAY_ONERI_GERI_ALINDI, OLAY_ONERI_UYGULANDI, kayit_ekle

from fusion_cli.core.errors import EvalError

from .proposals import (
    STATUS_APPLIED,
    STATUS_PENDING,
    STATUS_ROLLED_BACK,
    Proposal,
    ProposalStore,
    text_digest,
)
from .targets import PromptTarget, get_target
from .versioning import PromptStore

TargetResolver = Callable[[str], PromptTarget]


@dataclass(frozen=True, slots=True)
class AppliedChange:
    """Uygulama/geri alma sonucu: hangi istem, hangi sürüm yayımlandı."""

    prompt: str
    version: int
    previous_version: int


def apply_proposal(
    proposal_id: str,
    *,
    proposals: ProposalStore,
    versions: PromptStore,
    log_path: Path,
    now: Callable[[], float],
    resolve_target: TargetResolver = get_target,
) -> AppliedChange:
    """Bekleyen öneriyi istem dosyasına uygula."""

    proposal = proposals.get(proposal_id)
    if proposal.status != STATUS_PENDING:
        raise EvalError(f"{proposal_id} zaten '{proposal.status}'; yalnız bekleyen öneri uygulanır")
    target = resolve_target(proposal.prompt)
    current_text = target.read()
    if text_digest(current_text) != proposal.base_digest:
        raise EvalError(
            f"{target.file.name} öneri üretildikten sonra değişmiş; öneri bayat. "
            "Yeniden üret: fusion prompt-opt calistir"
        )

    previous = _record_current(versions, proposal.prompt, current_text)
    published = versions.publish(proposal.prompt, proposal.candidate_text)
    try:
        target.write(proposal.candidate_text)
    except OSError as error:
        versions.rollback(proposal.prompt, previous)
        raise EvalError(f"istem dosyası yazılamadı, değişiklik geri alındı: {error}") from error
    proposals.set_status(proposal_id, STATUS_APPLIED, applied_version=published.version)
    kayit_ekle(
        log_path,
        OLAY_ONERI_UYGULANDI,
        {"oneri": proposal_id, "istem": proposal.prompt, "surum": published.version},
        simdi=now(),
    )
    return AppliedChange(proposal.prompt, published.version, previous)


def rollback_prompt(
    prompt: str,
    *,
    proposals: ProposalStore,
    versions: PromptStore,
    log_path: Path,
    now: Callable[[], float],
    version: int | None = None,
    resolve_target: TargetResolver = get_target,
) -> AppliedChange:
    """İstemi önceki sürüme döndür.

    `version` verilmezse EN SON uygulanan önerinin öncesine dönülür. İstem dosyası
    depodaki geçerli sürümden farklıysa (elle düzenlenmiş) reddedilir: kullanıcının
    sonradan yaptığı iş ezilmez.
    """

    target = resolve_target(prompt)
    current = versions.current(prompt)
    if current is None:
        raise EvalError(f"{prompt} için sürüm geçmişi yok; geri alınacak bir şey yok")
    if text_digest(target.read()) != text_digest(current.text):
        raise EvalError(
            f"{target.file.name} sürüm {current.version} ile aynı değil (elle düzenlenmiş); "
            "üstüne yazılmadı"
        )
    applied = _last_applied(proposals, prompt)
    destination = version if version is not None else _before(applied)
    published = versions.rollback(prompt, destination)
    target.write(published.text)
    if applied is not None and applied.applied_version == current.version:
        proposals.set_status(applied.id, STATUS_ROLLED_BACK, applied_version=current.version)
    kayit_ekle(
        log_path,
        OLAY_ONERI_GERI_ALINDI,
        {"istem": prompt, "surum": published.version, "donulen": destination},
        simdi=now(),
    )
    return AppliedChange(prompt, published.version, current.version)


def _record_current(versions: PromptStore, prompt: str, text: str) -> int:
    """Dosyadaki hâli deponun geçerli sürümü yap (zaten öyleyse dokunma); sürüm no döndür."""

    current = versions.current(prompt)
    if current is not None and current.text == text:
        return current.version
    return versions.publish(prompt, text).version


def _last_applied(proposals: ProposalStore, prompt: str) -> Proposal | None:
    uygulananlar = [
        p for p in proposals.list() if p.prompt == prompt and p.status == STATUS_APPLIED
    ]
    return max(uygulananlar, key=lambda p: p.applied_version or 0, default=None)


def _before(applied: Proposal | None) -> int:
    if applied is None or not applied.applied_version or applied.applied_version < 2:
        raise EvalError("geri alınacak uygulanmış öneri yok; --surum <numara> ile sürüm ver")
    return int(applied.applied_version) - 1
