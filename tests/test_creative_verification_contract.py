"""Yaratıcı çıktı doğrulayıcıları: gürültü ile gerçek hata ayrılır, zayıf kanıt kanıt sayılmaz.

Ölçüldü (29 Ekim): oyun sondası favicon 404'ünü "konsol hatası" sayıp çalışan oyunu
bozuk raporluyordu; WebGL canvas'ta `toDataURL` boş kare verdiği için "tuşlar etkisiz"
yanlış alarmı çıkıyordu (ve değişen bir canvas hash'i tek başına etkileşim kanıtı
sayılıyordu). Remotion videosunda ise kullanıcıya ait olmayan sabit marka adı vardı.
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import threading

import pytest

from fusion_cli.config.paths import bundled_skills_dir
from fusion_cli.tools.play_probe import ProbeReport, probe_game
from fusion_cli.tools.preview_probe import probe
from fusion_cli.tools.resource_noise import is_favicon_load_error, is_favicon_url


def test_favicon_adresi_taninir_baska_kaynak_taninmaz():
    assert is_favicon_url("http://127.0.0.1:8000/favicon.ico")
    assert is_favicon_url("http://127.0.0.1:8000/apple-touch-icon.png")
    assert not is_favicon_url("http://127.0.0.1:8000/oyun.js")
    assert not is_favicon_url("http://127.0.0.1:8000/img/favicon-sprite-notes.txt/x.png")


def test_favicon_konsol_satiri_yalniz_konumu_favicon_ise_gurultudur():
    metin = "Failed to load resource: the server responded with a status of 404 (File not found)"

    assert is_favicon_load_error(metin, "http://x/favicon.ico")
    assert not is_favicon_load_error(metin, "http://x/oyun.js")
    assert not is_favicon_load_error("Uncaught TypeError", "http://x/favicon.ico")


def _rapor(**alan) -> ProbeReport:
    temel = {
        "console_errors": (),
        "raf_per_second": 60,
        "state_before": None,
        "state_after": None,
        "canvas_changed": False,
        "restart_state": None,
    }
    return ProbeReport(**(temel | alan))


def test_webgl_canvas_degismedi_tek_basina_tuslar_etkisiz_sayilmaz():
    rapor = _rapor(canvas_kind="webgl")

    assert not any("tuşlar" in sorun for sorun in rapor.problems())
    assert "tek başına kanıt değil" in rapor.summary()


def test_2d_canvas_degismedi_durum_kancasi_yoksa_hala_sorun():
    rapor = _rapor(canvas_kind="2d")

    assert any("tuşlar" in sorun for sorun in rapor.problems())


def test_degisen_canvas_durum_kancasi_yokken_etkilesim_kaniti_degil():
    rapor = _rapor(canvas_kind="webgl", canvas_changed=True)

    ozet = rapor.summary()
    assert "kanıt değil" in ozet and "__GAME_STATE__" in ozet


def test_favicon_notu_sorun_degil_bilgi_olarak_raporlanir():
    rapor = _rapor(canvas_kind="2d", canvas_changed=True, ignored_resources=("favicon.ico (404)",))

    assert rapor.problems() == ()
    assert "favicon.ico" in rapor.summary()


@pytest.fixture
def sunucu(tmp_path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a, **k: None  # type: ignore[method-assign]
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield tmp_path, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _calistir(url: str, tuslar: tuple[str, ...]) -> ProbeReport:
    pytest.importorskip("playwright")
    try:
        return asyncio.run(probe_game(url, tuslar))
    except Exception as hata:  # Chromium kurulu değilse ölçüm yapılamaz
        pytest.skip(f"tarayıcı yok: {hata}")


_FAVICONLU_OYUN = """<!doctype html><body><canvas id=c width=200 height=100></canvas><script>
const s={durum:'oynuyor',skor:0,oyuncu:{x:10}};const k=new Set();
addEventListener('keydown',e=>k.add(e.key));addEventListener('keyup',e=>k.delete(e.key));
const c=document.getElementById('c').getContext('2d');
(function f(){if(k.has('ArrowRight'))s.oyuncu.x+=2;c.fillStyle='#000';c.fillRect(0,0,200,100);
c.fillStyle='#fff';c.fillRect(s.oyuncu.x,50,10,10);requestAnimationFrame(f);})();
window.__GAME_STATE__=()=>s;
new Image().src='/favicon.ico';</script></body>"""


def test_favicon_404_calisan_oyunu_bozuk_raporlamaz(sunucu):
    kok, url = sunucu
    (kok / "index.html").write_text(_FAVICONLU_OYUN, encoding="utf-8")

    rapor = _calistir(url + "/index.html", ("ArrowRight",))

    assert rapor.console_errors == ()
    assert not any("konsol" in sorun for sorun in rapor.problems())
    assert any("favicon" in not_ for not_ in rapor.ignored_resources)


_GERCEK_HATALI_OYUN = _FAVICONLU_OYUN.replace(
    "new Image().src='/favicon.ico';", "setTimeout(()=>{throw new Error('gercek hata')},100);"
)


def test_gercek_runtime_hatasi_favicon_ayriminda_kaybolmaz(sunucu):
    kok, url = sunucu
    (kok / "index.html").write_text(_GERCEK_HATALI_OYUN, encoding="utf-8")

    rapor = _calistir(url + "/index.html", ("ArrowRight",))

    assert any("gercek hata" in sorun for sorun in rapor.problems())


_YOK_KAYNAKLI_OYUN = _FAVICONLU_OYUN.replace("/favicon.ico", "/sprite-yok.png")


def test_baska_kaynagin_404u_hala_sorun(sunucu):
    kok, url = sunucu
    (kok / "index.html").write_text(_YOK_KAYNAKLI_OYUN, encoding="utf-8")

    rapor = _calistir(url + "/index.html", ("ArrowRight",))

    assert any("sprite-yok.png" in sorun for sorun in rapor.problems())


# WebGL: tuşa basılınca üçgen kayar; durum kancası YOK ve preserveDrawingBuffer=false.
_WEBGL_OYUN = """<!doctype html><body><canvas id=c width=300 height=200></canvas><script>
const gl=document.getElementById('c').getContext('webgl');let x=-0.8;const k=new Set();
addEventListener('keydown',e=>k.add(e.key));addEventListener('keyup',e=>k.delete(e.key));
(function f(){if(k.has('ArrowRight'))x+=0.02;gl.enable(gl.SCISSOR_TEST);
gl.scissor(0,0,300,200);gl.clearColor(0,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);
gl.scissor(Math.round((x+1)*140),90,20,20);gl.clearColor(1,1,1,1);gl.clear(gl.COLOR_BUFFER_BIT);
requestAnimationFrame(f);})();</script></body>"""


def test_webgl_oyununda_tus_etkisi_olculur_ve_yanlis_alarm_yok(sunucu):
    kok, url = sunucu
    (kok / "index.html").write_text(_WEBGL_OYUN, encoding="utf-8")

    rapor = _calistir(url + "/index.html", ("ArrowRight",))

    if rapor.canvas_kind != "webgl":
        pytest.skip("bu tarayıcıda WebGL yok")
    assert not any("tuşlar" in sorun for sorun in rapor.problems())
    assert rapor.canvas_changed is True


def test_remotion_becerisi_kullanici_videosuna_sabit_marka_adi_koymaz():
    kaynak = (bundled_skills_dir() / "remotion-video" / "SKILL.md").read_text(encoding="utf-8")

    assert "ürün adı 'Fusion'" not in kaynak


_SAYFA = (
    "<!doctype html><title>Sayfa</title><body><h1>Merhaba dünya, bu sayfa yeterince uzun bir "
    "metin taşıyor ki boş sayılmasın.</h1><script>new Image().src='YOL';</script></body>"
)


@pytest.mark.parametrize(
    ("yol", "beklenen_sorun"), [("/favicon.ico", False), ("/gorsel-yok.png", True)]
)
def test_onizleme_sondasi_favicon_404unu_ayirir(sunucu, yol, beklenen_sorun):
    pytest.importorskip("playwright")
    kok, url = sunucu
    (kok / "index.html").write_text(_SAYFA.replace("YOL", yol), encoding="utf-8")

    try:
        sonuc = asyncio.run(probe(url + "/index.html"))
    except Exception as hata:
        pytest.skip(f"tarayıcı yok: {hata}")

    sorunlu = bool(sonuc.console_errors or sonuc.failed_resources)
    assert sorunlu is beklenen_sorun
