"""Araya girme gerçek tur akışına bağlı.

Kuyruk tek başına işe yaramaz: yönerge bir sonraki model çağrısından ÖNCE mesaj
listesine girmeli ve yalnız bir kez girmeli.
"""

from __future__ import annotations

from fusion_cli.core.steering import SteeringQueue
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.loop import apply_steering


def test_yonerge_mesaj_listesine_eklenir():
    kuyruk = SteeringQueue()
    kuyruk.push("testleri de çalıştır")
    messages = [Message("user", "görev")]

    eklendi = apply_steering(messages, kuyruk)

    assert eklendi == 1
    assert "testleri de çalıştır" in messages[-1].content
    assert messages[-1].harness_note is True


def test_yonerge_yoksa_liste_degismez():
    messages = [Message("user", "görev")]

    assert apply_steering(messages, SteeringQueue()) == 0
    assert len(messages) == 1


def test_kuyruk_yoksa_akis_bozulmaz():
    messages = [Message("user", "görev")]

    assert apply_steering(messages, None) == 0


def test_ayni_yonerge_iki_kez_eklenmez():
    kuyruk = SteeringQueue()
    kuyruk.push("dur")
    messages = [Message("user", "görev")]

    apply_steering(messages, kuyruk)
    ikinci = apply_steering(messages, kuyruk)

    assert ikinci == 0
    assert len(messages) == 2
