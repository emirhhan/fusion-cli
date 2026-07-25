"""Web iskelesi — tasarım referansını PROMPTA değil DİSKE koyar.

Bu oturumda üç kez ölçüldü: model prompt'taki kuralları sıkça görmezden geliyor, araç
sonucuna ise tepki veriyor. Kullanıcının isteğinde açıkça "boş bağlantı bulunmasın"
yazmasına rağmen 18-29 boş bağlantı üretildi; aynı model, kapı araç sonucu olarak
söyleyince hepsini düzeltti.

Araştırma da aynı yöne işaret ediyor: bileşen/iskele tabanlı üretim, bütün-sayfa
üretimini ölçülebilir biçimde yeniyor (ComUICoder, 1D-Bench) ve bolt.new, v0, Lovable
gibi araçların hepsi sabit bir iskeleden başlıyor. UI kodu eğitim verisinin %1'inden
azı olduğu için (Apple UICoder) zayıf modelin doğru yapıyı kendiliğinden kurmasını
beklemek gerçekçi değil — ona doğru yapıyı VERMEK gerekiyor.

İskele YIKICI DEĞİLDİR: var olan dosyanın üzerine yazmaz, atlar.
"""

from __future__ import annotations

from pathlib import Path

from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import optional_str
from .files import resolve_path

#: Diske yazılacak iskele dosyaları. İçerikleri paket içinde durur ve test edilir.
SCAFFOLD_FILES: tuple[str, ...] = ("tokens.css", "format.js", "index.html")

_TEMPLATES = Path(__file__).parent / "scaffold"


def scaffold_web(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Hazır tasarım token'ları, biçimlendiriciler ve sayfa iskeletini diske yaz."""
    hedef = resolve_path(context, optional_str(args, "path", "."))
    hedef.mkdir(parents=True, exist_ok=True)

    yazilan: list[str] = []
    korunan: list[str] = []
    for ad in SCAFFOLD_FILES:
        dosya = hedef / ad
        if dosya.exists():
            # Kullanıcının ya da önceki turun dosyasını EZME.
            korunan.append(ad)
            continue
        dosya.write_text((_TEMPLATES / ad).read_text(encoding="utf-8"), encoding="utf-8")
        context.touched.add(dosya)
        yazilan.append(ad)

    return ToolResult(_ozet(hedef, yazilan, korunan))


def _ozet(hedef: Path, yazilan: list[str], korunan: list[str]) -> str:
    satirlar = [f"iskele hazır: {hedef}"]
    if yazilan:
        satirlar.append(f"yazıldı: {', '.join(yazilan)}")
    if korunan:
        satirlar.append(f"zaten vardı, korundu (atlandı): {', '.join(korunan)}")
    satirlar.append(
        "Şimdi bunları DOLDUR: index.html'deki BÜYÜK HARFLİ yer tutucuları gerçek "
        "içerikle değiştir, style.css'i tokens.css değişkenlerini kullanarak yaz, "
        "script.js'te format.js'ten import et. tokens.css ve format.js'i YENİDEN YAZMA."
    )
    return "\n".join(satirlar)
