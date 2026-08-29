"""Native kontrol panelinin sır sızdırmayan protokol sözleşmesi."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


class _MemorySecrets:
    available = True

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def list_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.values))

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def delete(self, name: str) -> bool:
        return self.values.pop(name, None) is not None


async def _request(session: AppSession, lines: list[str], name: str, data: dict[str, object]):
    await session.handle(Request(id=name, name=name, data=data))
    return json.loads(lines[-1])["veri"]


async def test_kontrol_durumu_model_izin_gateway_ve_sir_adlarini_guvenli_dondurur(
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "home")
    secrets = _MemorySecrets()
    secrets.set("OPENROUTER_API_KEY", "sk-cok-gizli-deger")
    session._secret_store = secrets  # type: ignore[assignment]

    result = await _request(session, lines, "kontrol.durum", {})
    await session.close()

    encoded = json.dumps(result)
    assert result["ok"] is True
    assert result["model"]["agent"]
    assert result["izin"]["mod"] in {"ask", "auto", "plan"}
    assert result["gateway"]["durum"] == "kapali"
    assert any(item["id"] == "openrouter" and item["kurulu"] for item in result["saglayicilar"])
    assert "sk-cok-gizli-deger" not in encoded


async def test_kontrol_anahtar_kaydeder_ama_degeri_yanitlamaz(tmp_path: Path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "home")
    secrets = _MemorySecrets()
    session._secret_store = secrets  # type: ignore[assignment]
    secret = "sk-test-asla-geri-donmemeli"

    result = await _request(
        session,
        lines,
        "kontrol.anahtar_kaydet",
        {"saglayici": "openrouter", "deger": secret},
    )
    invalid = await _request(
        session,
        lines,
        "kontrol.anahtar_kaydet",
        {"saglayici": "bilinmeyen", "deger": secret},
    )
    await session.close()

    assert result == {"ok": True, "saglayici": "openrouter", "kurulu": True}
    assert secrets.values["OPENROUTER_API_KEY"] == secret
    assert secret not in json.dumps(result) and secret not in lines[-2]
    assert invalid["ok"] is False


async def test_kontrol_anahtar_siler_ve_gateway_yasam_dongusunu_yonetir(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "home")
    secrets = _MemorySecrets()
    secrets.set("OPENROUTER_API_KEY", "secret")
    session._secret_store = secrets  # type: ignore[assignment]

    deleted = await _request(
        session, lines, "kontrol.anahtar_sil", {"saglayici": "openrouter"}
    )
    # Gerçek gateway yerine kısa ömürlü, zararsız bir süreçle yaşam döngüsü kanıtlanır.
    session._gateway_command = "python3 -c 'import time; time.sleep(10)'"
    started = await _request(session, lines, "kontrol.gateway_baslat", {})
    duplicate = await _request(session, lines, "kontrol.gateway_baslat", {})
    stopped = await _request(session, lines, "kontrol.gateway_durdur", {})
    await session.close()

    assert deleted == {"ok": True, "saglayici": "openrouter", "kurulu": False}
    assert started["ok"] is True and started["durum"] == "calisiyor"
    assert duplicate["ok"] is False
    assert stopped["ok"] is True and stopped["durum"] in {"durduruldu", "tamamlandi"}
