"""Token sınırında kesilmiş görünen dosya yazımlarını ucuz kontrollerle yakala.

Ölçüldü (30 Ekim): kısa çıktılı bir model 400 satırlık HTML/Python'ı yarıda kesip
`write_file` çağırdığında yalnız yapılandırılmış biçimler (JSON/Godot/Python) doğrulanıyordu;
`.css`, `.html` "oluşturuldu: x (212 satır)" başarı mesajıyla diske gidiyor,
hata ancak sonraki turda çalıştırma/derleme sırasında görülüyordu.

Bu kontroller ENGEL DEĞİL, UYARIDIR: dosyayı parça parça yazan akışlar (iskele, sonra
doldurma) geçici olarak eksik dosya bırakabilir. Uyarı modele "tamamını yazdın mı?"
sorusunu sordurur; yanlış alarm bir cümleye mal olur, kaçırılan kesik dosya bir tura.
"""

from __future__ import annotations

import re
from pathlib import Path

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_HTML_OPEN = re.compile(r"<html[\s>]", re.IGNORECASE)
_HTML_CLOSE = re.compile(r"</html\s*>", re.IGNORECASE)


def yarim_uyarisi(path: Path, content: str) -> str | None:
    """Dosya yarıda kesilmiş görünüyorsa tek cümlelik uyarı; sağlam görünüyorsa None."""
    ek = path.suffix.lower()
    # `.py` burada YOK: `validate_structured` Python sözdizimini zaten ENGELLER.
    if ek in {".html", ".htm"}:
        if _HTML_OPEN.search(content) and not _HTML_CLOSE.search(content):
            return (
                "UYARI: dosya yarım olabilir, </html> ile bitmiyor. Çıktın token "
                "sınırında kesilmiş olabilir; kalan kısmı edit_file ile ekle."
            )
    elif ek == ".css":
        govde = _CSS_COMMENT.sub("", content)
        if govde.count("{") != govde.count("}"):
            return (
                "UYARI: dosya yarım olabilir, süslü parantezler dengesiz "
                f"({govde.count('{')} açılış, {govde.count('}')} kapanış)."
            )
    return None
