"""Ekran görüntüsü ölçeği, çerçeve bildirimi, bölge zoom ve ekran seçimi (P-030)."""

from __future__ import annotations

import struct
import subprocess
import zlib
from pathlib import Path

import pytest

from fusion_cli.core.desktop_frame import DesktopFrame, DesktopView
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_screen
from fusion_cli.tools.desktop_screen import Display


def _png(width: int, height: int) -> bytes:
    """Geçerli IHDR'li en küçük PNG; `sips` taklidi de bununla yazar."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    return (
        b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + chunk + struct.pack(">I", zlib.crc32(chunk))
    )


def _retina(monkeypatch, *, width_px: int = 2880, displays=None) -> list[list[str]]:
    """Ana ekran 1440x900 nokta; screencapture 2x piksel yazar, sips istenen genişliğe iner."""
    monkeypatch.setattr(desktop_screen, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_screen, "_screen_recording_denied", lambda: False)
    monkeypatch.setattr(
        desktop_screen, "_native_capture", lambda display, max_width, *_, **__: None
    )
    # Geri düşüşte ekrandaki engelli uygulama denetimi gerçek pencereleri okumasın.
    monkeypatch.setattr(desktop_screen, "_hidden_apps_on_screen", lambda settings: ())
    monkeypatch.setattr(
        desktop_screen,
        "list_displays",
        lambda: displays or (Display(1, 0.0, 0.0, 1440.0, 900.0, True),),
    )
    komutlar: list[list[str]] = []

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        komutlar.append(command)
        hedef = Path(command[-1])
        if command[0] == "screencapture":
            hedef.write_bytes(_png(width_px, width_px * 900 // 1440))
        elif command[0] == "sips":
            istenen = int(command[2])
            hedef.write_bytes(_png(istenen, istenen * 900 // 1440))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(desktop_screen, "_run", fake_run)
    return komutlar


def test_retina_goruntusu_kucultulur_ve_cerceve_bildirilir(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): ham 2880 px görüntü modele gidiyor, ölçek bildirilmiyordu."""
    komutlar = _retina(monkeypatch)
    context = ToolContext(root=tmp_path)

    sonuc = desktop_screen.desktop_screenshot({"path": "s.png"}, context)

    assert sonuc.ok, sonuc.output
    assert [k[0] for k in komutlar] == ["screencapture", "sips"]
    # #453: sabit hedef (en-boy korunur): 1440x900 → 1395 genişlik.
    assert komutlar[1][:3] == ["sips", "--resampleWidth", "1395"]
    cerceve = context.desktop.frame
    assert cerceve is not None and cerceve.image_width == 1395
    assert cerceve.to_point(1395, 0) == (1440.0, 0.0)
    assert "1395x871 px" in sonuc.output and "1440x900 nokta" in sonuc.output
    assert sonuc.images[0].startswith("data:image/png;base64,")


def test_kucuk_goruntu_kucultulmez(tmp_path, monkeypatch) -> None:
    komutlar = _retina(monkeypatch, width_px=1280)

    sonuc = desktop_screen.desktop_screenshot({"path": "s.png"}, ToolContext(root=tmp_path))

    assert sonuc.ok and [k[0] for k in komutlar] == ["screencapture"]


def test_hedef_genislik_sabit_eski_ayar_yok_sayilir(tmp_path, monkeypatch) -> None:
    """#448, #453: Claude 3456x2234'ü ~1372x887'ye indirir; hedefi değiştiren ayar yok."""
    from fusion_cli.core.desktop_frame import screenshot_target_width

    assert screenshot_target_width(3456, 2234) == 1372
    assert screenshot_target_width(1728, 1117) == 1372
    komutlar = _retina(monkeypatch)

    desktop_screen.desktop_screenshot(
        {"path": "s.png"}, ToolContext(root=tmp_path, desktop_screenshot_max_width=800)
    )

    assert komutlar[1][2] == str(screenshot_target_width(1440, 900)) == "1395"


def test_bolge_zoom_tam_goruntu_koordinatiyla_cekilir(tmp_path, monkeypatch) -> None:
    komutlar = _retina(monkeypatch)
    context = ToolContext(root=tmp_path)
    desktop_screen.desktop_screenshot({"path": "s.png"}, context)
    onceki = context.desktop.frame

    sonuc = desktop_screen.desktop_screenshot(
        {"path": "z.png", "region": "784,490,100,50"}, context
    )

    assert sonuc.ok, sonuc.output
    # 784 px * (1440/1395) ≈ 809 nokta; 100 px → 103 nokta.
    assert komutlar[-2][4] == "-R" and komutlar[-2][5] == "809,506,103,52"
    assert "KIRPIK" in sonuc.output and "784,490" in sonuc.output
    assert context.desktop.frame is onceki


def test_bolge_hatalari_reddedilir(tmp_path, monkeypatch) -> None:
    _retina(monkeypatch)
    context = ToolContext(root=tmp_path)
    desktop_screen.desktop_screenshot({"path": "s.png"}, context)

    assert not desktop_screen.desktop_screenshot({"region": "a,b"}, context).ok
    assert not desktop_screen.desktop_screenshot({"region": "0,0,0,5"}, context).ok
    assert not desktop_screen.desktop_screenshot({"region": "5000,0,10,10"}, context).ok


def test_ekran_secimi_screencapture_d_ile_gider(tmp_path, monkeypatch) -> None:
    ekranlar = (
        Display(1, 0.0, 0.0, 1440.0, 900.0, True),
        Display(2, 1440.0, -200.0, 2560.0, 1440.0, False),
    )
    komutlar = _retina(monkeypatch, displays=ekranlar)
    context = ToolContext(root=tmp_path)

    sonuc = desktop_screen.desktop_screenshot({"path": "s.png", "display": 2}, context)

    assert sonuc.ok and komutlar[0][4:6] == ["-D", "2"]
    assert context.desktop.frame is not None and context.desktop.frame.origin_x == 1440.0
    assert not desktop_screen.desktop_screenshot({"display": 3}, context).ok
    liste = desktop_screen.desktop_displays({}, context)
    assert liste.ok and "2: 2560x1440 nokta, sol üst (1440,-200)" in liste.output


def test_ekran_kaydi_izni_yoksa_yapisal_hata(tmp_path, monkeypatch) -> None:
    _retina(monkeypatch)
    monkeypatch.setattr(desktop_screen, "_screen_recording_denied", lambda: True)

    sonuc = desktop_screen.desktop_screenshot({}, ToolContext(root=tmp_path))

    assert not sonuc.ok and sonuc.structured == {
        "izin_gerekli": "screen_recording",
        "ayar_baglantisi": desktop_screen.permission_failure("screen_recording").structured[
            "ayar_baglantisi"
        ],  # type: ignore[index]
    }


def test_varsayilan_yol_depoya_karismaz_ve_touched_isaretlenir(tmp_path, monkeypatch) -> None:
    komutlar = _retina(monkeypatch, width_px=1000)
    context = ToolContext(root=tmp_path)

    sonuc = desktop_screen.desktop_screenshot({}, context)

    assert sonuc.ok and ".fusion/tmp" in komutlar[0][-1]
    assert any(".fusion" in str(p) for p in context.touched)


def test_png_basligi_okunur() -> None:
    assert desktop_screen.png_size(_png(12, 7)) == (12, 7)
    assert desktop_screen.png_size(b"JPEG") is None


@pytest.mark.parametrize(("x", "y", "beklenen"), [(0, 0, (10.0, 20.0)), (100, 50, (60.0, 45.0))])
def test_cerceve_pikseli_noktaya_cevirir(x, y, beklenen) -> None:
    cerceve = DesktopFrame(200, 100, 10.0, 20.0, 100.0, 50.0, 1)
    assert cerceve.to_point(x, y) == beklenen
    bos = DesktopView()
    assert bos.to_point(3, 4) == (3.0, 4.0)


# --- P-033: Fusion penceresi görüntüden hariç ----------------------------------------------


def test_fusion_penceresi_haric_yakalama_once_denenir(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): screencapture Fusion'ın kendi sohbet penceresini de görüntüye alıyordu."""
    komutlar = _retina(monkeypatch)
    istekler: list[tuple[Display, int]] = []
    monkeypatch.setattr(
        desktop_screen,
        "_native_capture",
        lambda display, max_width, *_, **__: (
            istekler.append((display, max_width)) or _png(1395, 872)
        ),
    )
    context = ToolContext(root=tmp_path)

    sonuc = desktop_screen.desktop_screenshot({"path": "s.png"}, context)

    assert sonuc.ok and komutlar == [] and istekler[0][1] == 1395
    assert context.desktop.frame is not None and context.desktop.frame.image_width == 1395


def test_haric_tutma_kapaliysa_veya_basarisizsa_screencapture(tmp_path, monkeypatch) -> None:
    komutlar = _retina(monkeypatch)
    assert desktop_screen.desktop_screenshot({"path": "a.png"}, ToolContext(root=tmp_path)).ok
    cagrildi: list[bool] = []
    monkeypatch.setattr(
        desktop_screen,
        "_native_capture",
        lambda display, max_width, *_, exclude_fusion=True, **__: cagrildi.append(exclude_fusion),
    )
    kapali = ToolContext(root=tmp_path, desktop_exclude_fusion_window=False)
    assert desktop_screen.desktop_screenshot({"path": "b.png"}, kapali).ok

    # #448: Fusion penceresi her zaman dışlanır; eski ayar yok sayılır.
    assert [k[0] for k in komutlar][:1] == ["screencapture"] and cagrildi == [True]


def test_yerel_yakalama_sonucu_cozulur(monkeypatch) -> None:
    import base64

    monkeypatch.setattr(desktop_screen, "_exclude_pids", lambda: [10, 20])
    ekran = Display(1, 0.0, 0.0, 1440.0, 900.0, True, identifier=7)
    istek: dict[str, object] = {}

    def fake_invoke(operation: str, target: dict[str, object]) -> dict[str, object]:
        istek.update(target, operation=operation)
        return {
            "ok": True,
            "image": "data:image/png;base64," + base64.b64encode(_png(4, 2)).decode(),
        }

    monkeypatch.setattr(desktop_screen, "invoke_sync", fake_invoke)

    assert desktop_screen._native_capture(ekran, 800) == _png(4, 2)
    assert istek["operation"] == "screen" and istek["id"] == 7
    assert istek["request"]["maxWidth"] == 800  # type: ignore[index]
    assert istek["request"]["excludePids"] == [10, 20]  # type: ignore[index]
    monkeypatch.setattr(desktop_screen, "invoke_sync", lambda *_: {"ok": False})
    assert desktop_screen._native_capture(ekran, 800) is None
    assert desktop_screen._native_capture(Display(1, 0, 0, 1, 1, True), 800) is None


def test_ata_surecler_launchd_ye_kadar_dislanir(monkeypatch) -> None:
    """Ölçüldü (31 Ekim): yalnız pid+ppid dışlanıyordu; terminalden koşan fusion'ın ebeveyni zsh
    olduğu için Terminal.app penceresi görüntüde kalıyordu."""
    ebeveynler = {500: "  400\n", 400: "300\n", 300: "1\n"}

    def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        assert command[:3] == ["ps", "-o", "ppid="]
        return subprocess.CompletedProcess(command, 0, ebeveynler.get(int(command[-1]), ""), "")

    monkeypatch.setattr(desktop_screen, "_run", fake_run)

    assert desktop_screen._ancestor_pids(500) == (400, 300)
    assert desktop_screen._ancestor_pids(999) == ()
    assert desktop_screen._ancestor_pids(500, depth=1) == (400,)


def test_bolge_notu_ve_ekran_uyusmazligi(tmp_path, monkeypatch) -> None:
    """Ölçüldü (31 Ekim): not 'büyütülmüş' diyordu; `display` verilse de bölge önceki çerçevenin
    ekranından kırpılıyordu."""
    iki_ekran = (
        Display(1, 0.0, 0.0, 1440.0, 900.0, True),
        Display(2, 1440.0, 0.0, 1920.0, 1080.0, False),
    )
    _retina(monkeypatch, displays=iki_ekran)
    context = ToolContext(root=tmp_path)
    context.desktop.frame = DesktopFrame(1568, 980, 1440.0, 0.0, 1920.0, 1080.0, 2)

    uyumsuz = desktop_screen.desktop_screenshot(
        {"path": "r.png", "region": "0,0,100,100", "display": 1}, context
    )
    uyumlu = desktop_screen.desktop_screenshot(
        {"path": "r.png", "region": "0,0,100,100", "display": 2}, context
    )

    assert not uyumsuz.ok and "ekranına (2)" in uyumsuz.output
    assert uyumlu.ok and "büyütülmüş" not in uyumlu.output and "ham ekran pikseli" in uyumlu.output


def test_ekran_listesi_okunamazsa_acik_hata(monkeypatch) -> None:
    monkeypatch.setattr(desktop_screen, "_mac_only", lambda: None)
    monkeypatch.setattr(desktop_screen, "list_displays", lambda: ())

    sonuc = desktop_screen.desktop_displays({}, ToolContext(root=Path("/")))

    assert not sonuc.ok and "Ekran listesi" in sonuc.output
