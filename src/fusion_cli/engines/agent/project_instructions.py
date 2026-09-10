"""Hedef projenin KENDİ talimat dosyasını oku — OpenCode'un `AGENTS.md` katmanı.

Fusion'ın kendi RULES.md/CLAUDE.md'si nasıl fusion'ı yönlendiriyorsa, agent'ın
üzerinde çalıştığı HEDEF proje de kendi kuralını (CLAUDE.md, AGENTS.md, .cursorrules…)
tanımlamış olabilir. Model bunu kendi kararıyla `read_file` ile bulabilir ama bu
şansa bırakılmış bir davranıştır — OpenCode bu katmanı sistem promptuna GARANTİLİ
ekler (docs/PROMPT_ARCHITECTURE.md'de araştırılan "Custom Instructions" katmanı).
Bu modül aynı garantiyi verir: dosya varsa okunur, yoksa sessizce atlanır.

Talimat dosyasının İŞARET ETTİĞİ kural dosyaları da bir seviye izlenir. Sebep
ölçüldü: bu deponun CLAUDE.md'si "kod yazmadan önce RULES.md okunur" der ve asıl
mimari/isimlendirme/katman kuralları orada durur — ama RULES.md prompta hiç
girmiyordu, yalnız ona giden işaret giriyordu. Garanti edilen katman, garanti
edilmeyen bir okuma turuna bağlanmış oluyordu.

Yalnızca proje KÖKÜNE bakılır (workspace_hint.py'deki "sığ tarama" ilkesiyle aynı):
derin arama turu bekletirdi ve çoğu proje kuralını kökte tutar.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
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

#: İşaret edilen kural dosyalarının TOPLAM bütçesi. Ayrı tutulur ki ana talimat
#: dosyası kendi bütçesini kaybetmesin.
MAX_LINKED_CHARS = 4_000

#: En fazla kaç kural dosyası izlenir. Talimat dosyaları çoğu kez onlarca bağlantı
#: taşır (rozetler, dış dokümanlar); hepsini okumak bütçeyi gürültüye harcardı.
MAX_LINKED_FILES = 3

#: İzlenebilir uzantılar. Talimat dosyası GÜVENİLMEZ girdidir: `.env`, anahtar
#: dosyası ya da ikili bir şeyi prompta gömmek sır sızdırır. Yalnız düz metin
#: kural biçimleri okunur.
LINKABLE_SUFFIXES: frozenset[str] = frozenset({".md", ".mdc", ".markdown", ".txt", ".rst"})

#: Markdown bağlantısı: [metin](hedef). Hedefteki başlık/çapa parçası atılır.
_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)")


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
        bloklar = [f'<proje_talimati kaynak="{filename}">\n{content}{ek}\n</proje_talimati>']
        bloklar.extend(_linked_rules(root, content, skip=path))
        return "\n".join(bloklar)
    return ""


def _linked_rules(root: Path, content: str, *, skip: Path) -> list[str]:
    """Talimat metninin işaret ettiği kural dosyalarını oku.

    Talimat dosyası çoğu kez asıl kuralı KENDİSİ taşımaz, işaret eder: bu deponun
    CLAUDE.md'si "kod yazmadan önce RULES.md okunur" der ve mimari, isimlendirme,
    katman kuralları orada durur. İşaret edilen dosya prompta hiç girmezse kural
    katmanı modelin kendi kararına kalır — modülün var oluş sebebi ise tam olarak
    bu şansı ortadan kaldırmaktır.

    Yalnız BİR seviye izlenir: derin zincir bağlam bütçesini sessizce tüketirdi.

    Talimat dosyası güvenilmez girdidir; her hedef üç kapıdan geçer: kök içinde
    kalmalı, izinli bir metin uzantısı taşımalı ve gerçek bir dosya olmalı. URL ve
    mutlak yol hiç denenmez.
    """
    kalan = MAX_LINKED_CHARS
    okunan: list[str] = []
    gorulen: set[Path] = {skip.resolve()}
    for hedef in _LINK_PATTERN.findall(content):
        if len(okunan) >= MAX_LINKED_FILES or kalan <= 0:
            break
        yol = _resolve_rule_path(root, hedef)
        if yol is None or yol in gorulen:
            continue
        gorulen.add(yol)
        try:
            metin = yol.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue
        if not metin:
            continue
        kirpildi = len(metin) > kalan
        metin = metin[:kalan]
        kalan -= len(metin)
        ad = yol.relative_to(root.resolve()).as_posix()
        ek = "\n[…kırpıldı, dosyanın tamamı için read_file kullan…]" if kirpildi else ""
        okunan.append(f'<proje_kurali kaynak="{ad}">\n{metin}{ek}\n</proje_kurali>')
    return okunan


def _resolve_rule_path(root: Path, target: str) -> Path | None:
    """Bağlantı hedefini kök içindeki gerçek bir kural dosyasına çöz; olmazsa `None`."""
    hedef = target.split("#", 1)[0].strip()
    if not hedef or "://" in hedef or hedef.startswith(("/", "#", "mailto:")):
        return None
    kok = root.resolve()
    try:
        yol = (kok / hedef).resolve()
    except (OSError, ValueError):
        return None
    # `resolve()` sembolik bağı da açar: `..` ya da bir symlink kökün dışına
    # çıkıyorsa dosya HİÇ açılmaz.
    if not yol.is_relative_to(kok):
        return None
    if yol.suffix.lower() not in LINKABLE_SUFFIXES or not yol.is_file():
        return None
    return yol


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
    ortam = (
        "ORTAM (Fusion tarafından ölçüldü):\n"
        + json.dumps(
            {
                "cwd": str(root.resolve()),
                "os": platform.system(),
                "arch": platform.machine(),
                "executables": {
                    name: path
                    for name in ("git", "python3", "node", "npm", "godot")
                    if (path := shutil.which(name))
                },
            },
            ensure_ascii=False,
        )
        + "\nDosya yollarını bu çalışma köküne göreli yaz; başka bir kök veya işletim "
        "sistemi varsayma. Listelenen çalıştırılabilir dosyalar PATH üzerinde bulundu; "
        "sürümleri henüz doğrulanmadı. Yeni kurulumdan önce mevcut aracı denetle."
    )
    ozet = workspace_summary(root)
    proje_talimati = read_project_instructions(root)
    if home is None:
        return "\n".join(part for part in (ortam, ozet, proje_talimati) if part)

    from ...history.memory_files import read_external_memory

    dis_bellek = read_external_memory(home, root)
    parts = [ortam, ozet, proje_talimati, dis_bellek]
    return "\n".join(part for part in parts if part)
