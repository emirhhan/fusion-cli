"""Masaüstü çekirdeğini (`fusion app`) gerçek modelle süren canlı kabul sürücüsü.

Arayüzün yaptığını yapar: oturumu kurar, görevi gönderir, çekirdeğin sorduğu
izin ve soruları kaydedip betikli cevaplarla yanıtlar, sonucu JSON olarak yazar.
Ölçülen şey kipin DAVRANIŞIDIR: hangi araç için izin sorulduğu, modelin ne
zaman seçenekli soru sorduğu, turun ne kadar sürdüğü.

Kullanım:
    python -m evals.live_drive --kok /tmp/deneme --mod auto --gorev "..." \\
        [--soru-cevabi ilk|atla] [--onay once|deny] [--sure 900] \\
        [--stderr günlük.txt --log]

`--log` çekirdeği INFO günlüğüyle başlatır, web taşıma çağrılarını zamanlar ve
60. saniyede bütün asyncio görevlerinin bekleme zincirini döker (takılma teşhisi).
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import time
from pathlib import Path
from typing import IO, Any

_LOG_LAUNCHER = """
import asyncio, logging, sys, time
logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format='%(relativeCreated)7.0f %(name)s %(message)s')
for n in ('httpx', 'httpcore', 'LiteLLM'):
    logging.getLogger(n).setLevel(logging.WARNING)

def _dokum():
    for gorev in asyncio.all_tasks():
        print('=== GOREV', gorev.get_name(), file=sys.stderr)
        coro = gorev.get_coro()
        while coro is not None:
            frame = getattr(coro, 'cr_frame', None) or getattr(coro, 'ag_frame', None)
            if frame is not None:
                print('   ', frame.f_code.co_filename, frame.f_lineno,
                      frame.f_code.co_name, file=sys.stderr)
            coro = getattr(coro, 'cr_await', None) or getattr(coro, 'ag_await', None)

_orijinal = asyncio.new_event_loop
def _yeni():
    loop = _orijinal()
    loop.call_later(60, _dokum)
    return loop
asyncio.new_event_loop = _yeni
asyncio.events.new_event_loop = _yeni

import fusion_cli.providers.web_browser as _wb
import fusion_cli.providers.web_registry as _wr
_orj = _wb.build_browser_transport
def _izle(session, **kw):
    tr = _orj(session, **kw)
    async def _tasima(c, m, model):
        t0 = time.monotonic()
        print('>> tasima', session.provider, len(m), file=sys.stderr, flush=True)
        try:
            r = await tr(c, m, model)
        except BaseException as e:
            print('<< tasima HATA', round(time.monotonic() - t0, 1), type(e).__name__,
                  str(e)[:100], file=sys.stderr, flush=True)
            raise
        print('<< tasima ok', round(time.monotonic() - t0, 1), file=sys.stderr, flush=True)
        return r
    return _tasima
_wb.build_browser_transport = _izle
_wr.build_browser_transport = _izle

sys.argv = ['fusion', 'app']
from fusion_cli.cli.app import main
main()
"""


def _komut(args: argparse.Namespace) -> list[str]:
    if args.log:
        return [sys.executable, "-c", _LOG_LAUNCHER]
    return [str(Path(sys.executable).with_name("fusion")), "app"]


def _cevap(veri: dict[str, Any], args: argparse.Namespace, kayit: dict[str, Any]) -> dict[str, Any]:
    """Çekirdeğin sorusunu kaydet ve betikli cevabı üret."""
    if veri.get("tur") == "onay":
        kayit["izinler"].append(
            {
                "arac": veri.get("arac"),
                "baslik": veri.get("baslik"),
                "hedef": veri.get("hedef"),
                "tehlike": veri.get("tehlike"),
            }
        )
        return {"secim": args.onay}
    secenekler = [s.get("etiket") for s in veri.get("secenekler") or []]
    kayit["sorular"].append(
        {"soru": veri.get("soru"), "secenekler": secenekler, "onerilen": veri.get("onerilen")}
    )
    ilk = veri.get("onerilen") or (secenekler[0] if secenekler else "")
    return {"metin": ilk if args.soru_cevabi == "ilk" else ""}


async def drive(args: argparse.Namespace, stderr: IO[bytes] | None) -> dict[str, Any]:
    process = await asyncio.create_subprocess_exec(
        *_komut(args),
        cwd=args.kok,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=stderr or asyncio.subprocess.DEVNULL,
        limit=16 * 1024 * 1024,
    )
    assert process.stdin and process.stdout
    kayit: dict[str, Any] = {"izinler": [], "sorular": [], "araclar": [], "sonuc": None}

    def gonder(payload: dict[str, Any]) -> None:
        assert process.stdin
        process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())

    baslat = {"kok": args.kok, "mod": args.mod, "kip": "kod"}
    gonder({"tip": "istek", "id": "baslat", "ad": "oturum.baslat", "veri": baslat})
    gonder({"tip": "istek", "id": "tur", "ad": "tur.calistir", "veri": {"gorev": args.gorev}})
    basla = time.monotonic()
    try:
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=args.sure)
            if not line:
                break
            try:
                mesaj = json.loads(line)
            except ValueError:
                continue
            tip, veri = mesaj.get("tip"), mesaj.get("veri") or {}
            if tip == "olay" and veri.get("olay") == "ToolExecuted":
                kayit["araclar"].append(veri.get("name"))
            if tip == "soru":
                gonder({"tip": "cevap", "id": mesaj["id"], "veri": _cevap(veri, args, kayit)})
            if tip == "sonuc" and mesaj.get("id") == "tur":
                kayit["sonuc"] = {"ok": veri.get("ok"), "metin": str(veri.get("metin", ""))[:1500]}
                break
    except TimeoutError:
        kayit["sonuc"] = {"ok": False, "metin": f"zaman aşımı ({args.sure} sn)"}
    finally:
        kayit["sure_sn"] = round(time.monotonic() - basla, 1)
        process.kill()
        await process.wait()
    return kayit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kok", required=True)
    parser.add_argument("--mod", default="auto", choices=["auto", "plan", "security"])
    parser.add_argument("--gorev", required=True)
    parser.add_argument("--soru-cevabi", default="ilk", choices=["ilk", "atla"])
    parser.add_argument("--onay", default="once", choices=["once", "deny"])
    parser.add_argument("--sure", type=float, default=900)
    parser.add_argument("--stderr", default="")
    parser.add_argument("--log", action="store_true")
    args = parser.parse_args()
    Path(args.kok).mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        stderr = stack.enter_context(Path(args.stderr).open("wb")) if args.stderr else None
        print(json.dumps(asyncio.run(drive(args, stderr)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
