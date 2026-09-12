"""`web.arac_olc`: taklit araç yeteneğini ölç ve sonucu yapılandırmaya yaz.

Bu, `WebSessionConfig.tool_eval_passed` bayrağını açan TEK yoldur. Puanlayıcı
(`tools/emulation_eval`) ve sonda (`engines/emulation_probe`) yazılmıştı ama
ikisini bağlayıp sonucu KAYDEDEN bir yol yoktu: bayrak yalnız `config.yaml` elle
düzenlenerek true olabiliyordu. Sonucu ölçüldü (kullanıcı makinesi) — `gemini_web`
elle açıldığı için dosya yazabiliyor, `chatgpt_web` aynı yetenekte olmasına
rağmen hiçbir şey yazamıyor ve kullanıcı sebebini göremiyordu.

Neden `appserver` altında: ölçüm `engines` sondasını çağırır, sonucu `providers`
yapılandırmasına yazar. Katman yönü `engines → providers` olduğu için bu bağlama
`providers` içinde duramaz (RULES.md "Katman Sınırları").

Ölçüm kullanıcının KOTASINDAN harcar; yalnız açık istekle çalışır.
"""

from __future__ import annotations

from typing import Any

from ..config.models import Config
from ..core.errors import FusionError
from ..engines.emulation_probe import ProbeReport, probe_emulation
from ..providers.web_browser import normalize_account
from ..providers.web_control import session_model, set_tool_eval_passed
from ..tools.emulation_eval import DEFAULT_THRESHOLDS

__all__ = ["measure_tool_support"]


async def measure_tool_support(
    config: Config, provider: str, account: str = "main"
) -> dict[str, Any]:
    """Oturumu ölç, bayrağı yaz, sonucu arayüze döndür."""
    hesap = normalize_account(account or "main")
    model = session_model(provider, hesap)
    try:
        rapor = await probe_emulation(config, model)
    except FusionError as hata:
        return {"ok": False, "metin": str(hata)}

    puan = rapor.score
    # Ölçülemeyen metrik 1.0 döner ("uygulanamadı" cezalandırılmaz). Hiçbir
    # senaryoda çağrı üretilmediyse bu, ölçümün GEÇTİĞİ anlamına gelmez: dosya
    # yazma izni ölçülmemiş bir yeteneğe verilemez.
    olculdu = puan.tool_selection_measured > 0
    gecti = olculdu and puan.passes()
    yeni = set_tool_eval_passed(config, provider, hesap, gecti)
    if yeni is None:
        return {"ok": False, "metin": "Ölçüm sonucu kaydedilemedi."}
    return {
        "ok": True,
        "gecti": gecti,
        "metin": _ozet(rapor, gecti=gecti, olculdu=olculdu),
        "puan": {
            "arac_secimi": puan.tool_selection,
            "sema_uyumu": puan.schema_validity,
            "arguman_korunumu": puan.argument_preservation,
            "gereksiz_cagri": puan.no_false_calls,
        },
    }


def _ozet(rapor: ProbeReport, *, gecti: bool, olculdu: bool) -> str:
    """Sonucu kullanıcının okuyabileceği tek cümleye indir.

    Geçemeyen ölçümde HANGİ sebepten düştüğü söylenir: "başarısız" demek
    kullanıcıya ne yapacağını göstermez.
    """
    if gecti:
        return "Ölçüm geçti: bu oturum dosya değiştiren ajan olarak kullanılabilir."
    if not olculdu:
        # İşaretin hiç görünmemesi ile görünüp ayrıştırılamaması farklı sorunlardır:
        # ilki modelin bloğu üretmemesi ya da arayüzün yutması, ikincisi biçim hatası.
        isaret_var = any(ornek.has_call_markers for ornek in rapor.samples)
        sebep = (
            "blok üretildi ama ayrıştırılamadı"
            if isaret_var
            else "model hiç araç bloğu üretmedi"
        )
        return (
            f"Ölçüm geçmedi: {sebep}. "
            "Bu oturum okuyabilir ve plan yapabilir ama dosya değiştiremez."
        )
    puan = rapor.score
    dusen = [
        ad
        for ad, deger, esik in (
            ("araç seçimi", puan.tool_selection, DEFAULT_THRESHOLDS.tool_selection),
            ("şema uyumu", puan.schema_validity, DEFAULT_THRESHOLDS.schema_validity),
            (
                "argüman korunumu",
                puan.argument_preservation,
                DEFAULT_THRESHOLDS.argument_preservation,
            ),
            ("gereksiz çağrı", puan.no_false_calls, DEFAULT_THRESHOLDS.no_false_calls),
        )
        if deger < esik
    ]
    return (
        "Ölçüm geçmedi: " + ", ".join(dusen) + ". "
        "Bu oturum okuyabilir ve plan yapabilir ama dosya değiştiremez."
    )
