"""Klasör güveni — Claude Code ile birebir (#67, #71).

Kaynak: code.claude.com/docs/en/permissions#project-allow-rules-and-workspace-trust ;
#when-your-local-settings-file-needs-trust.

    Anahtar        depoda git kökü (alt dizinler dahil, iç içe depo hariç); depo dışında
                   başlatılan dizin ve alt dizinleri
    İçerik         güven klasör başına bir kez verilir; `.claude/settings.json` ya da
                   `settings.local.json` değişince DÜŞMEZ (eski karma eşleşmesi kalktı)
    Ev dizini      `settings.local.json` ev dizininde güven adımı olmadan uygulanır
    Yerel dosya    öteki her yerde klasöre (ya da kapsayan üst klasöre) güven verilene dek
                   allow kuralları bekletilir; deny/ask her zaman okunur
"""

from __future__ import annotations

from pathlib import Path

#: Güven kaydında "hiç güvenilmedi" işareti (`trust._NEVER_TRUSTED` ile aynı).
_NEVER_TRUSTED = ""


def is_folder_trusted(root: Path) -> bool:
    """Klasöre (depoda git köküne, depo dışında kendisine ya da bir üst dizine) güvenildi mi?"""
    from . import trust

    store = trust._load()
    return any(
        (record := store.get(trust._key(candidate))) is not None
        and record.get("config_sha256") != _NEVER_TRUSTED
        for candidate in trust_candidates(root)
    )


def trust_candidates(root: Path) -> tuple[Path, ...]:
    """Güveni bu klasöre taşıyabilecek kayıt anahtarları."""
    current = root.resolve()
    repo = git_root(current)
    if repo is not None:
        # Üst klasör güveni iç içe depoya (klon, alt modül) uzanmaz.
        return tuple(dict.fromkeys((current, repo)))
    home = Path.home().resolve()
    return tuple(p for p in (current, *current.parents) if p != home and p != Path(p.anchor))


def is_config_home(root: Path) -> bool:
    """Ev dizini mi? (Oradaki `settings.local.json` güven adımı istemez.)"""
    try:
        return root.resolve() == Path.home().resolve()
    except (OSError, RuntimeError):
        return False


def git_root(root: Path) -> Path | None:
    """Klasörü kapsayan git deposunun kökü; depo değilse `None`."""
    for candidate in (root, *root.parents):
        if (candidate / ".git").exists():
            return candidate
    return None
