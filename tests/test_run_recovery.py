"""Süreç çöktükten sonra görev durumu dürüst kalır (WP07).

Rapor §4.2: yürütmeden önce `dispatching` kalıcı yazılır. Yan etki başlamış ama
sonuç yazılamadan süreç ölmüşse iş otomatik tekrarlanmaz; `needs_reconciliation`
döner. Henüz yürütülmemiş (kuyrukta) iş yan etki üretmediği için iptal sayılır.
İptal yalnız duruş kanıtıyla `cancelled` olur.
"""

from __future__ import annotations

from fusion_cli.core.execution_context import ExecutionContext
from fusion_cli.core.task_protocol import OperationRequest, RunStatus, args_digest
from fusion_cli.memory.run_store import SqliteRunStore

from .test_operation_idempotency import Saat


def _ctx():
    return ExecutionContext(
        tenant_id="hesap-a",
        user_id="hesap-a",
        workspace_id="kisisel",
        device_id="tel-a",
        scopes=frozenset({"agent.run", "project.read", "agent.cancel"}),
    )


def _accept(store, key):
    return store.accept(
        _ctx(),
        OperationRequest(
            idempotency_key=key, tool_name="agent.run", args_digest=args_digest(key), summary=key
        ),
    )


def test_cokme_sonrasi_yurutulen_is_uzlastirma_bekler_kuyruktaki_iptal_olur(tmp_path):
    yol = tmp_path / "runs.sqlite3"
    ilk = SqliteRunStore(yol, clock=Saat())
    calisan = _accept(ilk, "calisan")
    ilk.mark_dispatching(_ctx(), calisan.run_id)
    ilk.set_status(_ctx(), calisan.run_id, RunStatus.RUNNING)
    gonderilen = _accept(ilk, "gonderilen")
    ilk.mark_dispatching(_ctx(), gonderilen.run_id)
    kuyrukta = _accept(ilk, "kuyrukta")
    # Süreç çöküyor: işletim sistemi kilidi bırakır, kayıt dosyası diskte kalır.
    ilk._owner._handle.close()

    ikinci = SqliteRunStore(yol, clock=Saat())

    durum = {r.run_id: r.status for r in ikinci.list_runs(_ctx())}
    assert durum[calisan.run_id] is RunStatus.NEEDS_RECONCILIATION
    assert durum[gonderilen.run_id] is RunStatus.NEEDS_RECONCILIATION
    assert durum[kuyrukta.run_id] is RunStatus.CANCELLED
    son = ikinci.events_after(_ctx(), calisan.run_id, 0)[-1]
    assert son.kind == "needs_reconciliation"


def test_canli_sahip_varken_ikinci_acilis_isi_bozmaz(tmp_path):
    yol = tmp_path / "runs.sqlite3"
    ilk = SqliteRunStore(yol, clock=Saat())
    makbuz = _accept(ilk, "canli")
    ilk.mark_dispatching(_ctx(), makbuz.run_id)

    ikinci = SqliteRunStore(yol, clock=Saat())

    assert ikinci.snapshot(_ctx(), makbuz.run_id).status is RunStatus.DISPATCHING


def test_iptal_kanitsiz_cancelled_olmaz(tmp_path):
    store = SqliteRunStore(tmp_path / "runs.sqlite3", clock=Saat())
    makbuz = _accept(store, "is")
    store.mark_dispatching(_ctx(), makbuz.run_id)
    store.set_status(_ctx(), makbuz.run_id, RunStatus.RUNNING)

    istenen = store.request_cancel(_ctx(), makbuz.run_id)
    assert istenen.status is RunStatus.CANCELLING

    store.finish_cancel(_ctx(), makbuz.run_id, stopped=False)
    assert store.snapshot(_ctx(), makbuz.run_id).status is RunStatus.NEEDS_RECONCILIATION


def test_kuyruktaki_isin_iptali_hemen_cancelled(tmp_path):
    store = SqliteRunStore(tmp_path / "runs.sqlite3", clock=Saat())
    makbuz = _accept(store, "is")

    assert store.request_cancel(_ctx(), makbuz.run_id).status is RunStatus.CANCELLED
