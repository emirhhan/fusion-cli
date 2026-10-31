"""`/init` görevi ve `/doctor prompt` talimat denetimi (P-021).

Claude Code `/init` depo yapısını, build/test komutlarını ve kuralları inceleyip CLAUDE.md
üretir; `/doctor prompt-audit` talimat kalitesini denetler. Fusion'da:

- `init_task(root, …)` modele verilecek görevi, depodan ÖLÇÜLEN olgularla (proje türü,
  keşfedilen doğrulama komutları, var olan talimat dosyaları) kurar; dosyayı model yazar,
  mevcut dosyanın üzerine sormadan yazmaz.
- `audit_instructions(root, home)` yüklenen katmanları, toplam/kırpılan karakteri, kök dışı
  import notlarını ve izin/onay kurallarını değiştirmeye çalışan satırları raporlar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .instruction_layers import (
    MAX_FILE_CHARS,
    TOTAL_MAX_CHARS,
    InstructionFile,
    load_instruction_layers,
    read_text_limited,
)
from .instruction_rules import discover_rules

#: `/init` ile üretilecek dosya adı, biçime göre (Claude Code → CLAUDE.md, Codex → AGENTS.md).
INIT_TARGETS: dict[str, str] = {"agents": "AGENTS.md", "claude": "CLAUDE.md"}
DEFAULT_INIT_FORMAT = "agents"

#: Toplam bütçenin bu payı dolunca "kısalt" önerisi (kırpma başlamadan uyarı).
BUDGET_WARN_RATIO = 0.7

#: Depo talimatında izin/onay/gizlilik kurallarını değiştirmeye çalışan kalıplar. Bu satırlar
#: Fusion'da etkisizdir (güvenilmez etiket), ama kullanıcı görsün: başkasının deposundan
#: gelen bir dosya bunu deniyorsa haberi olmalı. Yalnız KURAL DEĞİŞTİRME kalıpları: `secret`,
#: `token`, `şifre` gibi genel sözcükler "sırları commit etme" satırlarını işaretleyip uyarı
#: yorgunluğu yaratıyordu (ölçüldü 31 Ekim). Sır SIZDIRMA denemesi ayrı kalıpla yakalanır.
_SUSPICIOUS = re.compile(
    r"onay(sız| sorma| isteme| bekleme)|izin (sorma|isteme)|sormadan (yap|çalıştır|sil)"
    r"|bypass|skip (the )?(permission|approval|confirmation)s?|without (asking|confirmation)"
    r"|ignore (all |any |the )?(previous|prior|safety|security|system) (rules|instructions)"
    r"|disable (safety|security|sandbox)|dangerously|--no-verify|rm -rf /|sudo "
    r"|(print|echo|cat|göster|yazdır|gönder|paylaş)\S*\s+[^\n]{0,40}"
    r"(api[_ -]?key|secret|token|şifre|parola|credential|\.env\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SuspiciousLine:
    source: str
    line_no: int
    text: str


@dataclass(frozen=True, slots=True)
class InstructionAudit:
    """`/doctor prompt` raporunun verisi."""

    files: tuple[InstructionFile, ...]
    rules: int
    total_chars: int
    trimmed_chars: int
    budget: int
    notes: tuple[str, ...]
    suspicious: tuple[SuspiciousLine, ...]
    suggestions: tuple[str, ...]


def audit_instructions(
    root: Path,
    home: Path | None,
    *,
    merge: bool = True,
    max_chars: int = TOTAL_MAX_CHARS,
) -> InstructionAudit:
    """Tur başında bağlama girecek talimatları ölç ve öneri üret; dosya yazmaz."""
    load = load_instruction_layers(root, home, merge=merge, max_chars=max_chars)
    rules = discover_rules(root, home) if merge else ()
    total = sum(item.chars for item in load.files)
    suspicious = tuple(_scan_suspicious(item) for item in load.files if not item.trusted)
    flat = tuple(line for group in suspicious for line in group)
    suggestions: list[str] = []
    project_files = [item for item in load.files if item.layer == "proje"]
    if not project_files:
        suggestions.append(
            "Proje talimat dosyası yok: `/init` ile AGENTS.md (ya da `/init claude` ile "
            "CLAUDE.md) oluştur."
        )
    if load.trimmed_chars:
        suggestions.append(
            f"{load.trimmed_chars} karakter kırpıldı: uzun bölümleri ayrı dosyalara taşıyıp "
            "`@docs/kurallar.md` ile içe aktar; dosya başına sınır "
            f"{MAX_FILE_CHARS} karakter."
        )
    elif total > max_chars * BUDGET_WARN_RATIO:
        suggestions.append(
            f"Talimatlar bütçenin %{int(100 * total / max_chars)}'ini kullanıyor "
            f"({total}/{max_chars}); kısaltmak modelin göreve ayıracağı payı artırır."
        )
    if flat:
        suggestions.append(
            "Depo talimatında izin/onay/sır kurallarına dokunan satırlar var; Fusion bunları "
            "uygulamaz ama dosyanın kaynağını gözden geçir."
        )
    if project_files and not _mentions_verification(root, project_files):
        suggestions.append(
            "Talimat test/doğrulama komutunu söylemiyor; `## Doğrulama` bölümüne "
            "`pytest`/`npm test` gibi komutu yaz (ya da /verify ile keşfet)."
        )
    return InstructionAudit(
        files=load.files,
        rules=len(rules),
        total_chars=total,
        trimmed_chars=load.trimmed_chars,
        budget=max_chars,
        notes=load.notes,
        suspicious=flat,
        suggestions=tuple(suggestions),
    )


def _scan_suspicious(item: InstructionFile) -> tuple[SuspiciousLine, ...]:
    try:
        text = read_text_limited(item.path, MAX_FILE_CHARS)
    except OSError:
        return ()
    found: list[SuspiciousLine] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _SUSPICIOUS.search(line):
            found.append(SuspiciousLine(item.label, number, line.strip()[:160]))
    return tuple(found)


_VERIFY_WORDS = re.compile(
    r"pytest|npm (run )?test|vitest|cargo test|go test|make test|\btests?\b", re.I
)


def _mentions_verification(root: Path, files: list[InstructionFile]) -> bool:
    for item in files:
        try:
            if _VERIFY_WORDS.search(read_text_limited(item.path, MAX_FILE_CHARS)):
                return True
        except OSError:
            continue
    return False


def render_audit(audit: InstructionAudit) -> str:
    """`/doctor prompt` çıktısı: yüklenenler, ölçüm, şüpheli satırlar, öneriler."""
    lines = [
        f"Talimat denetimi: {len(audit.files)} dosya, {audit.rules} kural dosyası, "
        f"{audit.total_chars}/{audit.budget} karakter"
        + (f", {audit.trimmed_chars} kırpıldı" if audit.trimmed_chars else "")
        + "."
    ]
    for item in audit.files:
        etiket = "güvenilir" if item.trusted else "depo içeriği"
        ek = f", {item.trimmed} kırpıldı" if item.trimmed else ""
        lines.append(f"  · {item.label} [{item.layer}, {etiket}] {item.chars} karakter{ek}")
    for note in audit.notes:
        lines.append(f"  ! {note}")
    if audit.suspicious:
        lines.append("Şüpheli satırlar (Fusion bunları uygulamaz):")
        lines.extend(f"  ! {s.source}:{s.line_no}  {s.text}" for s in audit.suspicious[:12])
    if audit.suggestions:
        lines.append("Öneriler:")
        lines.extend(f"  → {s}" for s in audit.suggestions)
    else:
        lines.append("Öneri yok; talimat katmanı sağlıklı.")
    return "\n".join(lines)


def init_task(root: Path, home: Path | None = None, *, fmt: str = DEFAULT_INIT_FORMAT) -> str:
    """`/init [agents|claude]` — modele verilecek görev; depodan ölçülen olgularla.

    Bilinmeyen biçim `agents` sayılır. Dosya varsa model üzerine yazmaz: eksik bölümleri
    önerir ve `ask_user` ile sorar.
    """
    from .verify_discovery import discover_commands, project_kinds

    target = INIT_TARGETS.get(fmt.strip().lower(), INIT_TARGETS[DEFAULT_INIT_FORMAT])
    kinds = ", ".join(project_kinds(root)) or "bilinmiyor"
    commands = ", ".join(f"`{c}`" for c in discover_commands(root)) or "keşfedilemedi"
    existing = [
        item.label for item in load_instruction_layers(root, home).files if item.layer == "proje"
    ]
    mevcut = ", ".join(existing) if existing else "yok"
    return (
        f"Bu proje için kök talimat dosyası hazırla: `{target}` (Claude Code /init gibi). "
        "Önce depoyu incele: depo haritası ve paket dosyaları (pyproject.toml, package.json, "
        "Cargo.toml, go.mod, project.godot…), README, mevcut kural dosyaları ve CI yapılandırması. "
        f"Fusion'ın ölçtükleri: proje türü: {kinds}; doğrulama komutları: {commands}; "
        f"mevcut talimat dosyaları: {mevcut}.\n"
        "Dosyayı şu bölümlerle yaz (kısa, somut, bu depoya özgü; genel öğüt yazma): "
        "`## Proje` (ne yapar, ana dizinler), `## Kurulum ve çalıştırma`, `## Doğrulama` "
        "(lint/tip/test komutları birebir), `## Kod kuralları` (stil, isimlendirme, dil, "
        "test beklentisi), `## Dikkat` (dokunulmaması gereken dosyalar, sırlar, üretim yolları). "
        "Toplam 3.000 karakteri geçme; uzun kuralları ayrı dosyaya koyup `@docs/...md` ile içe "
        "aktar.\n"
        f"`{target}` ZATEN VARSA üzerine yazma: eksik bölümleri listele ve `ask_user` ile "
        "ekleyip eklemeyeceğini sor. Başka bir talimat dosyası varsa (ör. CLAUDE.md ↔ "
        "AGENTS.md) aynı içeriği iki kez yazma; birini diğerine `@` ile bağla. Bitince dosyayı "
        "özetle ve `/doctor prompt` ile denetlenebileceğini söyle."
    )
