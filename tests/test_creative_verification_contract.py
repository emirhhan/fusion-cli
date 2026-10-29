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
import shutil
import subprocess
import threading

import pytest

from fusion_cli.config.paths import bundled_skills_dir
from fusion_cli.core.remotion_contract import (
    KitScenePlan,
    KitVerificationPlan,
    RegisteredKitContract,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import output_verify
from fusion_cli.engines.agent.output_verify import OutputPathVerifier
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

    assert 'ürün adı "Fusion"' not in kaynak
    assert '"Fusion" asla ekleme' in kaynak


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


# --- Remotion videosu: gerçek dosya, süre, çözünürlük, çözülebilirlik --------- #

_FFMPEG_VAR = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
ffmpeg_gerekli = pytest.mark.skipif(not _FFMPEG_VAR, reason="ffmpeg/ffprobe kurulu değil")


def _klip(yol, *, boyut="1920x1080", sure=3, fps=30):
    """Hareketli, gerçek bir H.264 klip (siyah/donuk bölüm içermez)."""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"testsrc2=size={boyut}:rate={fps}:duration={sure}",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", str(yol),
        ],
        check=True,
    )  # fmt: skip


def _baglam(kok, *, kare=90, sozlesme=True):
    baglam = ToolContext(root=kok)
    baglam.requested_outputs.add("out/video.mp4")
    baglam.touched.add(kok / "src.tsx")
    if sozlesme:
        plan = KitVerificationPlan("src/index.tsx", "Video", ("src",), 10.0, ())
        baglam.remotion_contract.register(
            RegisteredKitContract(plan, (KitScenePlan("a", "custom", kare),), ())
        )
    return baglam


@ffmpeg_gerekli
async def test_plana_uyan_gercek_video_kanit_ozeti_tasir(tmp_path):
    (tmp_path / "out").mkdir()
    _klip(tmp_path / "out/video.mp4")

    sonuc = await OutputPathVerifier(_baglam(tmp_path)).verify()

    assert sonuc.ok and sonuc.warnings == ()
    assert "1920x1080" in sonuc.summary and "3.0 sn" in sonuc.summary


@ffmpeg_gerekli
async def test_yanlis_cozunurluk_planla_uyusmuyor_sayilir(tmp_path):
    (tmp_path / "out").mkdir()
    _klip(tmp_path / "out/video.mp4", boyut="1280x720")

    sonuc = await OutputPathVerifier(_baglam(tmp_path)).verify()

    assert not sonuc.ok and "PLANA UYMUYOR" in sonuc.findings[0]
    assert "1280x720" in sonuc.findings[0]


@ffmpeg_gerekli
async def test_yanlis_sure_planla_uyusmuyor_sayilir(tmp_path):
    (tmp_path / "out").mkdir()
    _klip(tmp_path / "out/video.mp4", sure=2)

    sonuc = await OutputPathVerifier(_baglam(tmp_path)).verify()

    assert not sonuc.ok and "süre" in sonuc.findings[0]


@pytest.mark.parametrize("icerik", [b"", b"x", b"bu bir video degil" * 50])
async def test_video_olmayan_dosya_mp4_adiyla_gecmez(tmp_path, icerik):
    if not _FFMPEG_VAR and icerik:
        pytest.skip("ffprobe kurulu değil")
    (tmp_path / "out").mkdir()
    (tmp_path / "out/video.mp4").write_bytes(icerik)

    sonuc = await OutputPathVerifier(_baglam(tmp_path, sozlesme=False)).verify()

    assert not sonuc.ok and "VİDEO GEÇERSİZ" in sonuc.findings[0]


@ffmpeg_gerekli
async def test_kesilmis_video_cozulemiyor_sayilir(tmp_path):
    (tmp_path / "out").mkdir()
    hedef = tmp_path / "out/video.mp4"
    _klip(hedef)
    veri = hedef.read_bytes()
    # moov atom sonda değilse baştan bozulmuş sayılır; ortadan kesip sonuna çöp ekle.
    hedef.write_bytes(veri[: len(veri) // 2] + b"\x00" * 64)

    sonuc = await OutputPathVerifier(_baglam(tmp_path, sozlesme=False)).verify()

    assert not sonuc.ok


async def test_ffprobe_yoksa_sessiz_gecmez_not_measured_uyarisi_verir(tmp_path, monkeypatch):
    (tmp_path / "out").mkdir()
    (tmp_path / "out/video.mp4").write_bytes(b"x" * 100)
    from fusion_cli.tools import video_evidence

    monkeypatch.setattr(video_evidence.shutil, "which", lambda ad: None)
    monkeypatch.setattr(output_verify.shutil, "which", lambda ad: None)

    sonuc = await OutputPathVerifier(_baglam(tmp_path, sozlesme=False)).verify()

    assert sonuc.ok
    assert any("not_measured" in uyari for uyari in sonuc.warnings)
