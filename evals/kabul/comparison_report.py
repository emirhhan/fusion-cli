"""Public sidecar'ı yalnız beklenen typed kanıtla eşleşirse rapora taşı.

Unknown durumları kozmetik PASS'a çevirmek, ham yeni alan/log export etmek yok.
Bu receipt import/config gözlemini taşır; ürün kalite ve %90 kanıtı değildir.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from evals.kabul.engine_options import ComparisonValidity

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_INVALID_REASON = "Karşılaştırma sidecar kanıtı eksik/geçersiz; eş koşullar bilinmiyor."
_REASONS = {
    "Motor import kanıtı doğrulanmadı.",
    "Efektif ayar kanıtı eksik/geçersiz.",
}


def _validate_payload(payload: object, expected: ComparisonValidity) -> None:
    if not isinstance(payload, dict) or set(payload) != set(asdict(expected)):
        raise ValueError("Karşılaştırma kanıt şeması geçersiz.")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("Karşılaştırma kanıt sürümü geçersiz.")
    for name in (
        "import_verified",
        "config_verified",
        "equal_conditions_verified",
        "selected_model_preflight_verified",
    ):
        if type(payload[name]) is not bool:
            raise ValueError("Kanıt bayrağı bool olmalı.")
    if payload["equal_conditions_verified"] or payload["selected_model_preflight_verified"]:
        raise ValueError("Eş koşul veya önkontrol kanıtı bu receipt ile doğrulanamaz.")
    for name in ("authentication_status", "cache_initial_state", "dynamic_context_status"):
        if payload[name] != "unknown":
            raise ValueError("Kanıtlanmamış durum unknown kalmalı.")
    if payload["revision_provenance"] != "unverified":
        raise ValueError("Kaynak revizyon kökeni doğrulanmadı.")
    pid = payload["engine_pid"]
    if pid is not None and (type(pid) is not int or pid <= 0):
        raise ValueError("Motor süreç kimliği geçersiz.")
    digest = payload["source_digest"]
    if digest is not None and (not isinstance(digest, str) or not _DIGEST.fullmatch(digest)):
        raise ValueError("Motor kaynak özeti geçersiz.")
    digests = payload["config_digests"]
    if not isinstance(digests, list) or any(
        not isinstance(item, str) or not _DIGEST.fullmatch(item) for item in digests
    ):
        raise ValueError("Efektif config özetleri geçersiz.")
    reasons = payload["reasons"]
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) or reason not in _REASONS for reason in reasons
    ):
        raise ValueError("Kanıt nedeni public allowlist dışında.")
    canonical = json.loads(json.dumps(asdict(expected)))
    if payload != canonical:
        raise ValueError("Sidecar beklenen süreç/kaynak/ayar kanıtıyla eşleşmiyor.")


def read_comparison_metadata(workdir: Path, expected: ComparisonValidity) -> ComparisonValidity:
    """Sabit sidecar yolu; symlink/raw alanlar fail-closed ve sır içermeyen sonuç."""
    path = workdir / "comparison-proof.json"
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Sidecar normal dosya değil.")
        _validate_payload(json.loads(path.read_text(encoding="utf-8")), expected)
    except (OSError, ValueError, UnicodeError):
        return ComparisonValidity(reasons=(_INVALID_REASON,))
    return expected
