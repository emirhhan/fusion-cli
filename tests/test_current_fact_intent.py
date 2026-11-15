"""Changing facts require source evidence even when phrased as ordinary questions."""

import pytest

from fusion_cli.engines.effects.detect import required_effect_for


@pytest.mark.parametrize(
    "task",
    [
        "Python’ın en son kararlı sürümü nedir?",
        "What is the latest stable version of Python?",
        "Bugün dolar kaç TL?",
        "Şu anda euro kuru kaç?",
        "Bugünkü hava durumu nasıl?",
        "Türkiye'nin cumhurbaşkanı kim?",
        "Who is the CEO of Microsoft?",
        "Türkiye’nin cumhurbaşkanı kimdir?",
        "Microsoft CEO’su kimdir?",
        "Güncel Node.js sürümünü kaynakla birlikte söyle.",
        "Python'ın güncel sürümünü açıkla.",
        "https://www.python.org/downloads/ sayfasındaki en son kararlı sürüm nedir?",
        "Bugünkü haberleri özetle.",
        "What is the current price of gold?",
        "Kasım 2026 itibarıyla Python'ın son sürümü hangisi?",
    ],
)
def test_current_fact_question_requires_web_evidence(task):
    assert required_effect_for(task) == "web_lookup"


@pytest.mark.parametrize(
    "task",
    [
        "Python nedir?",
        "Kararlı sürüm ne demek?",
        "En son mesajımı özetle.",
        "Güncel değişiklikleri git diff ile göster.",
        "Dosyadaki son satırı oku.",
        "Bugün ne yapmak istersin?",
        "Döviz kuru nedir, nasıl hesaplanır?",
        "HTTP cache-control max-age nasıl çalışır?",
        "What is an exchange rate?",
        "Bir README dosyası oluştur; Node.js'in güncel sürümünü kullan.",
        "README.md dosyasındaki son sürüm nedir?",
        "Dosyadaki güncel fiyatı oku.",
        "En son konuştuğumuz Python sürümünü hatırlıyor musun?",
        'Şu metni çevir: "What is the latest stable version of Python?"',
        '"Python’ın en son kararlı sürümü nedir?" cümlesini İngilizceye çevir.',
        '"Güncel sürüm" ne demek?',
        '"Güncel Python sürümünü araştır" ne demek?',
        "Bugün bana yazdığın haber metnini kısalt.",
        "Güncel release notlarını yerel CHANGELOG.md dosyasından oku.",
        "Bugün Python öğrendim. Sürüm kavramını açıkla.",
        "Bugün öğrendiğim döviz kuru kavramını açıkla.",
        "Explain the concept of the current exchange rate.",
    ],
)
def test_current_fact_detection_preserves_other_task_intents(task):
    assert required_effect_for(task) != "web_lookup"


def test_unrelated_local_clause_does_not_suppress_current_fact_question():
    assert required_effect_for("README.md dosyasını oku. Bugün dolar kaç TL?") == "web_lookup"


def test_source_lookup_does_not_override_explicit_no_tools():
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.engines.agent.execution_policy import policy_for
    from tests.fakes import make_config

    policy = policy_for(
        make_config(),
        ModelSpec(name="test", model="fake/test"),
        "Araç kullanma. Python'ın en son kararlı sürümü nedir?",
    )
    assert not policy.offer_tools
    assert policy.requires_tool_evidence
    assert policy.max_evidence_reprompts == 0
