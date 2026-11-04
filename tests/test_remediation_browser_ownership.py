"""Seçili tarayıcı ve bekleyen onayın sahipliği kaybolmaz."""

from __future__ import annotations

import pytest

from fusion_cli.appserver.chrome_bridge import FEED_LIMIT, ChromeBridge
from fusion_cli.appserver.chrome_devices import BrowserChoiceRequiredError, BrowserDevices


def test_selected_disconnected_browser_never_routes_to_other_account():
    devices = BrowserDevices()
    devices.touch("work", "İş")
    devices.touch("personal", "Kişisel")
    devices.select("work")
    devices.forget("work")
    with pytest.raises(BrowserChoiceRequiredError):
        devices.target()
    assert not any(device["inUse"] for device in devices.describe())
    devices.select("personal")
    assert devices.target().device_id == "personal"


def test_unselected_single_browser_remains_usable():
    devices = BrowserDevices()
    devices.touch("only", "Chrome")
    assert devices.target().device_id == "only"


def test_pending_question_snapshot_survives_feed_eviction_and_clears_on_close():
    bridge = ChromeBridge()
    question = {"tur": "soru", "id": "q1", "veri": {"tur": "onay", "baslik": "Gönderilsin mi?"}}
    bridge.publish(question)
    for _ in range(FEED_LIMIT + 1):
        bridge.publish({"tur": "dusunuyor"})
    assert bridge.status()["sorular"] == [question]
    bridge.publish({"tur": "soru_kapandi", "id": "other"})
    assert bridge.status()["sorular"] == [question]
    bridge.publish({"tur": "soru_kapandi", "id": "q1"})
    assert bridge.status()["sorular"] == []


def test_rejected_answer_returns_actionable_reason_and_preserves_question():
    bridge = ChromeBridge(on_answer=lambda _identifier, _answer: False)
    bridge.publish({"tur": "soru", "id": "q1", "veri": {"tur": "onay"}})
    rejected = bridge._answer({"id": "q1", "veri": {"secim": "evet"}})
    assert not rejected["ok"]
    assert rejected.get("hata")
    assert bridge.status()["sorular"][0]["id"] == "q1"
