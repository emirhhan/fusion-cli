"""Takip turu, açık sohbetin ÜSTÜNE gelir; sohbeti sıfırdan kurmaz.

Ölçüldü (canlı iz, `devam=False`): öz-denetim düzeltici turu ve TUI'deki her
takip mesajı yeni bir tarayıcı sohbeti açıyor ve geçmişin tamamını tek düz metin
olarak yeniden gönderiyordu. Sebep `_initial_messages`: geçmiş her zaman bir
önceki turun `outcome.messages` listesidir ve zaten bir sistem mesajıyla başlar,
ama başına bir tane daha ekleniyordu — liste `[system, system, user, …]` oluyor,
gönderilmiş önek kayıyor ve `_deliver_turn` sohbeti sürdüremiyordu.

Zararı projenin kendi ölçümünde yazılı (`ConversationState` docstring'i): sohbet
sıfırlanınca model geçmişi kendi hafızası değil bir döküm gibi okuyor ve aynı
araç çağrılarını yeniden üretiyor. Canlı koşuda tam olarak bu oldu: düzeltici tur
dizini baştan listeledi, 1388 satırlık dosyayı yeniden okudu ve asıl görevi
kaybetti — üstelik öz-denetimin verdiği geri bildirim DOĞRUYDU.
"""

from __future__ import annotations

from fusion_cli.core.types import Message
from fusion_cli.engines.agent.loop import _initial_messages
from fusion_cli.providers.web_browser import conversation_digest


def _biten_tur(extra_system: str = "dersler") -> list[Message]:
    ilk = _initial_messages("asıl görev", None, plan_mode=False, extra_system=extra_system)
    return [*ilk, Message("assistant", "araç çağrısı"), Message("tool", "araç sonucu")]


def test_gecmis_verilince_tek_sistem_mesaji_kalir() -> None:
    mesajlar = _initial_messages(
        "takip görevi", _biten_tur(), plan_mode=False, extra_system="dersler"
    )

    assert [m.role for m in mesajlar] == ["system", "user", "assistant", "tool", "user"]


def test_takip_turu_acik_sohbeti_surdurebilir() -> None:
    """`_deliver_turn`'ün sürdürme koşulları: önek DEĞİŞMEMİŞ ve liste UZAMIŞ."""
    onceki = _biten_tur()
    mesajlar = _initial_messages("takip görevi", onceki, plan_mode=False, extra_system="dersler")

    gonderilmis = len(onceki)
    assert conversation_digest(mesajlar[:gonderilmis]) == conversation_digest(onceki)
    assert 0 < gonderilmis < len(mesajlar)


def test_sistem_metni_degisirse_sohbet_bilincli_olarak_sifirlanir() -> None:
    """Plan kipi açıldıysa model artık başka talimatlarla çalışıyordur."""
    onceki = _biten_tur()
    mesajlar = _initial_messages("takip görevi", onceki, plan_mode=True, extra_system="dersler")

    assert conversation_digest(mesajlar[: len(onceki)]) != conversation_digest(onceki)


def test_tur_ici_sistem_notlari_korunur() -> None:
    """Araya giren sistem notu konuşmanın parçasıdır; atılırsa önek yine kayar."""
    onceki = [*_biten_tur(), Message("system", "değişen dosyalar: a.py")]

    mesajlar = _initial_messages("takip", onceki, plan_mode=False, extra_system="dersler")

    assert [m.role for m in mesajlar] == [
        "system",
        "user",
        "assistant",
        "tool",
        "system",
        "user",
    ]
    assert conversation_digest(mesajlar[: len(onceki)]) == conversation_digest(onceki)


def test_ic_tur_sistem_metnini_gecmisten_miras_alir() -> None:
    """İç düzeltici tur, sistem metnini YENİDEN HESAPLAMAZ.

    Ölçüldü (canlı iz, `devam=False`): sistem mesajının çiftlenmesi çözüldükten
    SONRA da sohbet düşmeye devam etti. Sebep şu: `run_agent` her çağrıda
    dersleri ve uzmanlık talimatını O TURUN metnine göre hatırlıyor. Düzeltici
    turun metni ("şunları düzelt: …") asıl görevden farklıdır, dolayısıyla
    hatırlanan blok da farklı çıkıyor ve sistem metni değişiyor. Değişen sistem
    metni öneki kaydırır, `_deliver_turn` sohbeti sürdüremez.

    Düzeltici tur AYNI konuşmanın devamıdır: model zaten o talimatlarla
    çalışıyor, talimatı ortasından değiştirmenin bir gerekçesi yok.
    """
    onceki = _biten_tur("asıl turda hatırlanan dersler")

    mesajlar = _initial_messages(
        "şunları düzelt: …",
        onceki,
        plan_mode=False,
        extra_system="düzeltici turda hatırlanan BAŞKA dersler",
        inherit_system=True,
    )

    assert mesajlar[0].content == onceki[0].content
    assert conversation_digest(mesajlar[: len(onceki)]) == conversation_digest(onceki)


def test_ic_tur_sistemsiz_gecmiste_metni_hesaplar() -> None:
    """Miras alınacak bir sistem mesajı yoksa tur promtsuz kalmaz."""
    onceki = [Message("user", "merhaba"), Message("assistant", "selam")]

    mesajlar = _initial_messages(
        "düzelt", onceki, plan_mode=False, extra_system="dersler", inherit_system=True
    )

    assert mesajlar[0].role == "system"
    assert "dersler" in mesajlar[0].content


def test_dis_tur_sistem_metnini_miras_almaz() -> None:
    """Kullanıcının yeni mesajı yeni bir görevdir; dersleri yeniden hatırlanır."""
    onceki = _biten_tur("asıl turda hatırlanan dersler")

    mesajlar = _initial_messages(
        "yeni görev", onceki, plan_mode=False, extra_system="yeni dersler"
    )

    assert "yeni dersler" in mesajlar[0].content


def test_gecmis_yoksa_sistem_mesaji_yine_eklenir() -> None:
    mesajlar = _initial_messages("görev", None, plan_mode=False, extra_system="")

    assert [m.role for m in mesajlar] == ["system", "user"]


def test_sistemsiz_gecmis_de_desteklenir() -> None:
    """Geçmiş sistem mesajıyla başlamıyorsa hiçbir şey düşürülmez."""
    onceki = [Message("user", "merhaba"), Message("assistant", "selam")]

    mesajlar = _initial_messages("görev", onceki, plan_mode=False, extra_system="")

    assert [m.role for m in mesajlar] == ["system", "user", "assistant", "user"]


def test_web_compression_threshold() -> None:
    from fusion_cli.engines.agent.history import (
        WEB_COMPRESS_THRESHOLD_CHARS,
        needs_compression,
    )

    kisa_mesajlar = [Message("user", "x" * 15_000), Message("assistant", "y" * 5_000)]
    uzun_web_mesajlar = [Message("user", "x" * 15_000), Message("assistant", "y" * 10_000)]

    assert not needs_compression(kisa_mesajlar, threshold_chars=WEB_COMPRESS_THRESHOLD_CHARS)
    assert needs_compression(uzun_web_mesajlar, threshold_chars=WEB_COMPRESS_THRESHOLD_CHARS)
    # 25.000 karakter standart 177.000 karakterlik API eşiğini aşmaz
    assert not needs_compression(uzun_web_mesajlar)

