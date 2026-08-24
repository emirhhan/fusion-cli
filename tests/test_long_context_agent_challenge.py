"""Uzun bağlamlı (long-context) karmaşık proje görevleri için agent doğrulama testi.

Claude Code ve Antigravity seviyesindeki çok dosyalı, çok adımlı proje geliştirme ve
yeniden yapılandırma senaryolarını test eder.
"""

from __future__ import annotations

from fusion_cli.core.types import Message
from fusion_cli.engines.agent import history
from fusion_cli.engines.agent.history import (
    COMPRESS_THRESHOLD_CHARS,
    WEB_COMPRESS_THRESHOLD_CHARS,
    needs_compression,
    safe_cut,
    transcript,
)
from fusion_cli.providers.web_browser import trim_to_prompt_budget


def test_long_context_web_threshold_trigger() -> None:
    """Web provider aktifken 24.000 karakteri aşan mesajlar sıkıştırmaya yönlendirilmeli."""
    history_messages = [
        Message(
            "user",
            "5 modüllü büyük bir API projesini refactor et: "
            "database, service, router, middleware, config.",
        ),
        Message("assistant", "Anladım. Önce dosyaları okuyarak işe başlıyorum."),
        Message("tool", "def database_connect():\n" + "    pass  # connect logic\n" * 450),
        Message("assistant", "Şimdi service.py ve router.py okuyorum."),
        Message("tool", "class Service:\n" + "    def process(self):\n        return True\n" * 450),
        Message("assistant", "Middleware ve config okundu."),
        Message(
            "tool",
            "MIDDLEWARE_CONFIG = {\n"
            + '    "auth_middleware_enabled": True,\n' * 350
            + "}\n",
        ),
    ]

    # Karakter sayısı > WEB_COMPRESS_THRESHOLD_CHARS (24.000)
    assert history.total_chars(history_messages) >= WEB_COMPRESS_THRESHOLD_CHARS
    assert needs_compression(history_messages, threshold_chars=WEB_COMPRESS_THRESHOLD_CHARS)
    # Standart API eşiğini (177.000) henüz aşmamış olmalıdır
    assert not needs_compression(history_messages, threshold_chars=COMPRESS_THRESHOLD_CHARS)


def test_safe_cut_preserves_user_boundaries_in_long_history() -> None:
    """Uzun geçmiş kesilirken araç çağrısı ile sonucu ayrılmamalı, kullanıcı sınırına kaymalıdır."""
    history_messages = [
        Message("user", "İlk görev: database.py oluştur"),
        Message("assistant", "Yazıyorum..."),
        Message("tool", "oluşturuldu: database.py"),
        Message("user", "İkinci görev: service.py oluştur"),
        Message("assistant", "Yazıyorum..."),
        Message("tool", "oluşturuldu: service.py"),
        Message("user", "Üçüncü görev: test_service.py yaz ve testleri çalıştır"),
        Message("assistant", "Yazıyorum..."),
        Message("tool", "oluşturuldu: test_service.py"),
    ]

    cut_idx = safe_cut(history_messages, keep_recent=4)
    # Kesim noktası bir 'user' mesajına denk gelmelidir (orphan tool engeli)
    assert cut_idx > 0
    assert history_messages[cut_idx].role == "user"


def test_trim_to_prompt_budget_line_boundary_safety() -> None:
    """Prompt bütçesi aşıldığında kırpma satır sınırlarına hizalanmalı ve yapıyı bozmamalıdır."""
    long_content = "LINE_" + "x" * 80 + "\n"
    prompt = (
        "### FUSION//SİSTEM\nBaşlangıç talimatı\n\n"
        + (long_content * 500)
        + "### FUSION//GÖREV\nAsıl görev metni"
    )

    trimmed = trim_to_prompt_budget(prompt)

    assert len(trimmed) <= 30_000
    assert "KIRPILDI" in trimmed
    assert "### FUSION//GÖREV" in trimmed
    assert "Asıl görev metni" in trimmed


def test_transcript_formatting_in_multi_file_long_history() -> None:
    """Uzun araç çıktılarında denetim transkripti sonda kalan kritik bilgileri korumalıdır."""
    messages = [
        Message("user", "Projedeki tüm hataları tarayıp düzelt"),
        Message(
            "tool",
            "HATA: service.py:L45 - AttributeError: 'NoneType' object has no attribute 'connect'",
        ),
        Message("assistant", "Düzeltme yapıyorum."),
        Message("tool", "düzenlendi: service.py (1 değişiklik)"),
        Message("tool", "PASSED: test_service.py::test_connect"),
    ]

    trace_str = transcript(messages, limit=1000)

    assert "service.py" in trace_str
    assert "test_service.py" in trace_str
