"""Web kademesi (tier) beklentisi karşılaştırması (Faz 4, Görev 4).

Model kimliği `<sağlayıcı>/<hesap>/<kademe>` biçimindedir (bkz.
`providers/web_control.py::session_model`). Kademe `auto` ise kullanıcı BELİRLİ
bir kademe İSTEMEMİŞTİR — karşılaştırma o zaman GÜRÜLTÜ olur (Faz 4 planı §6.5
kararı). Yalnız kullanıcı açıkça bir kademe seçtiğinde (`gemini_web/main/pro`
gibi) ve gözlenen (`ModelResult.served_by`) bundan FARKLI görünüyorsa bir
uyuşmazlık raporlanır.
"""

from __future__ import annotations

from .constants import WEB_PROVIDER_SUFFIX


def expected_tier(model_id: str) -> str:
    """Model kimliğinin son parçası; `auto` ya da eksikse boş (beklenti YOK).

    Yalnız WEB oturumu kimlikleri için anlamlıdır (`<sağlayıcı>_web/<hesap>/
    <kademe>`, bkz. `providers/web_control.py::session_model`). Normal API
    kimlikleri de 3 parçadan oluşabilir (ör. `nvidia_nim/nvidia/nemotron-3-
    super-120b-a12b`) ama üçüncü parça orada bir MODEL adıdır, kademe değil —
    sağlayıcı öneki `_web` ile bitmiyorsa hiçbir zaman beklenti üretilmez
    (`ui/text.py::format_model` ile AYNI ayrım, `WEB_PROVIDER_SUFFIX`).
    """
    parcalar = model_id.split("/")
    if len(parcalar) < 3 or not parcalar[0].endswith(WEB_PROVIDER_SUFFIX):
        return ""
    son = parcalar[-1].strip()
    return "" if son.lower() == "auto" else son


def tier_mismatch(model_id: str, served_by: str) -> str:
    """Beklenen kademe TANIMLIYSA ve gözlenende GEÇMİYORSA beklenen kademeyi döndür.

    Tam bir kademe SIRALAMASI (pro > flash > flash-lite) kurulmadı — bu ölçülmedi
    ve sağlayıcıya göre değişir. Bunun yerine daha basit, daha güvenilir bir
    sinyal kullanılır: beklenen kademe adı gözlenen etikette geçmiyorsa bu her
    zaman bir uyuşmazlıktır (`web_browser.py:1865` civarındaki geçmiş hatadan
    ders: bu yalnız BİLGİLENDİRİR, turu asla düşürmez).
    """
    beklenen = expected_tier(model_id)
    gozlenen = served_by.strip()
    if not beklenen or not gozlenen:
        return ""
    return "" if beklenen.lower() in gozlenen.lower() else beklenen
