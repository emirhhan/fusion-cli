"""Doğrulanmış rutinlerden yalnız öneri saklar; beceri kurmaz veya çalıştırmaz."""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from ..core.errors import FusionError
from ..core.memory import RoutineObservation, RoutineSpec, SkillProposal
from ..core.redaction import contains_sensitive
from ..core.repair_ledger import FailureOrigin
from ..core.task_protocol import args_digest
from .store import process_lock

REQUIRED_SUCCESSFUL_RUNS = 3
PROPOSAL_SCHEMA_VERSION = 2


class SkillProposalError(FusionError):
    """Öneri dosyası güvenle okunamadı veya yazılamadı."""


def _normalized(routine: RoutineSpec) -> RoutineSpec:
    """Aynı şema/önkoşul/kontrolün biçim farklarını tek kimlikte birleştir."""
    try:
        schema = json.loads(routine.input_schema)
    except (ValueError, TypeError) as error:
        raise SkillProposalError("Rutin girdi şeması geçerli JSON olmalı.") from error
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise SkillProposalError("Rutin girdi şeması bir nesne tanımlamalı.")
    if not routine.routine_id.strip() or not routine.preconditions or not routine.checks:
        raise SkillProposalError("Rutin kimliği, önkoşullar ve kontroller boş olamaz.")
    preconditions = tuple(
        sorted({value.strip() for value in routine.preconditions if value.strip()})
    )
    checks = tuple(sorted({value.strip() for value in routine.checks if value.strip()}))
    if not preconditions or not checks:
        raise SkillProposalError("Rutin önkoşulları ve kontrolleri boş olamaz.")
    normalized = replace(
        routine,
        routine_id=routine.routine_id.strip(),
        input_schema=json.dumps(schema, sort_keys=True, ensure_ascii=False),
        preconditions=preconditions,
        checks=checks,
    )
    if _sensitive_value(asdict(normalized)) or _sensitive_value(schema):
        raise SkillProposalError("Hassas bilgi içeren rutin önerisi saklanamaz.")
    return normalized


def _sensitive_value(value: object) -> bool:
    """Ham metni JSON kaçışı hassas eşleşmeyi gizlemeden denetle."""
    if isinstance(value, str):
        return contains_sensitive(value)
    if isinstance(value, dict):
        return any(_sensitive_value(key) or _sensitive_value(item) for key, item in value.items())
    if isinstance(value, (tuple, list)):
        return any(_sensitive_value(item) for item in value)
    return False


def _proposal_id(routine: RoutineSpec, split: str) -> str:
    """Mevcut kanonik özet yordamını kullan; ders için ikinci kimlik açma."""
    identity = asdict(routine)
    identity.pop("description")
    if not routine.source_digest:
        identity.pop("source_digest")
    return args_digest({"routine": identity, "source_split": split})


class SkillProposalStore:
    """Çağıranın doğruladığı koşumları ayrı split ve koşum kimliğiyle biriktirir."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def observe(
        self,
        routine: RoutineSpec,
        observation: RoutineObservation,
    ) -> SkillProposal | None:
        """Üç ayrı başarılı kanıt olmadan öneri yayınlama; yinelemeleri sayma."""
        observation = _canonical_observation(observation)
        if not self._is_verified(observation):
            return None
        normalized = _normalized(routine)
        return await asyncio.to_thread(self._observe, normalized, observation)

    async def list(self, *, source_split: str | None = None) -> tuple[SkillProposal, ...]:
        """Yalnız eşiği geçen önerileri döndür; açık split başka kökenleri dışlar."""
        proposals = await asyncio.to_thread(self._read)
        return tuple(
            item
            for item in proposals
            if len(item.observations) >= REQUIRED_SUCCESSFUL_RUNS
            and (source_split is None or item.source_split == source_split)
        )

    async def get(self, proposal_id: str) -> SkillProposal | None:
        """Listeleme eşiğini geçmemiş birikimi beceri önerisi diye gösterme."""
        return next((item for item in await self.list() if item.id == proposal_id), None)

    @staticmethod
    def _is_verified(observation: RoutineObservation) -> bool:
        return (
            observation.success
            and observation.verified
            and observation.failure_origin is FailureOrigin.PRODUCT
            and bool(observation.run_id.strip())
            and bool(observation.evidence_refs)
            and all(reference.strip() for reference in observation.evidence_refs)
            and not _sensitive_value(asdict(observation))
        )

    def _observe(
        self, routine: RoutineSpec, observation: RoutineObservation
    ) -> SkillProposal | None:
        try:
            with process_lock(self._path.parent) as acquired:
                if not acquired:
                    raise SkillProposalError("Öneri dosyası kilitli; daha sonra yeniden dene.")
                proposals = list(self._read())
                identity = _proposal_id(routine, observation.source_split)
                existing = next((item for item in proposals if item.id == identity), None)
                if existing is None:
                    existing = SkillProposal(identity, routine, observation.source_split, ())
                if _is_new_proof(existing.observations, observation):
                    existing = replace(existing, observations=(*existing.observations, observation))
                proposals = [item for item in proposals if item.id != identity]
                proposals.append(existing)
                self._write(tuple(proposals))
                return existing if len(existing.observations) >= REQUIRED_SUCCESSFUL_RUNS else None
        except OSError as error:
            raise SkillProposalError(
                "Öneri dosyası yazılamadı; dizin izinlerini kontrol et."
            ) from error

    def _write(self, proposals: tuple[SkillProposal, ...]) -> None:
        payload = {
            "schema_version": PROPOSAL_SCHEMA_VERSION,
            "proposals": [asdict(item) for item in proposals],
        }
        if self._path.is_symlink():
            raise SkillProposalError("Öneri dosyası sembolik bağ olamaz.")
        # Benzersiz geçici dosya başka kayıtları ezmez; değişim atomiktir.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._path.parent, prefix=self._path.name, delete=False
        ) as handle:
            temporary = Path(handle.name)
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, default=_json_value), encoding="utf-8"
            )
            temporary.replace(self._path)
        finally:
            temporary.unlink(missing_ok=True)

    def _read(self) -> tuple[SkillProposal, ...]:
        if not self._path.exists():
            return ()
        try:
            if self._path.is_symlink():
                raise SkillProposalError("Öneri dosyası sembolik bağ olamaz.")
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if payload["schema_version"] not in {1, PROPOSAL_SCHEMA_VERSION}:
                raise SkillProposalError("Öneri dosyasının şema sürümü desteklenmiyor.")
            return tuple(_decode(item) for item in payload["proposals"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise SkillProposalError(
                "Öneri dosyası okunamadı; kayıt biçimini kontrol et."
            ) from error


def _json_value(value: object) -> str:
    if isinstance(value, FailureOrigin):
        return value.value
    raise TypeError("Öneri alanının JSON türü desteklenmiyor.")


def _decode(raw: dict[str, object]) -> SkillProposal:
    """Diskteki referansları tekrar doğrula; başarısız koşum eşiğe sızamaz."""
    routine_raw = raw["routine"]
    observations_raw = raw["observations"]
    if not isinstance(routine_raw, dict) or not isinstance(observations_raw, list):
        raise ValueError("Öneri kaydı geçersiz.")
    digest = routine_raw.get("source_digest", "")
    if not isinstance(digest, str):
        raise ValueError("Rutin kaynak özeti metin olmalı.")
    routine = _normalized(
        RoutineSpec(
            routine_id=str(routine_raw["routine_id"]),
            description=str(routine_raw["description"]),
            input_schema=str(routine_raw["input_schema"]),
            preconditions=_string_list(routine_raw["preconditions"]),
            checks=_string_list(routine_raw["checks"]),
            source_digest=digest,
        )
    )
    split = str(raw["source_split"])
    observations: tuple[RoutineObservation, ...] = ()
    for observation_raw in observations_raw:
        observation = _decode_observation(observation_raw)
        if (
            not SkillProposalStore._is_verified(observation)
            or observation.source_split != split
            or not _is_new_proof(observations, observation)
        ):
            raise ValueError("Önerinin bağımsız koşum veya kanıt kaydı geçersiz.")
        observations = (*observations, observation)
    if str(raw["id"]) != _proposal_id(routine, split):
        raise ValueError("Önerinin kanıt kimliği geçersiz.")
    return SkillProposal(str(raw["id"]), routine, split, observations)


def _decode_observation(raw: dict[str, object]) -> RoutineObservation:
    run_id = raw["run_id"]
    if not isinstance(run_id, str):
        raise ValueError("Koşum kimliği metin olmalı.")
    return _canonical_observation(
        RoutineObservation(
            run_id=run_id,
            success=raw["success"] is True,
            verified=raw["verified"] is True,
            evidence_refs=_string_list(raw["evidence_refs"]),
            source_split=str(raw["source_split"]),
            failure_origin=FailureOrigin(str(raw["failure_origin"])),
        )
    )


def _string_list(raw: object) -> tuple[str, ...]:
    """Kalıcı JSON sınırında koleksiyonu ve eleman türünü birlikte doğrula."""
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ValueError("Rutin alanı metin listesi olmalı.")
    return tuple(raw)


def _canonical_observation(observation: RoutineObservation) -> RoutineObservation:
    """Okuma ve yazmada aynı koşum/kanıt kimliklerini karşılaştır."""
    return replace(
        observation,
        run_id=observation.run_id.strip(),
        evidence_refs=tuple(dict.fromkeys(ref.strip() for ref in observation.evidence_refs)),
    )


def _is_new_proof(
    observations: tuple[RoutineObservation, ...],
    observation: RoutineObservation,
) -> bool:
    """Her satır yeni normalize koşum ve en az bir yeni kanıt taşımalı."""
    known_runs = {item.run_id for item in observations}
    known_evidence = {ref for item in observations for ref in item.evidence_refs}
    return observation.run_id not in known_runs and bool(
        set(observation.evidence_refs) - known_evidence
    )
