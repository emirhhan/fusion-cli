"""Sistem istemleri kendi içinde ve birbiriyle çelişmemeli (Z1-01..Z1-05).

Ölçüldü (30 Ekim): zayıf modeller çelişen iki talimat arasında dalgalanır ya da
şema örneğindeki seçenek metnini (`discovery | execution`) birebir kopyalar.
Bu testler istem dosyalarının yapısını sabitler; davranış ölçümü canlı modele
bağlı olduğundan metin sözleşmesi olarak okunur.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fusion_cli.engines.agent.plan_parser import parse_execution_plan

PROMPTS = Path(__file__).resolve().parents[1] / "src/fusion_cli/engines/agent/prompts"


def _oku(ad: str) -> str:
    return (PROMPTS / ad).read_text(encoding="utf-8")


def test_system_md_tek_dil_kurali_tasir() -> None:
    """Z1-01: 'kullanıcının dilinde yaz' ile 'yalnız Latin harfleriyle' çelişiyordu."""
    for ad in ("system.md", "system_chat.md"):
        metin = _oku(ad)
        assert "Latin harf" not in metin, ad
        assert metin.count("dilinde yaz") == 1, ad
        assert metin.count("alfabe") == 1, ad
        assert "karıştırma" in metin


def test_ilerleme_anlatimi_system_ve_api_arasinda_celismez() -> None:
    """Z1-02: system.md 'her aşamadan sonra', system_api.md 'her araçtan sonra yazma' diyordu."""
    system = _oku("system.md")
    api = _oku("system_api.md")

    assert "her aşamadan sonra TEK satır" not in system
    # Hangi katmanın iletişim kuralında söz sahibi olduğu açık yazılmalı.
    assert "çelişirse yukarıdaki kurallar geçerlidir" not in api.replace("\n", " ")
    assert "ilerleme anlatımında" in api.split("# Konuşma biçimi")[0].lower()


def test_fusion_bilgi_araci_olmayan_modele_her_seyi_vaat_etmez() -> None:
    """Z1-03: araçsız modele 'aynı yeteneklere sahipsin' demek uydurma araç çağrısı doğurur."""
    metin = _oku("fusion_bilgi.md")

    assert "aynı araçlara ve aynı yeteneklere" not in metin
    assert "görünmeyeni" in metin


def _plan_ornegi() -> str:
    metin = _oku("execution_plan.md")
    blok = re.search(r"Örnek plan[^\n]*\n(\{.*?\n\})\n", metin, flags=re.DOTALL)
    assert blok is not None, "tek geçerli örnek plan bulunamadı"
    return blok.group(1)


def test_plan_ornegi_secenek_metni_icermez_ve_ayristirilir() -> None:
    """Z1-04: örnekte seçenek metni olmamalı; olduğu gibi kopyalansa geçerli olmalı."""
    ornek = _plan_ornegi()

    assert " | " not in ornek
    plan = parse_execution_plan(ornek.replace("{task}", "x"))
    assert len(plan.steps) == 2
    assert {s.phase.value for s in plan.steps} == {"discovery", "execution"}
    json.loads(ornek)


def test_plan_istemi_izin_verilen_degerleri_ayri_satirda_verir() -> None:
    metin = _oku("execution_plan.md")

    assert "İzin verilen değerler" in metin
    for deger in ("discovery", "execution", "file_exists", "observe_first"):
        assert deger in metin.split("İzin verilen değerler")[1]


def test_plan_istemi_kisa_kosul_kimligi_ister() -> None:
    """Z1-05: `criterion_id` birebir metin değil `c1`, `c2`... olmalı."""
    metin = _oku("execution_plan.md")

    assert "birebir" not in metin.split("Kurallar:")[0]
    assert '"criterion_id": "c1"' in _plan_ornegi()
    assert "c1" in metin and "c2" in metin
