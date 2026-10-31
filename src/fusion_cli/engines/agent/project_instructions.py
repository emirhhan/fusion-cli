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

Kök talimatı tur başında yüklenir (workspace_hint.py'deki "sığ tarama" ilkesiyle aynı:
derin arama turu bekletirdi). Alt klasörlerin kendi talimatı ise model o klasördeki bir
dosyaya ERİŞİNCE yüklenir (`load_nested_instructions`; Claude Code'un iç içe CLAUDE.md
davranışı): klasör ve üst klasörleri (kök hariç) bir kez, dosya başına kısaltılmış olarak.
Güven politikası köktekiyle aynıdır — içerik her zaman "güvenilmez depo içeriği" etiketiyle
gelir, kök dışına çıkılmaz, bağlantılı kural dosyaları izlenmez.
"""

from __future__ import annotations

import json
import platform
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ...core.errors import PathAccessError
from ...core.types import Message
from ...tools.files import resolve_path
from ...tools.safe_delete import is_container_root, project_folders
from ...tools.wordpress_setup import tool_path
from .instruction_layers import (
    MAX_FILE_CHARS,
    MAX_LINKED_CHARS,
    TOTAL_MAX_CHARS,
    UNTRUSTED_NOTE,
    load_instruction_layers,
    neutralize,
    read_text_limited,
)
from .instruction_rules import (
    MAX_RULE_FILE_CHARS,
    RuleFile,
    discover_rules,
    rule_block,
    scoped_rules_for,
    unscoped_rules_block,
)

#: Tek dosya erişiminde eklenen `paths:` kapsamlı kuralların TOPLAM bütçesi (karakter).
SCOPED_RULES_MAX_CHARS = 8_000

#: Tek dosya erişiminde eklenen en fazla kapsamlı kural sayısı.
SCOPED_RULES_MAX_FILES = 6

#: Kalan kural bütçesi bunun altındaysa kural kırpıntı olarak değil hiç eklenmez (sonraya kalır).
SCOPED_RULES_MIN_CHARS = 200

__all__ = ["MAX_CHARS", "MAX_LINKED_CHARS", "read_all_instructions", "read_project_instructions"]

#: Bilinen proje-talimat dosyası adları, öncelik sırasıyla. İç içe klasörlerde dizin
#: başına TEK dosya alınır; kök için katmanlı okuma `instruction_layers` içindedir.
CANDIDATE_FILENAMES: tuple[str, ...] = (
    "CLAUDE.md",
    "AGENTS.md",
    "GEMINI.md",
    ".cursorrules",
)

#: Dosya başına okunacak en fazla karakter (geri uyumlu ad; bkz. `instruction_layers`).
MAX_CHARS = MAX_FILE_CHARS

#: Talimat/kural bloklarının başındaki güvenilmezlik uyarısı (A3-31).
_UNTRUSTED_NOTE = UNTRUSTED_NOTE

_neutralize = neutralize
_read_text_limited = read_text_limited


def read_project_instructions(
    root: Path,
    home: Path | None = None,
    *,
    merge: bool = True,
    max_chars: int = TOTAL_MAX_CHARS,
) -> str:
    """Proje (ve verilmişse kullanıcı) katmanlarını okuyup etiketli metin döndür.

    Dosya yoksa ya da okunamıyorsa boş dizge döner — bu bir hata değildir, çoğu
    projenin böyle bir dosyası yoktur. Ölçüm gerekiyorsa `load_instruction_layers`.
    """
    return load_instruction_layers(root, home, merge=merge, max_chars=max_chars).text


#: İç içe talimat dosyası başına okunacak en fazla karakter (kök için `MAX_CHARS` 8.000).
#: Alt klasör talimatı bağlama TUR ORTASINDA eklenir ve her erişimde yeni klasör
#: getirebilir; kısa tutulur, tamamı için `read_file` önerilir.
NESTED_MAX_CHARS = 3_000

#: Bir turda eklenecek en fazla iç içe talimat dosyası: derin bir ağaçta gezen model
#: bağlamı talimatlarla doldurmasın.
NESTED_MAX_FILES = 8

#: İç içe talimat aranmayan dizin adları: bağımlılık/üretim ağaçları üçüncü tarafın
#: AGENTS.md dosyasını taşıyabilir (enjeksiyon yolu) ve proje kuralı değildir.
_NESTED_SKIP_DIRS = frozenset(
    {"node_modules", "vendor", "site-packages", "dist", "build", "target", "__pycache__"}
)
#: İç içe beceri keşfi de aynı gürültü dizinlerini atlar (`nested_skills`; P-052).
NESTED_SKIP_DIRS = _NESTED_SKIP_DIRS

NESTED_NOTE_HEADER = (
    "FUSION_NOT: Eriştiğin dosyanın klasörü kendi talimatını taşıyor; o klasördeki işlerde "
    "geçerlidir (kök talimatıyla çakışırsa daha yakın olan öncelikli)."
)


@dataclass(frozen=True, slots=True)
class NestedLoad:
    """Bir erişimin getirdiği iç içe talimatlar: bağlama eklenecek mesaj ve ölçüm."""

    message: Message
    files: tuple[str, ...]
    chars: int


def nested_marker(rel: str) -> str:
    """Talimat bloğunun açılış etiketi; bağlamda var mı diye bakmak için de kullanılır."""
    return f'<alt_talimat kaynak="{rel}">'


def _nested_candidates(kok: Path, hedef: Path) -> list[tuple[str, Path]]:
    """Hedef dosyanın klasöründen köke (kök HARİÇ) kadar bulunan talimat dosyaları.

    Dış → iç sıralıdır (üst klasör önce). Her klasörden `CANDIDATE_FILENAMES` önceliğiyle
    TEK dosya alınır. Kök dışına çıkan hedef/sembolik bağ ve gürültü dizinleri atlanır.
    """
    try:
        gercek = hedef.resolve()
    except (OSError, RuntimeError):
        return []
    if not gercek.is_relative_to(kok):
        return []
    klasor = gercek if gercek.is_dir() else gercek.parent
    parcalar = klasor.relative_to(kok).parts
    if any(p in _NESTED_SKIP_DIRS or p.startswith(".") for p in parcalar):
        return []
    bulunan: list[tuple[str, Path]] = []
    for derinlik in range(1, len(parcalar) + 1):
        dizin = kok.joinpath(*parcalar[:derinlik])
        for ad in CANDIDATE_FILENAMES:
            aday = dizin / ad
            try:
                if not aday.is_file():
                    continue
                cozulen = aday.resolve()
            except OSError:
                continue
            # Sembolik bağ kök dışındaki bir dosyaya çıkıyorsa HİÇ açılmaz.
            if cozulen == gercek or not cozulen.is_relative_to(kok):
                continue
            bulunan.append((aday.relative_to(kok).as_posix(), cozulen))
            break
    return bulunan


def load_nested_instructions(
    root: Path,
    target: Path,
    *,
    loaded: set[str],
    present: Callable[[str], bool],
    max_files: int = NESTED_MAX_FILES,
    rules: tuple[RuleFile, ...] = (),
) -> NestedLoad | None:
    """Model `target` dosyasına eriştiğinde bağlama eklenecek iç içe talimatları döndür.

    `loaded` bu turda işlenmiş talimat yollarının kümesidir ve BURADA güncellenir (çağıranın
    durumudur); `present(rel)` o talimatın bağlamda zaten durup durmadığını söyler (önceki
    turdan kalan geçmiş). İkisinden biri "var" derse dosya iki kez eklenmez. Bilinen sınır:
    bağlam sıkıştırması notu düşürürse aynı tur içinde yeniden eklenmez (sonraki turda,
    `present` yanlış dönünce eklenir). Eklenecek bir şey yoksa `None`.

    `rules`: `.claude/rules` kuralları; `paths:` deseni erişilen dosyaya uyanlar aynı mesajda,
    aynı tekilleştirme sözleşmesiyle (etiketleri `loaded`/`present`) eklenir (P-016). Kurallar
    ayrı bütçeyle (`SCOPED_RULES_MAX_CHARS`, `SCOPED_RULES_MAX_FILES`) girer ve `max_files`
    sayacına KATILMAZ: ölçüldü (31 Ekim), 12 kural tek mesaja 50 KB ekliyor ve sayacı
    doldurup sonraki klasörün AGENTS.md'sini engelliyordu. Bütçeye sığmayan kural `loaded`a
    yazılmaz; sonraki erişimde yeni bütçeyle gelir.
    """
    kok = root.resolve()
    bloklar: list[str] = []
    adlar: list[str] = []
    toplam = 0
    rule_labels = {kural.label for kural in rules}
    for rel, yol in _nested_candidates(kok, target):
        if rel in loaded:
            continue
        if present(rel):
            loaded.add(rel)
            continue
        if len(loaded - rule_labels) >= max_files:
            break
        try:
            icerik = _read_text_limited(yol, NESTED_MAX_CHARS)
        except OSError:
            continue
        loaded.add(rel)
        if not icerik:
            continue
        kirpildi = len(icerik) > NESTED_MAX_CHARS
        icerik = _neutralize(icerik[:NESTED_MAX_CHARS])
        ek = "\n[…kırpıldı, dosyanın tamamı için read_file kullan…]" if kirpildi else ""
        bloklar.append(f"{nested_marker(rel)}\n{_UNTRUSTED_NOTE}\n{icerik}{ek}\n</alt_talimat>")
        adlar.append(rel)
        toplam += len(icerik)
    kural_kalan = SCOPED_RULES_MAX_CHARS
    kural_sayisi = 0
    atlanan: list[str] = []
    for kural in _scoped_rules(kok, target, rules):
        if kural.label in loaded:
            continue
        if present(kural.label):
            loaded.add(kural.label)
            continue
        if kural_kalan < SCOPED_RULES_MIN_CHARS or kural_sayisi >= SCOPED_RULES_MAX_FILES:
            atlanan.append(kural.label)
            continue
        blok, eklenen = rule_block(kural, min(MAX_RULE_FILE_CHARS, kural_kalan))
        loaded.add(kural.label)
        if not blok:
            continue
        bloklar.append(blok)
        adlar.append(kural.label)
        toplam += eklenen
        kural_kalan -= eklenen
        kural_sayisi += 1
    if atlanan:
        bloklar.append(
            f"[…{len(atlanan)} kural bu erişimde bütçe nedeniyle atlandı: "
            + ", ".join(atlanan)
            + " — sonraki erişimde gelir ya da read_file ile oku…]"
        )
    if not bloklar:
        return None
    metin = "\n".join([NESTED_NOTE_HEADER, *bloklar])
    return NestedLoad(Message("user", metin, harness_note=True), tuple(adlar), toplam)


def _scoped_rules(kok: Path, target: Path, rules: tuple[RuleFile, ...]) -> tuple[RuleFile, ...]:
    """Erişilen dosyanın köke göreli yoluna uyan `paths:` kuralları; kök dışı hedefte boş."""
    if not rules:
        return ()
    try:
        rel = target.resolve().relative_to(kok).as_posix()
    except (OSError, ValueError):
        return ()
    return scoped_rules_for(rules, rel)


def resolve_access_path(context: object, raw: str) -> Path | None:
    """Modelin verdiği yolu çöz; kısıtlı kipte kök dışına çıkıyorsa `None`."""
    try:
        return resolve_path(context, raw)  # type: ignore[arg-type]
    except (PathAccessError, OSError, ValueError):
        return None


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
    if not kanit:  # kanıtı tanımsız tür: "bu dizin bir  projesidir" demesin (A3-32)
        return ""
    return (
        f"ÇALIŞMA ALANI: bu dizin bir {kanit} projesidir. Görev bu projeye aittir; "
        "işi projenin kendi araç ve biçimleriyle yap, başka bir teknolojiyle "
        "yandan yeni bir proje kurma."
    )


#: Depo uyarısında adı sayılacak en fazla proje.
_CONTAINER_LIST_LIMIT = 12


def container_root_note(root: Path, home: Path) -> str:
    """Kök bir PROJE DEPOSUysa (Masaüstü, içinde birden çok proje) modele uyarı.

    Ölçüldü (1 Ekim olayı): Fusion `~/Desktop`'ta açıktı; "projeyi tamamiyle sil"
    isteğinde model "proje" = çalışma kökü sandı ve Masaüstündeki projeleri sildi.
    Kullanıcının kastettiği tek bir alt klasördü (`sneaksup-wp`).
    """
    if not is_container_root(root, home):
        return ""
    projeler = [p.relative_to(root.resolve()).as_posix() for p in project_folders(root.resolve())]
    liste = ", ".join(projeler[:_CONTAINER_LIST_LIMIT]) or "(işaretli proje yok)"
    return (
        "DİKKAT — BU KÖK BİR PROJE DEPOSU: içinde ayrı projeler var ("
        + liste
        + "). Kullanıcı 'proje', 'site', 'uygulama' dediğinde bu kökün TAMAMINI değil "
        "içindeki TEK bir projeyi kasteder. Hangisi olduğu açık değilse ask_user ile sor. "
        "Kökün tamamını silme, taşıma ya da toptan yeniden düzenleme."
    )


#: ORTAM bloğunda varlığı ölçülen araçlar. Ölçüldü (2 Ekim): `wp`, `mysql`, `docker`
#: kuruluyken listede yoktu; model kullanıcıya bunları kurmasını söyleyen rehber yazdı.
_MEASURED_EXECUTABLES = (
    "git", "python3", "node", "npm", "php", "wp", "composer", "mysql", "docker", "brew",
    "godot",
)  # fmt: skip


def read_all_instructions(
    root: Path,
    home: Path | None,
    *,
    instruction_merge: bool = True,
    instruction_max_chars: int = TOTAL_MAX_CHARS,
) -> str:
    """Proje talimatı ve dış araç belleklerini birlikte döndür.

    Sıra bilinçlidir: kullanıcı katmanı önce, proje katmanı sonra gelir — çakışma
    halinde projeye daha yakın olan kural kazanır (Claude Code ile aynı). Dış bellek
    (MEMORY.md vb.) en sonda.

    `home` verilmezse (ör. testte ya da ev dizini bilinmiyorsa) kullanıcı katmanı ve dış
    bellek hiç okunmaz — bu, `AgentDeps` alanlarının "yoksa o yetenek hiç sunulmaz"
    deseniyle tutarlıdır. `instruction_merge=False` eski tek-dosya davranışıdır.
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
                    for name in _MEASURED_EXECUTABLES
                    if (path := shutil.which(name, path=tool_path()))
                },
            },
            ensure_ascii=False,
        )
        + "\nDosya yollarını bu çalışma köküne göreli yaz; başka bir kök veya işletim "
        "sistemi varsayma. Listelenen çalıştırılabilir dosyalar PATH üzerinde bulundu; "
        "sürümleri henüz doğrulanmadı. Yeni kurulumdan önce mevcut aracı denetle. "
        "Bu araçlarla yapılabilen kurulumu KENDİN yap; kullanıcıya komut listesi verme. "
        "Kullanıcı sonucu görmek/önizlemek/çalıştırmak isterse start_preview çağır."
    )
    depo = container_root_note(root, home or Path.home())
    if depo:
        ortam = f"{ortam}\n{depo}"
    ozet = workspace_summary(root)
    proje_talimati = read_project_instructions(
        root, home, merge=instruction_merge, max_chars=instruction_max_chars
    )
    # `.claude/rules` genel kuralları (P-016); `paths:` olanlar dosya erişiminde gelir.
    kurallar = unscoped_rules_block(discover_rules(root, home)) if instruction_merge else ""
    if home is None:
        return "\n".join(part for part in (ortam, ozet, proje_talimati, kurallar) if part)

    from ...history.memory_files import read_external_memory

    dis_bellek = read_external_memory(home, root)
    parts = [ortam, ozet, proje_talimati, kurallar, dis_bellek]
    return "\n".join(part for part in parts if part)
