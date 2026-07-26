"""Kurulumun gerçekten kullanılabilir olup olmadığı.

`detect().any_configured` yeterli DEĞİLDİR: bir anahtarın varlığı, o anahtarla
zorunlu rollerin (agent, hakem, en az bir aday) çalışabileceği anlamına gelmez.
Kullanıcıya "kurulum tamam" demenin ölçütü rollerin çalışabilirliğidir.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.config.keys import ProviderKeys
from fusion_cli.config.loader import load_config
from fusion_cli.config.readiness import Readiness, evaluate
from fusion_cli.core.types import ModelSpec


def test_iki_anahtar_da_varsa_hazir():
    rapor = evaluate(load_config(), ProviderKeys(openrouter=True, nim=True))

    assert rapor.state is Readiness.READY
    assert rapor.agent_ok and rapor.judge_ok and rapor.candidates_ok
    assert not rapor.reasons


def test_hic_anahtar_yoksa_hazir_degil():
    rapor = evaluate(load_config(), ProviderKeys(openrouter=False, nim=False))

    assert rapor.state is Readiness.NOT_READY
    assert rapor.reasons, "sebep yazılmadan 'hazır değil' denmez"


def test_yalniz_openrouter_ile_hazir():
    """OpenRouter ürünün taban çizgisidir: her rolde en az bir OpenRouter modeli var."""
    rapor = evaluate(load_config(), ProviderKeys(openrouter=True, nim=False))

    assert rapor.state is Readiness.READY


def test_yalniz_nim_gercek_yapilandirmaya_gore_degerlendirilir():
    """NIM tek başına yeterliyse 'hazır' denir; değilse sebebiyle söylenir.

    Karar varsayımla değil, ETKİN yapılandırmadaki zincirlere bakılarak verilir.
    """
    config = load_config()
    rapor = evaluate(config, ProviderKeys(openrouter=False, nim=True))

    nim_agent = any(m.startswith("nvidia_nim/") for m in config.agent.models)
    assert (rapor.state is Readiness.READY) == (nim_agent and rapor.judge_ok)


def test_yerel_saglayici_kullanan_engellenmez():
    """Ollama/vLLM kullanan ileri kullanıcı anahtarsız da çalışabilmeli."""
    yerel = ModelSpec(name="yerel", model="ollama/qwen2.5-coder:7b")
    config = replace(load_config(), agent=yerel, judge=yerel, candidates=(yerel,))

    rapor = evaluate(config, ProviderKeys(openrouter=False, nim=False))

    assert rapor.state is Readiness.READY


def test_agent_calisiyor_ama_hakem_calismiyorsa_kismen_hazir():
    """Tur çalışır ama fusion motoru hakemsiz kalır; bu 'tamam' değildir."""
    config = load_config()
    yerel = ModelSpec(name="yerel", model="ollama/x")
    kirik = ModelSpec(name="hakem", model="openrouter/yok:free")
    ozel = replace(config, agent=yerel, judge=kirik, candidates=(yerel,))

    rapor = evaluate(ozel, ProviderKeys(openrouter=False, nim=False))

    assert rapor.state is Readiness.PARTIALLY_READY
    assert any("hakem" in sebep.lower() for sebep in rapor.reasons)


def test_agent_calismiyorsa_hazir_degil():
    config = load_config()
    kirik = ModelSpec(name="agent", model="openrouter/yok:free")
    ozel = replace(config, agent=kirik)

    rapor = evaluate(ozel, ProviderKeys(openrouter=False, nim=False))

    assert rapor.state is Readiness.NOT_READY


def test_sebepler_anahtar_degeri_icermez():
    """Hiçbir tanı çıktısı anahtarın kendisini göstermez."""
    rapor = evaluate(load_config(), ProviderKeys(openrouter=False, nim=False))

    birlesik = " ".join(rapor.reasons)
    assert "sk-" not in birlesik and "nvapi-" not in birlesik
