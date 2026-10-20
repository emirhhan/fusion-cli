"""`fusion paperclip`: Paperclip heartbeat'inden görev kurma; anahtar göreve sızmaz."""

from __future__ import annotations

import pytest

from fusion_cli.cli.paperclip_command import PaperclipEnvError, heartbeat_task

_ORTAM = {
    "PAPERCLIP_API_URL": "http://127.0.0.1:3100",
    "PAPERCLIP_API_KEY": "gizli-calisma-jetonu",
    "PAPERCLIP_RUN_ID": "run-1",
    "PAPERCLIP_TASK_ID": "ISS-42",
    "PAPERCLIP_WAKE_REASON": "issue_assigned",
    "PAPERCLIP_AGENT_ID": "fusion",
}


def test_gorev_uyanma_bilgisini_tasir_anahtari_tasimaz():
    gorev = heartbeat_task(_ORTAM)

    assert "PAPERCLIP_TASK_ID: ISS-42" in gorev
    assert "issue_assigned" in gorev
    assert "read_skill" in gorev and "paperclip" in gorev
    assert "gizli-calisma-jetonu" not in gorev
    assert "$PAPERCLIP_API_KEY" in gorev


def test_atanmis_is_yoksa_gelen_kutusuna_yonlendirir():
    gorev = heartbeat_task({k: v for k, v in _ORTAM.items() if k != "PAPERCLIP_TASK_ID"})

    assert "PAPERCLIP_TASK_ID" not in gorev


def test_paperclip_disinda_anlasilir_hata():
    with pytest.raises(PaperclipEnvError, match="PAPERCLIP_API_KEY"):
        heartbeat_task({"PAPERCLIP_API_URL": "http://x"})
