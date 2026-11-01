"""Masaüstü `izin.*` ve `proje.guven_*` istekleri (P-003, P-012).

    izin.kurallar        tüm katmanlardaki kurallar + engeller + hedef dosya
    izin.ekle            {kalip, karar, kapsam: "proje"|"kullanici"}  (proje: güvenilmiyorsa hata)
    izin.sil             {kalip, karar, dosya?}  (dosya: tablodaki satırın dosyası)
    izin.engel           {anahtar: block_reads_outside_root|block_writes_outside_root, deger: bool}
    proje.guven_durum    TrustReport: güvenildi mi, neden, düşürülen bölümler
    proje.guven_ver      fusion trust eşdeğeri
    proje.guven_kaldir   güven kaydını siler

İşlevler saf: oturum nesnesi yalnız kök ve yapılandırmayı geçirir, sonucu alır.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import permission_admin, trust
from ..config.hooks import untrusted_hook_files
from ..config.models import Config
from ..core.errors import ConfigError
from ..ui import messages


def list_rules(root: Path, config: Config) -> dict[str, Any]:
    return permission_admin.rules_payload(root, config)


def add_rule(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    try:
        decision = permission_admin.parse_decision(data.get("karar"))
    except ValueError:
        return {
            "ok": False,
            "metin": messages.PERMISSIONS_BAD_DECISION.format(given=data.get("karar")),
        }
    try:
        rule = permission_admin.parse_pattern(data.get("kalip"), decision)
    except ValueError:
        return {
            "ok": False,
            "metin": messages.PERMISSIONS_BAD_PATTERN.format(given=data.get("kalip")),
        }
    try:
        # Masaüstünde kapsam AÇIKÇA seçilir: "Bu proje" güvenilmeyen projede sessizce
        # kullanıcı dosyasına düşmez, hata döner (P-003).
        change = permission_admin.add_permission_rule(
            root,
            rule,
            user_level=data.get("kapsam") == "kullanici",
            strict_project=data.get("kapsam") == "proje",
            # Claude'un paylaşılan proje kapsamı: `.claude/settings.json` (#83).
            project_shared=data.get("kapsam") == "paylasilan",
        )
    except ConfigError as error:
        return {"ok": False, "metin": str(error)}
    if not change.changed:
        return {
            "ok": False,
            "metin": messages.PERMISSIONS_EXISTS.format(
                rule=change.pattern, decision=decision.value
            ),
        }
    return {
        "ok": True,
        "metin": messages.PERMISSIONS_ADDED.format(
            rule=change.pattern, decision=decision.value, path=change.path
        ),
        "dosya": str(change.path),
    }


def remove_rule(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    try:
        decision = permission_admin.parse_decision(data.get("karar"))
        rule = permission_admin.parse_pattern(data.get("kalip"), decision)
    except ValueError:
        return {"ok": False, "metin": messages.PERMISSIONS_USAGE}
    dosya = data.get("dosya")
    try:
        removed = permission_admin.remove_permission_rule(
            root, rule, path=Path(dosya) if isinstance(dosya, str) and dosya else None
        )
    except ConfigError as error:
        return {"ok": False, "metin": str(error)}
    if removed is None:
        return {
            "ok": False,
            "metin": messages.PERMISSIONS_NOT_FOUND.format(
                rule=rule.pattern, decision=decision.value
            ),
        }
    return {"ok": True, "dosya": str(removed.path)}


def set_block(config: Config, data: dict[str, Any]) -> tuple[Config | None, dict[str, Any]]:
    """Kök-dışı engel anahtarını yaz; başarılıysa güncel yapılandırmayı da döndür."""
    key = str(data.get("anahtar", ""))
    value = data.get("deger")
    if key not in permission_admin.OUTSIDE_ROOT_FLAGS or not isinstance(value, bool):
        return None, {"ok": False, "metin": "Engel anahtarı ya da değeri geçersiz."}
    try:
        updated = permission_admin.set_outside_root_flag(config, key, value)
    except ConfigError as error:
        return None, {"ok": False, "metin": str(error)}
    return updated, {"ok": True, "anahtar": key, "deger": value}


def trust_status(root: Path) -> dict[str, Any]:
    report = trust.trust_report(root)
    return {
        "ok": True,
        "guvenildi": report.state.trusted,
        "neden": report.state.reason,
        "dusurulen_bolumler": list(report.dropped_sections),
        "yok_sayilan_dosyalar": list(report.ignored_files),
        "yuklenmeyen_araclar": report.forged_tools,
        # Güven bu dosyaların kanca komutlarını da açar (P-009); şerit bunu söyler.
        "kanca_dosyalari": list(untrusted_hook_files(root)),
        "kok": str(root),
    }


def trust_grant(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        return {"ok": False, "metin": f"Dizin bulunamadı: {root}"}
    try:
        trust.trust_project(root)
    except ConfigError as error:
        return {"ok": False, "metin": str(error)}
    return trust_status(root)


def trust_revoke(root: Path) -> dict[str, Any]:
    try:
        trust.untrust_project(root)
    except ConfigError as error:
        return {"ok": False, "metin": str(error)}
    return trust_status(root)
