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
from dataclasses import asdict
from pathlib import Path
from typing import IO, Any

from evals import driver_engine
from evals.driver_limits import DRIVER_GRACE_S

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

import fusion_cli.engines.agent.loop as _loop
_bp = _loop.build_provider
def _saglayici(spec, **kw):
    print('>> model', spec.model, 'yedek', list(spec.fallback), file=sys.stderr, flush=True)
    return _bp(spec, **kw)
_loop.build_provider = _saglayici

sys.argv = ['fusion', 'app']
from fusion_cli.cli.app import main
main()
"""


#: Takılma teşhisi: çekirdeğe `kill -USR1 <pid>` iş parçacığı yığınlarını,
#: `kill -USR2 <pid>` asyncio görevlerinin bekleme zincirini stderr'e (cekirdek.err)
#: döker. Ölçüldü (4 Ekim): kabul koşuları CPU %0'da dakikalarca bekledi ve
#: Python yığını dışarıdan görülemediği için neyi beklediği bulunamadı.
_TESHIS_LAUNCHER = """
import asyncio, faulthandler, signal, sys
faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)

def _gorevler(*_):
    try:
        gorevler = asyncio.all_tasks(asyncio.get_running_loop())
    except RuntimeError:
        return
    for gorev in gorevler:
        print('=== GOREV', gorev.get_name(), file=sys.stderr)
        gorev.print_stack(limit=12, file=sys.stderr)
        # print_stack askıdaki görevin yalnız en dış çerçevesini verir; asıl bekleyen
        # yer zincirin SONUNDADIR. cr_await / gi_yieldfrom / ag_await izlenir.
        halka = gorev.get_coro()
        for _ in range(60):
            cerceve = (getattr(halka, 'cr_frame', None) or getattr(halka, 'gi_frame', None)
                       or getattr(halka, 'ag_frame', None))
            if cerceve is None:
                print('    bekliyor:', repr(halka)[:300], file=sys.stderr)
                break
            kod = cerceve.f_code
            print(f'    {kod.co_filename}:{cerceve.f_lineno} {kod.co_name}', file=sys.stderr)
            halka = (getattr(halka, 'cr_await', None) or getattr(halka, 'gi_yieldfrom', None)
                     or getattr(halka, 'ag_await', None))
            if halka is None:
                break
    sys.stderr.flush()

_orijinal = asyncio.new_event_loop
def _yeni():
    loop = _orijinal()
    loop.add_signal_handler(signal.SIGUSR2, _gorevler)
    return loop
asyncio.new_event_loop = _yeni
asyncio.events.new_event_loop = _yeni
sys.argv = ['fusion', 'app']
from fusion_cli.cli.app import main
main()
"""


def _komut(args: argparse.Namespace) -> list[str]:
    selected = driver_engine.selected_command(args)
    if selected is not None:
        return selected
    if args.log:
        return [sys.executable, "-c", _LOG_LAUNCHER]
    return [sys.executable, "-c", _TESHIS_LAUNCHER]


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


def _say(sayac: dict[str, int], veri: dict[str, Any]) -> None:
    """Olayı rapor sayacına işle; arka plan model çağrıları sayılmaz."""
    olay = veri.get("olay")
    if olay == "ModelCallStarted" and not veri.get("background"):
        sayac["model_cagrisi"] += 1
        # Ana döngüyü web modeli karşıladıysa (öğretmen devri ya da web yedeği) iş
        # "Nemotron yaptı" sayılmaz; öğretmen danışması kendi rolüyle ayrıdır.
        if "_web/" in str(veri.get("model", "")) and veri.get("role") != "ogretmen":
            sayac["web_model_cagrisi"] += 1
    elif olay == "ModelCallFinished" and not veri.get("background"):
        kullanim = (veri.get("result") or {}).get("usage") or {}
        istem = int(kullanim.get("prompt_tokens") or 0)
        sayac["istem_token"] += istem
        sayac["en_buyuk_istem"] = max(sayac["en_buyuk_istem"], istem)
    elif olay == "ToolExecuted":
        if veri.get("name") == "ask_teacher":
            sayac["ogretmen_cagrisi"] += 1
        if veri.get("outcome") not in (None, "ok"):
            sayac["arac_hatasi"] += 1
    elif olay == "ModelFallbackActivated":
        sayac["yedege_gecis"] += 1
    elif olay == "ToolCallRepaired":
        sayac["sozlesme_onarimi"] += 1
    elif olay == "TeacherMemoryUsed":
        sayac["hafizadan_plan"] += 1


async def drive(
    args: argparse.Namespace, stderr: IO[bytes] | None, olay_gunlugu: IO[bytes] | None = None
) -> dict[str, Any]:
    engine = driver_engine.from_options(args)
    process = await asyncio.create_subprocess_exec(
        *_komut(args),
        cwd=args.kok,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=stderr or asyncio.subprocess.DEVNULL,
        limit=16 * 1024 * 1024,
    )
    assert process.stdin and process.stdout
    kayit: dict[str, Any] = {"izinler": [], "sorular": [], "araclar": [], "turlar": []}
    # Uzun görev raporu için sayaçlar: model/öğretmen çağrısı, hata ve yedeğe geçiş.
    sayac: dict[str, int] = {
        "model_cagrisi": 0,
        "ogretmen_cagrisi": 0,
        "arac_hatasi": 0,
        "yedege_gecis": 0,
        "sozlesme_onarimi": 0,
        "hafizadan_plan": 0,
        "web_model_cagrisi": 0,
        "istem_token": 0,
        "en_buyuk_istem": 0,
    }
    kayit["sayaclar"] = sayac
    bekleyen: dict[str, asyncio.Future[dict[str, Any]]] = {}
    engine_ready: asyncio.Future[dict[str, object]] | None = (
        asyncio.get_running_loop().create_future() if engine is not None else None
    )

    def gonder(payload: dict[str, Any]) -> None:
        assert process.stdin
        process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())

    async def oku() -> None:
        assert process.stdout
        while True:
            try:
                line = await process.stdout.readline()
            except ValueError as hata:  # satır akış sınırını aştı; atlanır, okuma sürer
                kayit.setdefault("surucu_hatalari", []).append(repr(hata)[:500])
                continue
            if not line:
                # Çekirdek kapandı: cevap bekleyen istekler süre dolana kadar asılı
                # kalmasın (ölçüldü: ölen çekirdeğin sürücüsü 3600 sn bekliyordu).
                if engine_ready is not None and not engine_ready.done():
                    engine_ready.set_exception(
                        ConnectionError("motor kanıtı gelmeden çekirdek kapandı")
                    )
                for bekleyen_istek in bekleyen.values():
                    if not bekleyen_istek.done():
                        bekleyen_istek.set_exception(ConnectionError("çekirdek kapandı"))
                break
            try:
                isle(line)
            # Sınır: tek bir bozuk mesaj okuyucuyu öldürürse çekirdek cevap bekleyip
            # sonsuza kadar takılıyordu (ölçüldü: kabul koşusu 9+ dk onayda kaldı).
            except Exception as hata:  # sınır: hata kayda yazılır, okuma sürer
                kayit.setdefault("surucu_hatalari", []).append(repr(hata)[:500])

    def isle(line: bytes) -> None:
        try:
            mesaj = json.loads(line)
        except ValueError:
            return
        tip, veri = mesaj.get("tip"), mesaj.get("veri") or {}
        if tip == "motor_kaniti" and engine is not None and engine_ready is not None:
            if engine_ready.done():
                kayit["hata"] = "Yinelenen motor kanıtı reddedildi."
                driver_engine.invalidate_pending(bekleyen, kayit["hata"])
                return
            try:
                receipt = driver_engine.validate_receipt(veri, engine, process.pid)
                engine_ready.set_result(asdict(receipt))
            except ValueError as error:
                engine_ready.set_exception(error)
            return
        if engine is not None and driver_engine.handle_config(tip, veri, kayit):
            if kayit.get("hata"):
                driver_engine.invalidate_pending(bekleyen, kayit["hata"])
            return
        if tip == "olay":
            _say(sayac, veri)
            if olay_gunlugu is not None:
                # Her satır hemen diske iner: tamponda bekleyen olaylar, takılan bir
                # koşuda "en son ne oldu" sorusunu yanlış cevaplatıyordu (ölçüldü, 4 Ekim).
                # Zaman damgası: süre sınırına takılan çağrıların ne kadar beklediği ve
                # adımların süresi sonradan ölçülebilsin (olaylarda zaman yoktu).
                damgali = {**mesaj, "ts": round(time.time(), 2)}
                olay_gunlugu.write((json.dumps(damgali, ensure_ascii=False) + "\n").encode())
                olay_gunlugu.flush()
        if tip == "olay" and veri.get("olay") == "ToolExecuted":
            kayit["araclar"].append(veri.get("name"))
        elif tip == "soru":
            gonder({"tip": "cevap", "id": mesaj["id"], "veri": _cevap(veri, args, kayit)})
        elif tip == "sonuc" and mesaj.get("id") in bekleyen:
            bekleyen.pop(mesaj["id"]).set_result(veri)

    async def istek(ad: str, veri: dict[str, Any], sure: float) -> dict[str, Any]:
        kimlik = f"{ad}-{len(kayit['turlar'])}-{time.monotonic_ns()}"
        bekleyen[kimlik] = asyncio.get_running_loop().create_future()
        gonder({"tip": "istek", "id": kimlik, "ad": ad, "veri": veri})
        return await asyncio.wait_for(bekleyen[kimlik], timeout=sure)

    async def initialize() -> None:
        if engine_ready is not None:
            kayit["motor_kaniti"] = await engine_ready
            if kayit.get("hata"):
                raise ValueError("Motor kanıtı yinelendi.")
        await istek("oturum.baslat", {"kok": args.kok, "mod": args.mod, "kip": "kod"}, 60)

    okuyucu = asyncio.create_task(oku())
    try:
        try:
            await asyncio.wait_for(initialize(), timeout=60)
        except (ValueError, ConnectionError, TimeoutError) as error:
            kayit["hata"] = f"Oturum/motor başlangıcı doğrulanmadı: {type(error).__name__}"
            return kayit
        if args.chrome:
            bilgi = await istek("chrome.baslat", {}, 30)
            eslesme = json.dumps({"port": bilgi.get("port"), "anahtar": bilgi.get("anahtar")})
            await asyncio.to_thread(Path(args.chrome).write_text, eslesme, encoding="utf-8")
            bitis = time.monotonic() + args.eslestirme_suresi
            while time.monotonic() < bitis:
                if (await istek("chrome.durum", {}, 30)).get("bagli"):
                    break
                await asyncio.sleep(3)
            else:
                kayit["hata"] = "Chrome eklentisi eşleştirilmedi."
                return kayit
        for gorev in args.gorev:
            if engine is not None and kayit.get("hata"):
                return kayit
            basla = time.monotonic()
            kayit["efektif_baslangic"] = len(kayit.get("efektif_kanitlar", []))
            try:
                sonuc = await istek(
                    "tur.calistir",
                    {"gorev": gorev, "sure_s": args.sure},
                    args.sure + DRIVER_GRACE_S,
                )
                ozet = {"ok": sonuc.get("ok"), "metin": str(sonuc.get("metin", ""))[:2000]}
            except TimeoutError:
                ozet = {"ok": False, "metin": f"zaman aşımı ({args.sure} sn)"}
            except ConnectionError as hata:
                ozet = {"ok": False, "metin": str(hata)}
            if engine is not None:
                ozet["efektif_kanit"] = (
                    len(kayit.get("efektif_kanitlar", [])) > kayit["efektif_baslangic"]
                )
            kayit["turlar"].append(
                {"gorev": gorev[:120], **ozet, "sure_sn": round(time.monotonic() - basla, 1)}
            )
    finally:
        # Önce girişi kapat: çekirdek düzgün çıkıp tarayıcı kirasını bırakır. Zorla
        # öldürmek paylaşılan Chrome'u sahipsiz bırakıyordu.
        if process.stdin is not None:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=20)
        except TimeoutError:
            process.kill()
            await process.wait()
        await okuyucu
        if engine is not None:
            kayit["kontrollu_ayar_kaniti"] = bool(kayit.get("efektif_kanitlar")) and not kayit.get(
                "hata"
            )
        if engine is not None and kayit.get("hata"):
            for turn in kayit["turlar"]:
                turn.update(ok=False, metin=kayit["hata"])
    # Tek görevli eski çağıranlar için kısayol.
    if len(kayit["turlar"]) == 1:
        kayit["sonuc"] = {k: kayit["turlar"][0][k] for k in ("ok", "metin")}
        kayit["sure_sn"] = kayit["turlar"][0]["sure_sn"]
    return kayit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kok", required=True)
    parser.add_argument("--mod", default="auto", choices=["auto", "plan", "security"])
    parser.add_argument("--gorev", required=True, action="append")
    parser.add_argument("--soru-cevabi", default="ilk", choices=["ilk", "atla"])
    parser.add_argument("--onay", default="once", choices=["once", "deny"])
    parser.add_argument("--sure", type=float, default=900)
    parser.add_argument("--stderr", default="")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--engine-source", default="")
    parser.add_argument("--engine-manifest", default="")
    parser.add_argument("--engine-proof", default="")
    parser.add_argument("--model-probe", action="store_true")
    parser.add_argument("--remotion-browser-executable", default="")
    parser.add_argument(
        "--remotion-browser-mode", default="", choices=["", "headless-shell", "chrome-for-testing"]
    )
    parser.add_argument("--chrome", default="", help="eşleştirme bilgisinin yazılacağı dosya")
    parser.add_argument("--eslestirme-suresi", type=float, default=900)
    parser.add_argument("--olaylar", default="", help="çekirdek olaylarının yazılacağı JSONL")
    args = parser.parse_args()
    Path(args.kok).mkdir(parents=True, exist_ok=True)
    with contextlib.ExitStack() as stack:
        stderr = stack.enter_context(Path(args.stderr).open("wb")) if args.stderr else None
        olaylar = stack.enter_context(Path(args.olaylar).open("wb")) if args.olaylar else None
        sonuc = asyncio.run(drive(args, stderr, olaylar))
        print(json.dumps(sonuc, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
