"""Duraklatma mesajı modelin açıklamasını EZMEZ.

Ölçüldü (6 Eylül canlı koşusu, `erisilemeyen-kaynagi-uydurma`): adım doğrulamadan
geçemedi ("beklenen çalışma alanı değişikliği gözlenmedi") ve duraklatma mesajı
modelin açıklamasının YERİNE geçti. Kullanıcı yalnızca "Plan adımı duraklatıldı"
gördü; adresin hiç var olmadığını öğrenemedi — oysa eksik olan bilgi tam da oydu.

Bulgu ile açıklama farklı sorulara cevap verir: bulgu kapının neden kapandığını,
açıklama işin neden yapılamadığını söyler. Biri diğerinin yerine geçemez.
"""

from __future__ import annotations

from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import _pause_text
from fusion_cli.engines.agent.step_verification import StepVerificationResult


def _dogrulama(*findings: str) -> StepVerificationResult:
    return StepVerificationResult(ok=False, findings=tuple(findings))


def _sonuc(text: str) -> AgentOutcome:
    return AgentOutcome(final_text=text, messages=[], model_calls_made=1, tool_calls_made=1)


def test_bulgu_ve_aciklama_birlikte_yazilir():
    metin = _pause_text(
        "fetch-site",
        "Adım yinelendiğinde dış etkiyi çoğaltabilir.",
        _dogrulama("beklenen çalışma alanı değişikliği gözlenmedi"),
        _sonuc("Adrese erişemedim: alan adı çözülemedi."),
    )

    assert "fetch-site" in metin
    assert "beklenen çalışma alanı değişikliği gözlenmedi" in metin
    assert "alan adı çözülemedi" in metin, "modelin açıklaması kayboldu"


def test_aciklama_yoksa_mesaj_yine_anlamli():
    metin = _pause_text("adim", "Sebep.", _dogrulama("bulgu"), _sonuc("   "))

    assert metin == "Plan adımı duraklatıldı: adim. Sebep. bulgu"


def test_bulgu_yoksa_aciklama_kullanilir():
    metin = _pause_text("adim", "Sebep.", _dogrulama(), _sonuc("model ne yaptığını anlattı"))

    assert "model ne yaptığını anlattı" in metin


def test_aciklama_bulgunun_kopyasiysa_tekrarlanmaz():
    metin = _pause_text("adim", "Sebep.", _dogrulama("aynı metin"), _sonuc("aynı metin"))

    assert metin.count("aynı metin") == 1
