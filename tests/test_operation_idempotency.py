"""Kalıcı görev kabulü: aynı anahtar+aynı içerik tek makbuz, farklı içerik çatışma (WP07).

Plan §10 / rapor §4.2: işlem kabul edilmeden önce idempotency anahtarı ve argüman
özeti kalıcı kayda alınır; kabul ile ilk olay aynı transaction'dadır. Her yöntem
kaynak yetkisini bağlamdan denetler.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.execution_context import ExecutionContext
from fusion_cli.core.task_protocol import (
    IdempotencyConflictError,
    OperationRequest,
    RunAccessDeniedError,
    RunStatus,
    args_digest,
)
from fusion_cli.memory.run_store import SqliteRunStore


class Saat:
    def __init__(self) -> None:
        self.value = 1000.0

    def now(self) -> float:
        return self.value


def _ctx(tenant="hesap-a", device="tel-a", scopes=("agent.run", "project.read", "agent.cancel")):
    return ExecutionContext(
        tenant_id=tenant,
        user_id=tenant,
        workspace_id="kisisel",
        device_id=device,
        scopes=frozenset(scopes),
    )


def _istek(prompt="raporu yaz", key="k-1"):
    return OperationRequest(
        idempotency_key=key,
        tool_name="agent.run",
        args_digest=args_digest({"prompt": prompt}),
        summary=prompt,
    )


@pytest.fixture
def store(tmp_path):
    return SqliteRunStore(tmp_path / "runs.sqlite3", clock=Saat())


def test_ayni_anahtar_ayni_icerik_tek_makbuz(store):
    ilk = store.accept(_ctx(), _istek())
    ikinci = store.accept(_ctx(), _istek())

    assert ilk.run_id == ikinci.run_id
    assert ilk.duplicate is False and ikinci.duplicate is True
    assert len(store.list_runs(_ctx())) == 1


def test_ayni_anahtar_farkli_icerik_catisma(store):
    store.accept(_ctx(), _istek("raporu yaz"))

    with pytest.raises(IdempotencyConflictError):
        store.accept(_ctx(), _istek("veritabanını sil"))


def test_kabul_ve_ilk_olay_ayni_transactionda(store):
    makbuz = store.accept(_ctx(), _istek())

    olaylar = store.events_after(_ctx(), makbuz.run_id, 0)
    assert [(olay.seq, olay.kind) for olay in olaylar] == [(1, "accepted")]
    assert olaylar[0].schema_version == 1
    assert olaylar[0].event_id and olaylar[0].run_id == makbuz.run_id


def test_olay_sirasi_monoton_ve_kaldigi_yerden_devam(store):
    makbuz = store.accept(_ctx(), _istek())
    for parca in ("a", "b", "c"):
        store.append_event(_ctx(), makbuz.run_id, "delta", {"text": parca})

    sonraki = store.events_after(_ctx(), makbuz.run_id, 2)

    assert [olay.seq for olay in sonraki] == [3, 4]
    assert [olay.payload["text"] for olay in sonraki] == ["b", "c"]


def test_yeniden_acilan_depo_ayni_makbuzu_ve_olaylari_dondurur(tmp_path):
    yol = tmp_path / "runs.sqlite3"
    ilk = SqliteRunStore(yol, clock=Saat())
    makbuz = ilk.accept(_ctx(), _istek())
    ilk.append_event(_ctx(), makbuz.run_id, "delta", {"text": "x"})
    ilk.close()

    ikinci = SqliteRunStore(yol, clock=Saat())

    tekrar = ikinci.accept(_ctx(), _istek())
    assert tekrar.run_id == makbuz.run_id and tekrar.duplicate
    # Kapanan süreçte hiç başlamamış iş tekrar çalıştırılmaz; iptal olayıyla kapanır.
    olaylar = ikinci.events_after(_ctx(), makbuz.run_id, 0)
    assert [(olay.seq, olay.kind) for olay in olaylar] == [
        (1, "accepted"),
        (2, "delta"),
        (3, "cancelled"),
    ]
    assert tekrar.status is RunStatus.CANCELLED


def test_kapsamsiz_baglam_gorev_acamaz_ve_iptal_edemez(store):
    makbuz = store.accept(_ctx(), _istek())
    okuyucu = _ctx(scopes=("project.read",))

    with pytest.raises(RunAccessDeniedError):
        store.accept(okuyucu, _istek(key="k-2"))
    with pytest.raises(RunAccessDeniedError):
        store.request_cancel(okuyucu, makbuz.run_id)


def test_bitmis_gorevin_durumu_geri_donmez(store):
    makbuz = store.accept(_ctx(), _istek())
    store.set_status(_ctx(), makbuz.run_id, RunStatus.SUCCEEDED)

    store.set_status(_ctx(), makbuz.run_id, RunStatus.RUNNING)

    assert store.snapshot(_ctx(), makbuz.run_id).status is RunStatus.SUCCEEDED


def test_girdi_anlik_goruntusu_degismez_ve_sahiplik_denetimli(store):
    ref = store.save_input(_ctx(), {"prompt": "raporu yaz", "project": "p"})

    assert store.load_input(_ctx(), ref) == {"prompt": "raporu yaz", "project": "p"}
    assert store.load_input(_ctx(tenant="hesap-b"), ref) is None
