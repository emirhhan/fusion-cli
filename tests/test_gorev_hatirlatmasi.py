"""Promptun "GÖREV (yapılacak iş budur)" bloğu KULLANICININ görevini taşır.

Ölçüldü: devam turlarında bu blok kullanıcının görevini değil harness'ın kendi
uyarı notunu gösteriyordu. Sebep zincir halinde:

  - `_deliver_turn` devam kipinde yalnızca `messages[state.sent_count:]` dilimini
    biçimlendiriyor (gönderilmemiş yeni mesajlar).
  - O dilimde kullanıcının görevi YOKTUR; içindeki tek `role="user"` mesajı
    refleksiyon notudur (`[eylem-kanıtı-zorunlu]`, `[dur-ve-yap]` gibi).
  - `_task_reminder` "son user mesajı" diye o notu alıyordu.

Sonuç: modele, promptun en çok bakılan yerinde, "yapılacak iş budur" başlığıyla
harness'ın azar notu veriliyordu. Refleksiyon notu olmayan devam turlarında ise
blok tamamen boş kalıyor ve görev hiç hatırlatılmıyordu. Canlı koşuda model üç
tur boyunca "somut bir görev almadım" dedi.

Ayırt etme metinden TAHMİN EDİLMEZ: notu üreten taraf `harness_note` alanını
doldurur (`Message.ok` alanındaki ilkenin aynısı).
"""

from __future__ import annotations

from fusion_cli.core.types import Message
from fusion_cli.engines.agent import reflexion
from fusion_cli.providers.web_browser import _task_reminder, format_browser_prompt


def test_harness_notu_gorev_sanilmaz() -> None:
    mesajlar = [
        Message("user", "sidebar ile içerik üst üste biniyor, düzelt"),
        Message("assistant", "bakıyorum"),
        Message("user", "[eylem-kanıtı-zorunlu] henüz değiştirici araç yok", harness_note=True),
    ]

    hatirlatma = _task_reminder(mesajlar)

    assert "sidebar ile içerik üst üste biniyor" in hatirlatma
    assert "eylem-kanıtı-zorunlu" not in hatirlatma


def test_gorev_yalnizca_harness_notu_varsa_bos_kalmaz() -> None:
    """Görev listede yoksa uydurulmaz; blok boş kalır ama NOT da yazılmaz."""
    mesajlar = [
        Message("user", "[dur-ve-yap] keşif yeterli", harness_note=True),
    ]

    assert _task_reminder(mesajlar) == ""


def test_refleksiyon_notlari_isaretli_uretilir() -> None:
    """Notu üreten taraf işaretler; ayrıştırıcı metne bakmaz."""
    uretilenler = [
        reflexion.note(persistent=False),
        reflexion.note(persistent=True),
        reflexion.auto_continue_note(),
        reflexion.asked_instead_of_acting_note(),
        reflexion.enough_exploring_note(rounds=3),
        reflexion.repeated_edit_note(count=2),
        reflexion.change_log_note(("a.py",)),
        reflexion.wrong_workspace_note(root="/x"),
        reflexion.empty_response_note(),
        reflexion.tool_evidence_required_note("write"),
        reflexion.tool_contract_repair_note("geçersiz JSON"),
    ]

    assert all(mesaj.role == "user" for mesaj in uretilenler)
    assert all(mesaj.harness_note for mesaj in uretilenler)


def test_kullanici_mesaji_isaretsizdir() -> None:
    """Varsayılan False olmalı; kullanıcı mesajı yanlışlıkla elenmesin."""
    assert Message("user", "görev").harness_note is False


def test_devam_kipinde_gorev_dilimin_disindan_gelir() -> None:
    """Devam turunda gönderilen dilimde görev YOKTUR; tam geçmişten alınmalı.

    Ölçülen hatanın ikinci yarısı: `_deliver_turn` devam kipinde yalnızca
    `messages[sent_count:]` dilimini biçimlendiriyor. Görev o dilimde olmadığı için
    hatırlatma bloğu boş kalıyor ve model görevini hiç görmüyordu.
    """
    tam_gecmis = [
        Message("system", "sistem"),
        Message("user", "sidebar hatasını düzelt"),
        Message("assistant", "bakıyorum"),
        Message("tool", "dosya içeriği"),
    ]
    yeni_dilim = tam_gecmis[3:]

    prompt = format_browser_prompt(yeni_dilim, continuation=True, full_history=tam_gecmis)

    assert "sidebar hatasını düzelt" in prompt
