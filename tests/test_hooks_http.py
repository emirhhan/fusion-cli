"""`type: "http"` kancası (P-009): POST, karar sözleşmesi, başlık ortamı, iç ağ koruması.

Ölçüldü (1 Kasım): yalnız `command` türü vardı; `http` tanımı "tür desteklenmiyor" diye
atlanıyordu. Testler ağa çıkmaz: `pinned_http.direct_async_transport` sahte taşımadır.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from fusion_cli.config.hooks import hook_rows, parse_hooks_block
from fusion_cli.core.hooks.events import HTTP_HANDLER, HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.http_runner import expand_header
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.tools import pinned_http

#: Literal genel IP: ad çözümlemesi (ağ) yapılmaz.
GENEL_URL = "https://93.184.216.34/kanca"


@pytest.fixture
def istekler(monkeypatch):
    """Sahte sunucu: gelen istekleri kaydeder, `yanit` sözlüğündeki cevabı döner."""
    kayit: list[httpx.Request] = []
    yanit = {"durum": 200, "govde": ""}

    def _isle(request: httpx.Request) -> httpx.Response:
        kayit.append(request)
        return httpx.Response(yanit["durum"], text=yanit["govde"])

    monkeypatch.setattr(
        pinned_http, "direct_async_transport", lambda _host: httpx.MockTransport(_isle)
    )
    monkeypatch.setenv("KANCA_ANAHTARI", "gizli-123")
    monkeypatch.setenv("BASKA_SIR", "sizmamali")
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    return kayit, yanit


def _http(url: str = GENEL_URL, event: HookEvent = HookEvent.PRE_TOOL_USE, **extra) -> HookCommand:
    return HookCommand(event, "", url, 5.0, "test", "", HTTP_HANDLER, **extra)


def _oturum(tmp_path: Path, *commands: HookCommand, ozel: bool = False) -> HookSession:
    return HookSession(
        root=tmp_path,
        loader=lambda: HookSet(tuple(commands)),
        http_allow_private=lambda: ozel,
    )


def test_http_tanimi_okunur_gecersiz_adres_ve_diger_turler_gerekceyle_atlanir():
    commands, skipped = parse_hooks_block(
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "http",
                            "url": GENEL_URL,
                            "headers": {"Authorization": "Bearer $KANCA_ANAHTARI"},
                            "allowedEnvVars": ["KANCA_ANAHTARI"],
                            "timeout": 7,
                        },
                        {"type": "http", "url": "file:///etc/passwd"},
                        {"type": "prompt", "prompt": "uygun mu?"},
                    ],
                }
            ]
        },
        source="fusion",
        path=Path("hooks.json"),
        default_timeout_s=60.0,
    )
    assert [(c.handler, c.command, c.timeout_s) for c in commands] == [
        (HTTP_HANDLER, GENEL_URL, 7.0)
    ]
    assert commands[0].headers == (("Authorization", "Bearer $KANCA_ANAHTARI"),)
    assert commands[0].allowed_env_vars == ("KANCA_ANAHTARI",)
    assert ["http://" in s.reason for s in skipped] == [True, False]
    assert "tür desteklenmiyor: prompt" in skipped[1].reason
    assert hook_rows(HookSet(commands))[0].command == f"POST {GENEL_URL}"


def test_baslikta_yalniz_izinli_ortam_degiskeni_doldurulur():
    ortam = {"A": "1", "B": "2"}
    assert expand_header("x $A ${A} $B ${YOK}", ("A",), ortam) == "x 1 1  "


async def test_http_kancasi_olayi_post_eder_json_karari_uygulanir(tmp_path, istekler):
    kayit, yanit = istekler
    yanit["govde"] = json.dumps(
        {"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "yasak"}}
    )
    hook = _http(
        headers=(("Authorization", "Bearer $KANCA_ANAHTARI"), ("X-Diger", "$BASKA_SIR")),
        allowed_env_vars=("KANCA_ANAHTARI",),
    )

    verdict = await _oturum(tmp_path, hook).emit(
        HookEvent.PRE_TOOL_USE, subjects=("Bash",), fields={"tool_name": "Bash"}
    )

    assert verdict.blocked and verdict.reason == "yasak"
    istek = kayit[0]
    assert istek.method == "POST" and istek.headers["content-type"] == "application/json"
    assert istek.headers["authorization"] == "Bearer gizli-123"
    assert istek.headers["x-diger"] == ""
    govde = json.loads(istek.content)
    assert (govde["hook_event_name"], govde["tool_name"]) == ("PreToolUse", "Bash")


async def test_http_2xx_disi_yanit_engellemez_hata_olarak_gosterilir(tmp_path, istekler):
    _, yanit = istekler
    yanit["durum"], yanit["govde"] = 500, "sunucu çöktü"

    verdict = await _oturum(tmp_path, _http()).emit(HookEvent.PRE_TOOL_USE, subjects=("Bash",))

    assert not verdict.blocked and verdict.ran == 1
    assert "HTTP 500: sunucu çöktü" in verdict.errors[0]


async def test_http_ic_ag_adresi_varsayilan_engellenir_ayarla_acilir(tmp_path, istekler):
    kayit, _ = istekler
    yerel = _http("http://127.0.0.1:8080/kanca", HookEvent.STOP)

    engelli = await _oturum(tmp_path, yerel).emit(HookEvent.STOP)
    assert kayit == [] and "iç ağ adresi" in engelli.errors[0]
    assert "hook_http_allow_private" in engelli.errors[0]

    acik = await _oturum(tmp_path, yerel, ozel=True).emit(HookEvent.STOP)
    assert len(kayit) == 1 and acik.errors == ()


def test_guvenilmeyen_proje_ayari_ic_ag_iznini_acamaz():
    from fusion_cli.config.trust import EXECUTION_RUNTIME_KEYS

    assert "hook_http_allow_private" in EXECUTION_RUNTIME_KEYS
