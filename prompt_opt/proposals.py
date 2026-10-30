"""Öneri deposu — optimizasyonun bulduğu ama HENÜZ uygulanmamış istem değişiklikleri.

Bir öneri, temel istem metnini ve adayı birlikte taşır; uygulama sırasında istem dosyası
önerinin üretildiği metinle aynı değilse reddedilir (bayat öneri). Skorlar iki kümeden
gelir: optimizasyon kümesi (adayın seçildiği) ve ayrı tutulan küme (adayın gerilemediğinin
doğrulandığı). Durum geçişleri: bekliyor → uygulandi → geri_alindi.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from fusion_cli.core.atomic_file import atomic_replace_text
from fusion_cli.core.errors import EvalError

STATUS_PENDING = "bekliyor"
STATUS_APPLIED = "uygulandi"
STATUS_ROLLED_BACK = "geri_alindi"
PROPOSAL_ID = re.compile(r"on-[0-9a-f]{10}")


def text_digest(text: str) -> str:
    """İstem metninin özeti: bayatlık denetimi tam metni karşılaştırmadan yapılır."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def proposal_id(prompt: str, candidate_text: str) -> str:
    """Aynı istem + aynı aday için kararlı kimlik: yeniden çalıştırma kopya üretmez."""

    return "on-" + hashlib.sha256(f"{prompt}\0{candidate_text}".encode()).hexdigest()[:10]


@dataclass(frozen=True, slots=True)
class Proposal:
    """Kullanıcı onayı bekleyen bir istem değişikliği."""

    id: str
    prompt: str
    created: str
    suite: str
    heldout_suite: str
    base_digest: str
    base_text: str
    candidate_text: str
    addition: str
    opt_base: float
    opt_candidate: float
    heldout_base: float
    heldout_candidate: float
    reason: str
    status: str = STATUS_PENDING
    applied_version: int | None = None


class ProposalStore:
    """Öneri dosyaları (`<id>.json`) için dizin."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def save(self, proposal: Proposal) -> None:
        payload = json.dumps(asdict(proposal), ensure_ascii=False, indent=2)
        atomic_replace_text(self._path(proposal.id), payload)

    def get(self, proposal_id_: str) -> Proposal:
        path = self._path(proposal_id_)
        if not path.is_file():
            raise EvalError(
                f"böyle bir öneri yok: {proposal_id_} (liste: fusion prompt-opt oneriler)"
            )
        return _load(path)

    def list(self) -> tuple[Proposal, ...]:
        if not self._directory.is_dir():
            return ()
        loaded: list[Proposal] = []
        for path in sorted(self._directory.glob("on-*.json")):
            try:
                loaded.append(_load(path))
            except (EvalError, OSError):
                continue
        return tuple(loaded)

    def set_status(
        self, proposal_id_: str, status: str, *, applied_version: int | None = None
    ) -> Proposal:
        updated = replace(self.get(proposal_id_), status=status, applied_version=applied_version)
        self.save(updated)
        return updated

    def _path(self, proposal_id_: str) -> Path:
        # Kimlik dosya adına dönüşür; `../` ile dizin dışına çıkılamaz.
        if not PROPOSAL_ID.fullmatch(proposal_id_):
            raise EvalError(f"geçersiz öneri kimliği: {proposal_id_!r} (örnek: on-0123456789)")
        return self._directory / f"{proposal_id_}.json"


def _load(path: Path) -> Proposal:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Proposal(**raw)
    except (json.JSONDecodeError, TypeError) as error:
        raise EvalError(f"öneri okunamadı: {path.name} — {error}") from error
