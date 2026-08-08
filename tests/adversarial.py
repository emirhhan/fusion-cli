"""Zayıf modellerin BİLİNEN kötü davranışlarını üreten sağlayıcılar.

Her davranış gerçek koşularda ölçülmüştür (kod tabanındaki "ölçüldü" yorumlarının
kaynağı bunlar). Amaç modeli düzeltmek değil — modeli düzeltemeyiz. Amaç şunu
garanti etmek:

    Model SONUNDA geçerli bir hamle yaparsa, harness onu engellemez.

Kilitlenme tam olarak bu iddianın ihlalidir: model toparlanır ama kapılar birbirini
kilitlediği için hamlesi hiç çalışmaz ve tur sıfır ilerlemeyle ölür.

Her sağlayıcı önce N kötü tur üretir, sonra DOĞRU hamleyi yapar. Test o doğru
hamlenin diske indiğini ölçer.
"""

from __future__ import annotations

from collections.abc import Iterator

from fusion_cli.core.types import ModelResult, ToolCall

from .fakes import model_result, tool_call

#: Doğru hamlenin diske yazdığı içerik. Testler bu metni dosyada arar.
HEDEF_ICERIK = "<!DOCTYPE html>\n<html lang=\"tr\"><body><h1>Gerçek İçerik</h1></body></html>\n"
HEDEF_DOSYA = "index.html"

#: Model toparlandıktan sonra verdiği nihai cevap. Somut teslim içerir ki
#: otomatik-devam sezgiseli turu "yarım" sanıp fazladan tur harcamasın.
BITIS_CEVABI = f"Sayfa `{HEDEF_DOSYA}:1` içine yazıldı ve doğrulandı."


def dogru_hamle() -> ModelResult:
    """Her senaryonun sonunda gelen GEÇERLİ hamle: dosyayı yaz."""
    return model_result(
        tool_calls=(tool_call("write_file", path=HEDEF_DOSYA, content=HEDEF_ICERIK),)
    )


def _bozuk_cagri(name: str, raw: str) -> ToolCall:
    """Ham (ayrıştırılamayan) argümanlı çağrı — şema doğrulaması buna takılmalı."""
    return ToolCall(id=f"call_{name}", name=name, arguments=raw)


# --------------------------------------------------------------------------- #
# Davranışlar — her biri (ad, betik) döndürür
# --------------------------------------------------------------------------- #


def tekrarci() -> list[ModelResult]:
    """Aynı okumayı üst üste yapar (tekrar kapısına takılır), sonra toparlar.

    Ölçülen: model dört dosyayı okuyup birini düzelttikten sonra aynı dosyayı üç
    kez okudu ve tur boşa gitti.
    """
    return [
        model_result(tool_calls=(tool_call("list_dir", path="."),)),
        model_result(tool_calls=(tool_call("list_dir", path="."),)),
        model_result(tool_calls=(tool_call("list_dir", path="."),)),
        dogru_hamle(),
        model_result(BITIS_CEVABI),
    ]


def kor_yazici() -> list[ModelResult]:
    """Var olan dosyayı okumadan ezmeye çalışır, engellenir, sonra okuyup yazar."""
    return [
        model_result(
            tool_calls=(tool_call("write_file", path="mevcut.txt", content="ezildi"),)
        ),
        model_result(tool_calls=(tool_call("read_file", path="mevcut.txt"),)),
        dogru_hamle(),
        model_result(BITIS_CEVABI),
    ]


def bozuk_json() -> list[ModelResult]:
    """Ayrıştırılamayan argüman gönderir, sözleşme kapısına takılır, sonra düzeltir."""
    return [
        model_result(tool_calls=(_bozuk_cagri("read_file", "{path: index.html"),)),
        dogru_hamle(),
        model_result(BITIS_CEVABI),
    ]


def yanlis_arac() -> list[ModelResult]:
    """Var olmayan bir araç çağırır, sonra doğrusunu bulur."""
    return [
        model_result(tool_calls=(tool_call("dosya_yaz", yol="x", icerik="y"),)),
        dogru_hamle(),
        model_result(BITIS_CEVABI),
    ]


def eksik_alan() -> list[ModelResult]:
    """Zorunlu alanı düşürür (ölçüldü: büyük içerikte 'path' sık düşüyor), sonra tamamlar."""
    return [
        model_result(tool_calls=(tool_call("write_file", content=HEDEF_ICERIK),)),
        dogru_hamle(),
        model_result(BITIS_CEVABI),
    ]


def erken_pes_eden() -> list[ModelResult]:
    """Araç çağırmadan 'yaptım' der, kanıt kapısına takılır, sonra gerçekten yapar."""
    return [
        model_result("Dosyayı oluşturdum."),
        dogru_hamle(),
        model_result(BITIS_CEVABI),
    ]


def sonuc_yoksayan() -> list[ModelResult]:
    """Hata sonucunu yok sayıp aynı hatayı tekrarlar, sonra farklı yol dener."""
    bozuk = model_result(
        tool_calls=(tool_call("edit_file", path=HEDEF_DOSYA, old="YOK", new="x"),)
    )
    return [bozuk, bozuk, dogru_hamle(), model_result(BITIS_CEVABI)]


def iskele_dolduran() -> list[ModelResult]:
    """Gerçek olay: iskele kurar, sonra iskele dosyasını doldurmaya çalışır."""
    return [
        model_result(tool_calls=(tool_call("scaffold_web", path="."),)),
        dogru_hamle(),
        model_result(BITIS_CEVABI),
    ]


def gec_toparlanan() -> list[ModelResult]:
    """Boşta-tur kapısının SINIRINDA toparlanır: kapı bir tur erken kesmemeli."""
    bos = model_result(tool_calls=(_bozuk_cagri("read_file", "}{"),))
    return [bos, bos, dogru_hamle(), model_result(BITIS_CEVABI)]


#: (ad, betik üretici) — testler bunun üzerinde gezinir. Yeni bir zayıf-model
#: davranışı ölçüldüğünde buraya eklenir ve tüm özellik testleri onu da kapsar.
DAVRANISLAR: tuple[tuple[str, Iterator[ModelResult] | object], ...] = (
    ("tekrarci", tekrarci),
    ("kor_yazici", kor_yazici),
    ("bozuk_json", bozuk_json),
    ("yanlis_arac", yanlis_arac),
    ("eksik_alan", eksik_alan),
    ("erken_pes_eden", erken_pes_eden),
    ("sonuc_yoksayan", sonuc_yoksayan),
    ("iskele_dolduran", iskele_dolduran),
    ("gec_toparlanan", gec_toparlanan),
)
