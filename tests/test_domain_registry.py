"""Alan kayıt defteri: yeni alan eklemek motoru değiştirmeden adaptör eklemektir.

Kayıt defteri alanların kanıt sözleşmelerini birleştirir; hangi alanın ne istediğini
motor bilmez. Çok alanlı projede (ör. `.blend` + `project.godot`) eşleşen TÜM alanlar
uygulanır: birini seçmek diğerinin kapısını sessizce düşürürdü.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from fusion_cli.core.errors import FusionError
from fusion_cli.engines.agent.domain_adapters.contract import DomainAdapter, ToolFailureMarkers
from fusion_cli.engines.agent.domain_adapters.registry import DomainRegistry
from fusion_cli.engines.agent.plan_coverage import Deliverable


def test_birden_cok_alan_eslesirse_hepsi_kayit_sirasiyla_doner(tmp_path):
    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")
    (tmp_path / "medya.json").write_text("{}", encoding="utf-8")
    blender = DomainAdapter(name="blender", marker="sahne.blend")
    web = DomainAdapter(name="web", marker="index.html")
    medya = DomainAdapter(name="medya", marker="medya.json")
    kayit = DomainRegistry((blender, web, medya))

    assert kayit.matching(tmp_path) == (blender, medya)
    assert kayit.first_match(tmp_path) is blender


def test_eslesen_alanlarin_kapilari_sirayla_ve_tekrarsiz_birlesir(tmp_path):
    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")
    (tmp_path / "medya.json").write_text("{}", encoding="utf-8")
    kayit = DomainRegistry(
        (
            DomainAdapter(
                name="blender",
                marker="sahne.blend",
                gates=("blender --background --quit", "ortak-kontrol"),
            ),
            DomainAdapter(
                name="medya", marker="medya.json", gates=("ffprobe cikti.mp4", "ortak-kontrol")
            ),
        )
    )

    assert kayit.gate_commands(tmp_path) == (
        "blender --background --quit",
        "ortak-kontrol",
        "ffprobe cikti.mp4",
    )


def test_calistirilamayan_projede_kurulum_kapisi_secilir(tmp_path):
    """Hazırlık yalnız çalıştırılabilir projede ve davranış kapısından ÖNCE gelir."""
    durum = {"hazir": False}
    adaptor = DomainAdapter(
        name="blender",
        marker="sahne.blend",
        gates=("blender --render",),
        setup_gates=("blender --version",),
        is_runnable=lambda kok: durum["hazir"],
        preparation=lambda kok: ("blender --hazirla",),
    )

    assert adaptor.gate_commands(tmp_path) == ("blender --version",)

    durum["hazir"] = True

    assert adaptor.gate_commands(tmp_path) == ("blender --hazirla", "blender --render")


def test_cikti_isaretleri_yalniz_calistirilabilir_adi_olan_alandan_gelir():
    kayit = DomainRegistry(
        (
            DomainAdapter(
                name="blender",
                marker="sahne.blend",
                executable="blender",
                output_failure_markers=("error: python",),
            ),
            DomainAdapter(name="web", marker="index.html", output_failure_markers=("uncaught",)),
        )
    )

    assert kayit.output_failure_markers() == (ToolFailureMarkers("blender", ("error: python",)),)


def test_artifact_denetimi_isaret_yokken_de_uzantiyla_calisir(tmp_path):
    cagrilar: list[object] = []

    def denetim(kok):
        cagrilar.append(kok)
        return ("çıktı eksik",)

    kayit = DomainRegistry(
        (
            DomainAdapter(
                name="medya",
                marker="medya.json",
                artifact_suffixes=(".mp4",),
                artifact_checks=(denetim,),
            ),
        )
    )

    assert kayit.artifact_findings(tmp_path) == ()
    assert cagrilar == []

    (tmp_path / "klip").mkdir()
    (tmp_path / "klip" / "a.mp4").write_bytes(b"x")

    assert kayit.artifact_findings(tmp_path) == ("çıktı eksik",)


def test_kabul_kosullari_kokten_ya_da_gorevde_kelime_olarak_gecen_alandan_gelir(tmp_path):
    kayit = DomainRegistry(
        (
            DomainAdapter(
                name="blender",
                marker="sahne.blend",
                criteria=("render dosyası üretildi",),
                task_markers=("blender",),
            ),
        )
    )

    assert kayit.acceptance_criteria(tmp_path, "bir logo çiz") == ()
    assert kayit.acceptance_criteria(tmp_path, "Blender'da sahne kur") == (
        "render dosyası üretildi",
    )
    assert kayit.acceptance_criteria(tmp_path, "blenderbot ile konuş") == ()

    (tmp_path / "sahne.blend").write_text("", encoding="utf-8")

    assert kayit.acceptance_criteria(tmp_path, "bir logo çiz") == ("render dosyası üretildi",)


def test_teslimatlar_tum_alanlardan_ad_tekrarsiz_toplanir():
    render = Deliverable(
        name="render",
        request_markers=("render",),
        plan_markers=("render",),
        instruction="render dosyasını üreten ayrı bir adım",
    )
    kayit = DomainRegistry(
        (
            DomainAdapter(name="a", marker="a.x", deliverables=(render,)),
            DomainAdapter(name="b", marker="b.x", deliverables=(render,)),
        )
    )

    assert kayit.deliverables() == (render,)


def test_ayni_adli_iki_alan_reddedilir():
    with pytest.raises(FusionError, match="blender"):
        DomainRegistry(
            (
                DomainAdapter(name="blender", marker="a.blend"),
                DomainAdapter(name="blender", marker="b.blend"),
            )
        )


def test_adaptor_sozlesmesi_plan_ve_onaya_kanca_vermez():
    """Adaptör YALNIZ kanıt sözleşmesidir.

    Plan yürütmesine, onaya veya bütçeye kanca eklemek bu testi bilinçli olarak
    değiştirmeyi gerektirir: bir alanın ortak güvenlik politikasını ezmesi sessizce
    mümkün olmamalı (master belge §14 Faz 1).
    """
    assert {alan.name for alan in fields(DomainAdapter)} == {
        "name",
        "marker",
        "gates",
        "setup_gates",
        "is_runnable",
        "preparation",
        "executable",
        "output_failure_markers",
        "criteria",
        "task_markers",
        "artifact_suffixes",
        "artifact_checks",
        "deliverables",
    }
