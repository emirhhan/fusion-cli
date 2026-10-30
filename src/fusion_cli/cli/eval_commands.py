"""`fusion eval` — gerçek hatalardan eval görevi taslağı üret, onayla (döngünün 1. halkası).

`taslak-uret` tur günlüğünden taslak çıkarır; `taslaklar / kabul / sil` taslağı kullanıcı
onaylar ya da atar. Taslak hiçbir zaman kendiliğinden kümeye girmez.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from ..config.loader import load_config
from ..core.clock import SystemClock
from ..core.errors import EvalError
from ..ui import theme
from .dongu_ortak import DEFAULT_SUITE, fail, loop_paths, require_dev_tools
from .repl.transcript_store import read_workspace_events

if TYPE_CHECKING:
    # Yalnız tip için: `evals` çalışma anında tembel yüklenir.
    from evals.taslak import Taslak

eval_app = typer.Typer(
    no_args_is_help=True, help="Eval görevleri: gerçek hatalardan taslak üret, onayla."
)
console = Console()

#: Varsayılan: son kaç günün konuşması taranır (haftalık çalıştırma için).
DEFAULT_SCAN_DAYS = 7
SECONDS_PER_DAY = 86_400
#: Listede gösterilen isteğin uzunluğu.
LIST_REQUEST_CHARS = 70


@eval_app.command("taslak-uret")
def draft_generate(
    project: Annotated[
        Path | None, typer.Option("--proje", help="Proje kökü (varsayılan: bulunduğun dizin).")
    ] = None,
    days: Annotated[
        int, typer.Option("--gun", min=1, help="Son kaç günün konuşması.")
    ] = DEFAULT_SCAN_DAYS,
    limit: Annotated[int, typer.Option("--maks", min=1, help="En çok kaç taslak yazılsın.")] = 50,
) -> None:
    """Konuşma günlüğündeki düzeltme/geri alma/tekrar/başarısız turlardan taslak üret."""
    require_dev_tools()
    from evals.dongu_kaydi import OLAY_TASLAK_URETILDI, kayit_ekle
    from evals.kume import kabul_edilen_kimlikler
    from evals.taslak import taslak_uret
    from evals.taslak_deposu import TaslakDeposu

    paths = loop_paths()
    root = (project or Path.cwd()).expanduser().resolve()
    now = SystemClock().now()
    records = read_workspace_events(load_config().memory_dir, root)
    found = taslak_uret(
        records,
        kok=root,
        ev=Path.home(),
        simdi=now,
        sonra=now - days * SECONDS_PER_DAY,
        maks=limit,
    )
    written = TaslakDeposu(paths.drafts).kaydet(found, atla=kabul_edilen_kimlikler(paths.suites))
    kinds = Counter(taslak.kaynak.value for taslak in written)
    kayit_ekle(
        paths.log,
        OLAY_TASLAK_URETILDI,
        {"bulunan": len(found), "yeni": len(written), "kaynaklar": dict(kinds), "gun": days},
        simdi=now,
    )
    console.print(
        f"{len(records)} kayıt tarandı: {len(found)} taslak bulundu, {len(written)} yeni yazıldı."
    )
    if written:
        console.print("Görmek için: fusion eval taslaklar")


@eval_app.command("taslaklar")
def drafts_show(
    draft_id: Annotated[str, typer.Argument(help="Verilirse o taslağın ayrıntısı.")] = "",
) -> None:
    """Onay bekleyen taslakları listele (ya da birinin ayrıntısını göster)."""
    require_dev_tools()
    from evals.taslak_deposu import TaslakDeposu

    store = TaslakDeposu(loop_paths().drafts)
    try:
        if draft_id:
            _print_draft_detail(store.oku(draft_id))
            return
        drafts = store.listele()
    except EvalError as error:
        raise fail(str(error)) from error
    if not drafts:
        console.print("Onay bekleyen taslak yok. Üretmek için: fusion eval taslak-uret")
        return
    table = Table(title="Eval görev taslakları (onay bekliyor)")
    for column in ("kimlik", "kaynak", "ölçüt", "istek"):
        table.add_column(column)
    for draft in drafts:
        table.add_row(
            draft.id,
            draft.kaynak.value,
            draft.olcut.kind.value if draft.olcut else "[yok]",
            escape(draft.request[:LIST_REQUEST_CHARS].replace("\n", " ")),
        )
    console.print(table)
    console.print("Kabul: fusion eval kabul <kimlik>   ·   Atma: fusion eval sil <kimlik>")


def _print_draft_detail(draft: Taslak) -> None:
    console.print(f"[bold]{escape(draft.id)}[/bold]  ({draft.kaynak.value})")
    console.print(escape(draft.request))
    for satir in draft.kanit:
        console.print(f"[{theme.DIM}]- {escape(satir)}[/{theme.DIM}]")
    ozet = draft.olcut.kind.value if draft.olcut else "yok"
    console.print(f"ölçüt: {ozet} ({escape(draft.olcut_notu)})")


@eval_app.command("kabul")
def draft_accept(
    draft_id: Annotated[str, typer.Argument(help="`fusion eval taslaklar` kimliği")],
    suite: Annotated[
        str, typer.Option("--kume", help="Eklenecek kullanıcı kümesi.")
    ] = DEFAULT_SUITE,
    command: Annotated[str, typer.Option("--komut", help="Ölçüt: bu komut 0 dönmeli.")] = "",
    keyword: Annotated[
        str, typer.Option("--anahtar", help="Ölçüt: cevapta bu metin geçmeli.")
    ] = "",
    file: Annotated[str, typer.Option("--dosya", help="Ölçüt: bu dosya değişmeli.")] = "",
) -> None:
    """Taslağı onayla: görev kullanıcı kümesine eklenir, taslak kaldırılır."""
    require_dev_tools()
    from evals.dongu_kaydi import OLAY_TASLAK_KABUL, kayit_ekle
    from evals.kume import SETUP_UYARISI, kume_dosyasi, olcut_olustur, taslagi_kabul_et
    from evals.taslak_deposu import TaslakDeposu

    paths = loop_paths()
    try:
        criterion = olcut_olustur(
            komut=command or None, anahtar=keyword or None, dosya=file or None
        )
        target = kume_dosyasi(suite, paths.suites)
        task = taslagi_kabul_et(TaslakDeposu(paths.drafts), draft_id, target, olcut=criterion)
    except EvalError as error:
        raise fail(str(error)) from error
    kayit_ekle(
        paths.log,
        OLAY_TASLAK_KABUL,
        {"taslak": task.id, "kume": suite, "olcut": task.criterion.kind.value},
        simdi=SystemClock().now(),
    )
    console.print(f"Eklendi: {escape(task.id)} → {escape(str(target))}")
    console.print(f"[{theme.WARN}]{escape(SETUP_UYARISI)}[/{theme.WARN}]")


@eval_app.command("sil")
def draft_delete(
    draft_id: Annotated[str, typer.Argument(help="`fusion eval taslaklar` kimliği")],
) -> None:
    """Taslağı at; aynı hata günlükte durdukça bir daha önerilmez."""
    require_dev_tools()
    from evals.dongu_kaydi import OLAY_TASLAK_SILINDI, kayit_ekle
    from evals.taslak_deposu import TaslakDeposu

    paths = loop_paths()
    try:
        TaslakDeposu(paths.drafts).kaldir(draft_id, reddet=True)
    except EvalError as error:
        raise fail(str(error)) from error
    kayit_ekle(paths.log, OLAY_TASLAK_SILINDI, {"taslak": draft_id}, simdi=SystemClock().now())
    console.print(f"Silindi: {escape(draft_id)}")
