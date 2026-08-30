"""Oturum kullanımı ve sağlık özeti."""

from __future__ import annotations

from fusion_cli.appserver.usage import UsageMeter, health_payload, usage_status
from fusion_cli.core.events import ModelCallFinished, ToolExecuted
from fusion_cli.core.health import HealthRegistry
from fusion_cli.core.types import ModelResult, TokenUsage


def _bitis(model: str, girdi: int, cikti: int, maliyet: float = 0.0) -> ModelCallFinished:
    return ModelCallFinished(
        role="agent",
        result=ModelResult(
            name="agent",
            model=model,
            text="x",
            latency_ms=10,
            ok=True,
            usage=TokenUsage(prompt_tokens=girdi, completion_tokens=cikti, cost_usd=maliyet),
        ),
    )


def test_token_ve_maliyet_toplanir():
    olcer = UsageMeter()

    olcer.observe(_bitis("a/b", 100, 50, 0.002))
    olcer.observe(_bitis("a/b", 20, 10, 0.001))

    yuk = olcer.payload()
    assert yuk["cagri"] == 2
    assert yuk["toplam_token"] == 180
    assert yuk["maliyet_usd"] == 0.003


def test_model_kirilimi_cok_harcayandan_baslar():
    olcer = UsageMeter()
    olcer.observe(_bitis("az/model", 5, 5))
    olcer.observe(_bitis("cok/model", 500, 500))

    modeller = olcer.payload()["modeller"]

    assert modeller[0]["model"] == "cok/model"


def test_model_disi_olay_sayaci_bozmaz():
    olcer = UsageMeter()

    olcer.observe(ToolExecuted(name="read_file", args={}, outcome="ok", output=""))

    assert olcer.payload()["cagri"] == 0


def test_hic_ornek_gormemis_model_saglikta_listelenmez():
    """Ölçülmemiş bir modeli "kötü" göstermek yanıltıcı olurdu."""
    kayit = HealthRegistry(failure_threshold=3, cooldown_s=30, alpha=0.3)
    kayit.for_model("hic/kullanilmadi")

    assert health_payload(kayit) == []


def test_olculmus_model_durumuyla_listelenir():
    kayit = HealthRegistry(failure_threshold=3, cooldown_s=30, alpha=0.3)
    kayit.for_model("a/b").record(True, latency_ms=120)

    satirlar = health_payload(kayit)

    assert satirlar[0]["model"] == "a/b"
    assert satirlar[0]["durum"] == "sağlıklı"
    assert satirlar[0]["ornek"] == 1


def test_durum_yuku_iki_bolumu_de_tasir():
    kayit = HealthRegistry(failure_threshold=3, cooldown_s=30, alpha=0.3)
    olcer = UsageMeter()
    olcer.observe(_bitis("a/b", 10, 10))

    yuk = usage_status(olcer, kayit)

    assert yuk["ok"] is True
    assert yuk["kullanim"]["toplam_token"] == 20
    assert yuk["saglik"] == []
