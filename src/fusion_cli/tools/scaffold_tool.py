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
        # Yazmadan ÖNCE kaydet: iskele de turun değişiklik kümesine girer. Eskiden
        # yalnızca `touched`'a ekleniyordu; `/undo` iskeleyi görmüyor ve motor bu
        # dosyaların agent tarafından oluşturulduğunu bilemiyordu.
        context.changes.record(dosya)
        dosya.write_text((_TEMPLATES / ad).read_text(encoding="utf-8"), encoding="utf-8")
        context.touched.add(dosya)
        yazilan.append(ad)

    return ToolResult(_ozet(hedef, yazilan, korunan, yabanci_sayfalar(hedef)))


def yabanci_sayfalar(hedef: Path) -> tuple[str, ...]:
    """Hedef dizinde iskeleye ait OLMAYAN sayfa dosyaları.

    Varlıkları iskelenin muhtemelen yanlış hamle olduğunu gösterir: dizinde zaten bir
    site var demektir ve jenerik bir iskele onun üzerine bindirilmemelidir.
    """
    try:
        girisler = sorted(yol.name for yol in hedef.iterdir() if yol.is_file())
    except OSError:
        return ()
    return tuple(
        ad for ad in girisler if ad.endswith((".html", ".htm")) and ad not in SCAFFOLD_FILES
    )


def _ozet(
    hedef: Path, yazilan: list[str], korunan: list[str], yabanci: tuple[str, ...]
) -> str:
    satirlar = [f"iskele hazır: {hedef}"]
    if yazilan:
        satirlar.append(f"yazıldı: {', '.join(yazilan)}")
    if korunan:
        satirlar.append(f"zaten vardı, korundu (atlandı): {', '.join(korunan)}")
    if yabanci:
        # Uyarı ARAÇ SONUCUNA konur, prompta değil: bu modülün başındaki ölçüm,
        # modelin prompt kurallarını atlayıp araç sonucuna tepki verdiğini gösteriyor.
        satirlar.append(
            "DİKKAT: bu dizinde zaten sayfa var — " + ", ".join(yabanci) + ". Görev "
            "sıfırdan yeni bir arayüz kurmak değilse iskeleyi DOLDURMA: önce var olan "
            "dosyaları oku ve asıl görevi onların üzerinden yürüt. Yazılan iskele "
            "dosyaları gereksizse bırak, üzerlerine jenerik içerik üretme."
        )
    satirlar.append(
        "Şimdi bunları DOLDUR: index.html'deki BÜYÜK HARFLİ yer tutucuları gerçek "
        "içerikle değiştir, style.css'i tokens.css değişkenlerini kullanarak yaz, "
        "script.js'te format.js'ten import et. tokens.css ve format.js'i YENİDEN YAZMA."
    )
    return "\n".join(satirlar)
