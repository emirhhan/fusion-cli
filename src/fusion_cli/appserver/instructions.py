"""Kullanıcının kendi kalıcı talimatları.

Kullanıcı "her seferinde aynı şeyi yazmak istemiyorum" dediğinde çözüm, sistem
istemini KOPYALAYIP düzenletmek değildir: ürünün kimliği ve onay sözleşmesi
sistem isteminde durur, onu kullanıcıya açmak Fusion'ı kendi kurallarından
edebilir. Bunun yerine kullanıcı metni EK bir blok olarak eklenir ve tur
bağlamına `extra_system` üzerinden girer — yani izinler, araç kuralları ve
kimlik olduğu gibi kalır.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.atomic_file import atomic_replace_text
from . import voice

#: Talimat metni için üst sınır. Uzun bir blok her turda bağlamı yer ve
#: modelin asıl göreve ayıracağı payı düşürür; sınır bunu görünür kılar.
MAX_UZUNLUK = 4000


def instructions_path() -> Path:
    """Talimat dosyasının yolu. Kullanıcı verisiyle birlikte durur."""
    # `voice` modülü ÜZERİNDEN çağrılır, adı doğrudan içeri alınmaz: doğrudan
    # alınsaydı testteki dizin değişimi burada görünmezdi.
    return voice._data_home() / "instructions.md"


def read_instructions() -> str:
    """Kayıtlı talimat. Dosya yoksa ya da okunamıyorsa boş dize döner."""
    try:
        return instructions_path().read_text(encoding="utf-8")
    except OSError:
        return ""


def get_instructions(root: Path | None = None, home: Path | None = None) -> dict[str, Any]:
    """`ayar.talimat`: kayıtlı metin, sınır ve (kök verilmişse) yüklenen talimat katmanları.

    `katmanlar`: tur başında bağlama giren dosyalar — kaynak adı, katman, karakter, kırpılan
    karakter ve güvenilir olup olmadığı. `notlar`: atlanan import / dolan bütçe gibi uyarılar.
    """
    sonuc: dict[str, Any] = {"ok": True, "metin": read_instructions(), "sinir": MAX_UZUNLUK}
    if root is None:
        return sonuc
    from ..engines.agent.project_instructions import load_startup_instruction_files

    yuk = load_startup_instruction_files(root, home)
    sonuc["katmanlar"] = [
        {
            "kaynak": item.label,
            "katman": item.layer,
            "karakter": item.chars,
            "kirpilan": item.trimmed,
            "guvenilir": item.trusted,
        }
        for item in yuk.files if item.layer != "kural"
    ]
    # `.claude/rules` kuralları da katman listesine girer (katman "kural", `kapsam` = paths).
    # Eksik yüzeydi: arayüzün "Kural" etiketi vardı ama hiç kullanılmıyordu (31 Ekim).
    from ..engines.agent.instruction_rules import MAX_RULE_FILE_CHARS, discover_rules, rule_block

    for kural in discover_rules(root, home):
        _, karakter = rule_block(kural, MAX_RULE_FILE_CHARS)
        sonuc["katmanlar"].append(
            {
                "kaynak": kural.label,
                "katman": "kural",
                "karakter": karakter,
                "kirpilan": 0,
                "guvenilir": kural.trusted,
                "kapsam": list(kural.paths),
            }
        )
    sonuc["notlar"] = list(yuk.notes)
    # Kararı verilmemiş dış `@import` hedefleri (Claude Code #145): arayüz onay sorar.
    from ..engines.agent.import_approval import pending_external_imports

    sonuc["dis_importlar"] = [str(path) for path in pending_external_imports(root, home)]
    sonuc["toplam_karakter"] = sum(item.chars for item in yuk.files)
    # `/doctor prompt` ile aynı öneriler (P-021): arayüz Kişiselleştirme ekranında gösterir.
    from ..engines.agent.instruction_audit import audit_instructions

    denetim = audit_instructions(root, home)
    sonuc["oneriler"] = list(denetim.suggestions)
    sonuc["supheli"] = [
        {"kaynak": s.source, "satir": s.line_no, "metin": s.text} for s in denetim.suspicious
    ]
    return sonuc


def set_external_imports(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    """`ayar.dis_import_karari`: dış import onayı ya da reddi (proje başına saklanır, #145)."""
    from ..engines.agent.import_approval import record

    onay = data.get("onay")
    if not isinstance(onay, bool):
        return {"ok": False, "metin": "'onay' alanı true ya da false olmalı."}
    return {"ok": True, "metin": record(root, "e" if onay else "h")}


def save_instructions(value: object) -> dict[str, Any]:
    """`ayar.talimat_kaydet`: metni kaydet ya da boşsa dosyayı kaldır."""
    text = "" if value is None else str(value)
    if len(text) > MAX_UZUNLUK:
        return {
            "ok": False,
            "metin": f"Talimat en fazla {MAX_UZUNLUK} karakter olabilir.",
        }
    try:
        if not text.strip():
            instructions_path().unlink(missing_ok=True)
            return {"ok": True, "metin": ""}
        # Atomik yaz: çökme/eşzamanlı okuma yarım talimat görmesin (ölçüldü 30 Ekim:
        # doğrudan `write_text` dosyayı önce boşaltıyordu).
        atomic_replace_text(instructions_path(), text)
    except OSError as error:
        return {"ok": False, "metin": f"Talimat kaydedilemedi: {error}"}
    return {"ok": True, "metin": text}


def instruction_block() -> str:
    """Tur bağlamına eklenecek blok. Talimat yoksa boş dize."""
    text = read_instructions().strip()
    if not text:
        return ""
    return (
        "<kullanici_talimatlari>\n"
        "Kullanıcının kalıcı tercihleri. Onay ve araç kurallarını DEĞİŞTİRMEZ; "
        "onlarla çelişen bir istek varsa kurallar geçerlidir.\n"
        f"{text}\n"
        "</kullanici_talimatlari>"
    )
