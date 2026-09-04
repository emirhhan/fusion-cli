"""Hedef projenin KENDİ talimat dosyasını oku — OpenCode'un `AGENTS.md` katmanı.

Fusion'ın kendi RULES.md/CLAUDE.md'si nasıl fusion'ı yönlendiriyorsa, agent'ın
üzerinde çalıştığı HEDEF proje de kendi kuralını (CLAUDE.md, AGENTS.md, .cursorrules…)
tanımlamış olabilir. Model bunu kendi kararıyla `read_file` ile bulabilir ama bu
şansa bırakılmış bir davranıştır — OpenCode bu katmanı sistem promptuna GARANTİLİ
ekler (docs/PROMPT_ARCHITECTURE.md'de araştırılan "Custom Instructions" katmanı).
Bu modül aynı garantiyi verir: dosya varsa okunur, yoksa sessizce atlanır.

Yalnızca proje KÖKÜNE bakılır (workspace_hint.py'deki "sığ tarama" ilkesiyle aynı):
derin arama turu bekletirdi ve çoğu proje kuralını kökte tutar.
"""

from __future__ import annotations

from pathlib import Path

#: Bilinen proje-talimat dosyası adları, öncelik sırasıyla. İlk bulunan kullanılır;
#: birden fazlası varsa aynı bilgiyi iki kez göndermek gürültüdür.
CANDIDATE_FILENAMES: tuple[str, ...] = (
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    ".cursorrules",
)

#: Okunacak en fazla karakter. Bazı talimat dosyaları (ör. bu projenin RULES.md'si)
#: uzun olabilir; sınırsız okuma bağlam bütçesini tek dosyaya harcardı.
MAX_CHARS = 8_000


def read_project_instructions(root: Path) -> str:
    """Proje kökündeki ilk bilinen talimat dosyasını okuyup etiketli metin döndür.

    Dosya yoksa ya da okunamıyorsa boş dizge döner — bu bir hata değildir, çoğu
    projenin böyle bir dosyası yoktur.
    """
    for filename in CANDIDATE_FILENAMES:
        path = root / filename
        try:
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content:
            continue
        kirpildi = len(content) > MAX_CHARS
        if kirpildi:
            content = content[:MAX_CHARS]
        ek = "\n[…kırpıldı, dosyanın tamamı için read_file kullan…]" if kirpildi else ""
        return f'<proje_talimati kaynak="{filename}">\n{content}{ek}\n</proje_talimati>'
    return ""


#: Proje türünü belli eden işaret dosyaları — modele KANIT olarak gösterilir.
_KIND_EVIDENCE: dict[str, str] = {
    "godot": "project.godot",
    "python": "pyproject.toml",
    "node": "package.json",
    "rust": "Cargo.toml",
    "go": "go.mod",
}


def workspace_summary(root: Path) -> str:
    """Çalışma alanının TÜRÜNÜ modele bildir.

    Ölçüldü: içinde `project.godot` olan bir klasörde "2D platform oyunu yap"
    denince model HTML/JS oyunu yazdı. Klasör açıkça bir Godot projesiydi ve
    Fusion bunu zaten hesaplıyordu (`project_kinds`, ders etiketleri için), ama
    modele hiç söylemiyordu — model `list_dir` ile tahmin etmek zorunda kaldı ve
    yanlış yığınla yeni bir proje kurdu.

    Tanınmayan dizinde BOŞ döner: uydurma bir tanı, modeli yanlış yığına iter.
    """
    from .verify_discovery import project_kinds

    kinds = project_kinds(root)
    if not kinds:
        return ""
    kanit = ", ".join(f"{ad} ({_KIND_EVIDENCE[ad]})" for ad in kinds if ad in _KIND_EVIDENCE)
    return (
        f"ÇALIŞMA ALANI: bu dizin bir {kanit} projesidir. Görev bu projeye aittir; "
        "işi projenin kendi araç ve biçimleriyle yap, başka bir teknolojiyle "
        "yandan yeni bir proje kurma."
    )


def read_all_instructions(root: Path, home: Path | None) -> str:
    """Proje talimatı ve dış araç belleklerini birlikte döndür.

    Sıra bilinçlidir: proje talimatı önce gelir, çünkü çakışma halinde projenin
    kendi kuralı kullanıcının genel belleğini yener.

    `home` verilmezse (ör. testte ya da ev dizini bilinmiyorsa) dış bellek hiç
    okunmaz — bu, `AgentDeps` alanlarının "yoksa o yetenek hiç sunulmaz" deseniyle
    tutarlıdır.
    """
    # Çalışma alanı özeti EN BAŞTA: model neyin içinde olduğunu bilmeden doğru
    # aracı seçemez ve yanlış yığınla yandan yeni bir proje kurar (ölçüldü).
    ozet = workspace_summary(root)
    proje_talimati = read_project_instructions(root)
    if home is None:
        return "\n".join(part for part in (ozet, proje_talimati) if part)

    from ...history.memory_files import read_external_memory

    dis_bellek = read_external_memory(home, root)
    parts = [ozet, proje_talimati, dis_bellek]
    return "\n".join(part for part in parts if part)
