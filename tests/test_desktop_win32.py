"""Windows computer use (#430): yüzey kapısı, SendInput planları, hedef, yakalama, gizleme.

Gerçek Win32 çağrısı yapılmaz: `desktop_win32.api` sahte API ile değiştirilir, platform
`sys.platform` yaması ile Windows sayılır.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from PIL import Image

from fusion_cli.core.desktop_frame import DesktopFrame
from fusion_cli.core.desktop_settings import DesktopLevel, DesktopSettings
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import (
    desktop,
    desktop_lock,
    desktop_mouse,
    desktop_permissions,
    desktop_policy,
    desktop_screen,
    desktop_turn,
    desktop_win32,
    desktop_win32_screen,
)
from fusion_cli.tools.key_spec import KeyChord
from fusion_cli.tools.win32_api import (
    INPUT_KEYBOARD,
    INPUT_MOUSE,
    LLKHF_INJECTED,
    VK_ESCAPE,
    Win32Api,
    WindowInfo,
    is_physical_escape,
)

FUSION_PID = os.getpid()
APP_PID = 900


def test_carpma_tusu_windows_girdisine_donusur() -> None:
    specs = desktop_win32.chord_inputs(KeyChord("*"))

    assert [spec.vk for spec in specs] == [0x6A, 0x6A]
    assert [bool(spec.flags & 0x2) for spec in specs] == [False, True]


class FakeApi:
    """Win32Api'nin sahte eşi: girdileri kaydeder, pencere/süreç tablosu verilir."""

    def __init__(self) -> None:
        self.sent: list = []
        self.shown: list[tuple[int, int]] = []
        self.images = {
            APP_PID: r"C:\Windows\System32\notepad.exe",
            901: r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            902: r"C:\Program Files\1Password\1Password.exe",
            700: r"C:\Program Files\Fusion\Fusion.exe",
        }
        self.parents = {FUSION_PID: 700, 700: 4}
        self.at_point = 11
        self.front = 11
        self.window_pids = {11: APP_PID, 12: 901, 13: 902, 14: 700}
        self.rows = [
            WindowInfo(14, 700, (0, 0, 400, 300), True, False, "Fusion", False),
            WindowInfo(11, APP_PID, (100, 100, 900, 700), True, False, "Not Defteri", False),
            WindowInfo(13, 902, (1000, 0, 1400, 400), True, False, "1Password", False),
            WindowInfo(12, 901, (0, 0, 1920, 1080), True, True, "Chrome", False),
            WindowInfo(15, APP_PID, (0, 0, 10, 10), True, False, "", True),
        ]

    def send(self, specs) -> None:
        self.sent.extend(specs)

    def virtual_screen(self):
        return (0, 0, 1921, 1081)

    def monitors(self):
        return [(1920, 0, 1280, 1024, False), (0, 0, 1920, 1080, True)]

    def window_at(self, x, y):
        return self.at_point

    def foreground(self):
        return self.front

    def window_pid(self, hwnd):
        return self.window_pids.get(hwnd, 0)

    def process_image(self, pid):
        return self.images.get(pid)

    def parent_pids(self):
        return self.parents

    def windows(self):
        return list(self.rows)

    def show(self, hwnd, command):
        self.shown.append((hwnd, command))

    def capture(self, left, top, width, height):
        return b"\xff" * (width * height * 4)

    def escape_hook(self, on_escape):
        self.escape = on_escape
        return lambda: None


@pytest.fixture
def win(monkeypatch) -> FakeApi:
    fake = FakeApi()
    monkeypatch.setattr(desktop_win32.sys, "platform", "win32")
    monkeypatch.setattr(desktop_win32, "api", lambda: fake)
    monkeypatch.setattr(desktop_lock, "claim", lambda **_: None)
    # Bu Mac'te `_mac_only` None döner; Windows'ta macOS hatası verir.
    monkeypatch.setattr(desktop, "_mac_only", lambda: "yalnız macOS")
    monkeypatch.setattr(desktop_mouse, "_mac_only", lambda: "yalnız macOS")
    monkeypatch.setattr(desktop_screen, "_mac_only", lambda: "yalnız macOS")
    desktop_turn.use_app_surface(True)
    yield fake
    desktop_turn.use_app_surface(False)


def _context(tmp_path: Path, **settings) -> ToolContext:
    context = ToolContext(root=tmp_path, desktop_settings=DesktopSettings(**settings))
    context.desktop.frame = DesktopFrame(1920, 1080, 0.0, 0.0, 1920.0, 1080.0, 1)
    return context


# --- yüzey kapısı ------------------------------------------------------------------------


def test_windowsta_cli_computer_use_kapali_masaustu_uygulamasinda_acik(monkeypatch) -> None:
    monkeypatch.setattr(desktop_win32.sys, "platform", "win32")
    desktop_turn.use_app_surface(False)
    assert desktop_win32.gate("yalnız macOS") == desktop_win32.CLI_MESSAGE
    desktop_turn.use_app_surface(True)
    try:
        assert desktop_win32.gate("yalnız macOS") is None
    finally:
        desktop_turn.use_app_surface(False)


def test_macos_ve_linux_kapi_degismez(monkeypatch) -> None:
    monkeypatch.setattr(desktop_win32.sys, "platform", "linux")
    assert desktop_win32.gate("yalnız macOS") == "yalnız macOS"
    assert desktop_win32.gate(None) is None


def test_cli_de_windows_fare_araci_claude_gibi_reddeder(win, tmp_path) -> None:
    desktop_turn.use_app_surface(False)
    result = desktop_mouse.desktop_mouse({"x": 10, "y": 10}, _context(tmp_path))
    assert not result.ok and "yalnız Fusion masaüstü uygulamasında" in result.output
    assert win.sent == []


# --- girdi planları ----------------------------------------------------------------------


def test_tik_mutlak_sanal_masaustu_koordinatiyla_gider(win, tmp_path) -> None:
    result = desktop_mouse.desktop_mouse({"x": 960, "y": 540}, _context(tmp_path))
    assert result.ok, result.output
    assert [spec.kind for spec in win.sent] == [INPUT_MOUSE] * 3
    move, down, up = win.sent
    assert (move.dx, move.dy) == (32768, 32768)
    assert down.flags & 0x2 and up.flags & 0x4 and all(s.flags & 0x8000 for s in win.sent)


def test_degistiricili_tik_tuslari_sarar(win, tmp_path) -> None:
    result = desktop_mouse.desktop_mouse(
        {"x": 1, "y": 1, "modifiers": "ctrl+shift"}, _context(tmp_path)
    )
    assert result.ok
    keys = [(s.vk, bool(s.flags & 0x2)) for s in win.sent if s.kind == INPUT_KEYBOARD]
    assert keys == [(0x11, False), (0x10, False), (0x10, True), (0x11, True)]
    assert win.sent[0].kind == INPUT_KEYBOARD and win.sent[-1].kind == INPUT_KEYBOARD


def test_sag_orta_ve_surukleme_bayraklari(win) -> None:
    plan = desktop_mouse.mouse_plan("right_click", (5, 5))
    assert [s.flags & 0x18 for s in desktop_win32.mouse_inputs(plan, (0, 0, 100, 100))] == [
        0,
        0x8,
        0x10,
    ]
    drag = desktop_win32.mouse_inputs(
        desktop_mouse.mouse_plan("drag", (0, 0), (50, 50)), (0, 0, 101, 101)
    )
    assert drag[1].flags & 0x2 and drag[-1].flags & 0x4
    assert (drag[-1].dx, drag[-1].dy) == (32768, 32768)


def test_kaydirma_yonleri() -> None:
    up, left = desktop_win32.scroll_inputs(3, 2)
    assert up.flags == 0x800 and up.data == 360
    assert left.flags == 0x1000 and left.data == -240  # pozitif delta_x = sola


def test_tus_akoru_ve_uzatilmis_tuslar() -> None:
    specs = desktop_win32.chord_inputs(KeyChord("c", control=True))
    assert [(s.vk, bool(s.flags & 0x2)) for s in specs] == [
        (0x11, False),
        (0x43, False),
        (0x43, True),
        (0x11, True),
    ]
    assert desktop_win32.chord_inputs(KeyChord("left"))[0].flags & 0x1
    assert desktop_win32.chord_inputs(KeyChord("r", command=True))[0].vk == 0x5B


def test_macos_tus_tablosundaki_her_tusun_windows_karsiligi_var() -> None:
    assert set(desktop.KEY_CODES) <= set(desktop_win32.VK_CODES)


def test_unicode_metin_ve_satir_sonu() -> None:
    specs = desktop_win32.text_inputs("ç\r\n🙂")
    unicode = [s.scan for s in specs if s.flags & 0x4 and not s.flags & 0x2]
    assert unicode == [0xE7, 0xD83D, 0xDE42]
    assert [s.vk for s in specs if s.vk] == [0x0D, 0x0D]


def test_desktop_key_ve_type_izin_sormadan_gonderir(win, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop, "_framework", lambda: pytest.fail("macOS çerçevesi çağrıldı"))
    assert desktop.desktop_key({"key": "ctrl+s"}, _context(tmp_path)).ok
    assert desktop.desktop_type({"text": "ab"}, _context(tmp_path)).ok
    assert len(win.sent) == 4 + 4


def test_kaydirma_araci_once_imleci_tasir(win, tmp_path) -> None:
    result = desktop_mouse.desktop_scroll({"lines": -2, "x": 10, "y": 10}, _context(tmp_path))
    assert result.ok
    assert win.sent[0].flags & 0x1 and win.sent[-1].data == -240


# --- hedef ve politika -------------------------------------------------------------------


def test_nokta_hedefi_exe_ile_cozulur_ve_oge_okunur(win) -> None:
    answer = desktop_win32_screen.probe(
        {"point": [10.0, 20.0]}, win, element=lambda x, y: {"role": "Button", "title": "Gönder"}
    )
    assert answer == {
        "ok": True,
        "app": "notepad",
        "bundle": "notepad.exe",
        "pid": APP_PID,
        "element": {"role": "Button", "title": "Gönder"},
    }


def test_fusion_penceresi_fusion_kimligi_alir_okunamayan_surec_cozulmez(win) -> None:
    win.front = 14
    assert desktop_win32_screen.probe({}, win)["bundle"] == "com.fusion.desktop"
    win.front = 99
    assert desktop_win32_screen.probe({}, win)["ok"] is False
    assert desktop_win32_screen.probe({"pid": 5}, win)["ok"] is False


async def _assess(tool, args, context, win):
    async def probe(request):
        return desktop_win32_screen.probe(request, win, element=lambda x, y: {})

    return await desktop_policy.assess(tool, args, context, probe)


@pytest.mark.parametrize(
    ("hwnd", "denied", "blocked"),
    [
        (11, (), False),
        (11, ("Notepad",), True),  # ret listesi exe köküyle
        (14, (), True),  # Fusion'ın kendi penceresi
        (12, (), True),  # tarayıcı: yalnız bak, tıklama kapalı
    ],
)
async def test_windows_hedefi_kademe_ve_ret_listesine_takilir(
    win, tmp_path, hwnd, denied, blocked
) -> None:
    win.at_point = hwnd
    context = _context(tmp_path, enabled=True, denied_apps=denied)
    assessment = await _assess("desktop_click", {"x": 5, "y": 5}, context, win)
    assert (assessment.blocked is not None) is blocked


@pytest.mark.parametrize(
    ("app", "bundle", "level"),
    [
        ("chrome", "chrome.exe", DesktopLevel.OBSERVE),
        ("terminal64", "terminal64.exe", DesktopLevel.OBSERVE),
        ("WindowsTerminal", "windowsterminal.exe", DesktopLevel.CLICK),
        ("Code", "code.exe", DesktopLevel.CLICK),
        ("explorer", "explorer.exe", DesktopLevel.FULL),
        ("Fusion", "fusion.exe", None),
    ],
)
def test_windows_exe_kategorileri(app, bundle, level) -> None:
    assert desktop_policy.app_level(DesktopSettings(), app, bundle)[0] is level


# --- yakalama ----------------------------------------------------------------------------


def test_karartma_fusion_ve_reddedilen_pencereler(win) -> None:
    settings = DesktopSettings(denied_apps=("1Password",))
    rects = desktop_win32_screen.mask_rects(win, settings, (0, 0, 1920, 1080))
    assert rects == [(0, 0, 400, 300), (1000, 0, 1400, 400)]  # küçültülmüş Chrome yok


def test_yakalamadan_dislanan_fusion_penceresi_karartilmaz(win) -> None:
    win.rows[0] = WindowInfo(14, 700, (0, 0, 400, 300), True, False, "Fusion", False, 0x11)
    assert desktop_win32_screen.mask_rects(win, DesktopSettings(), (0, 0, 1920, 1080)) == []


def test_capture_png_karartir_ve_kucultur(win) -> None:
    data = desktop_win32_screen.capture_png((0, 0, 1920, 1080), 960, DesktopSettings(), win)
    image = Image.open(io.BytesIO(data)).convert("RGB")
    assert image.size == (960, 540)
    assert image.getpixel((10, 10)) == (0, 0, 0)  # Fusion penceresi
    assert image.getpixel((900, 500)) == (255, 255, 255)


def test_windows_ekran_goruntusu_uctan_uca(win, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(desktop_screen, "_run", lambda command: pytest.fail("screencapture"))
    context = _context(tmp_path)
    context.desktop.frame = None
    result = desktop_screen.desktop_screenshot({}, context)
    assert result.ok, result.output
    frame = context.desktop.frame
    assert frame is not None and frame.display == 1 and frame.point_width == 1920.0
    assert frame.image_width == desktop_screen.screenshot_target_width(1920, 1080)


def test_windows_yakalama_basarisizsa_karartmasiz_geri_dusus_yok(win, tmp_path, monkeypatch):
    def broken(*_args):
        raise OSError("BitBlt")

    monkeypatch.setattr(win, "capture", broken)
    monkeypatch.setattr(desktop_screen, "_run", lambda command: pytest.fail("screencapture"))
    result = desktop_screen.desktop_screenshot({}, _context(tmp_path))
    assert not result.ok and "Windows" in result.output


def test_ekranlar_ana_ekran_once(win) -> None:
    displays = desktop_screen.list_displays()
    assert [(d.index, d.x, d.is_main) for d in displays] == [(1, 0.0, True), (2, 1920.0, False)]


# --- gizleme, Esc, izin, uygulama açma ---------------------------------------------------


def test_gizleme_korunanlari_birakir_yalniz_kucultulenleri_geri_acar(win) -> None:
    hidden = desktop_win32_screen.hide((700, FUSION_PID), win)
    assert hidden == (APP_PID, 902)
    assert win.shown == [(11, 7), (13, 7)]
    desktop_win32_screen.unhide((APP_PID,), win)
    assert win.shown[-1] == (11, 4)
    desktop_win32_screen.unhide((APP_PID,), win)  # ikinci kez: zaten geri açıldı
    assert len(win.shown) == 3
    desktop_win32_screen.unhide((902,), win)


def test_tur_varsayilanlari_windows_yolunu_kullanir(win) -> None:
    assert desktop_turn._default_hide((700, FUSION_PID)) == (APP_PID, 902)
    desktop_turn._default_unhide((APP_PID, 902))
    stop = desktop_turn._default_escape(lambda: None)
    assert callable(stop) and callable(win.escape)


def test_fiziksel_esc_enjekte_esc_degil() -> None:
    assert is_physical_escape(0x100, VK_ESCAPE, 0)
    assert not is_physical_escape(0x100, VK_ESCAPE, LLKHF_INJECTED)
    assert not is_physical_escape(0x100, 0x41, 0)
    assert not is_physical_escape(0x200, VK_ESCAPE, 0)


def test_windowsta_izin_adimi_yok(monkeypatch) -> None:
    monkeypatch.setattr(desktop_permissions.sys, "platform", "win32")
    status = desktop_permissions.probe()
    assert (status.accessibility, status.screen_recording) == ("granted", "granted")
    assert status.as_dict()["platform"] == "windows"
    assert desktop_permissions.request("accessibility").accessibility == "granted"


def test_uygulama_listesi_fusion_ve_arac_pencereleri_haric(win) -> None:
    assert desktop_win32_screen.running_apps(win) == ("1Password", "chrome", "notepad")


@pytest.mark.parametrize(
    "raw", [r"C:\x.bat", "https://ornek.com", r"..\kotu", "a/b", "", "x" * 90, "cmd & calc"]
)
def test_uygulama_adi_yol_url_ve_kabuk_karakteri_kabul_etmez(raw) -> None:
    assert desktop_win32_screen.resolve_app(raw) is None


def test_path_aramasi_goreli_klasoru_atlar(tmp_path, monkeypatch) -> None:
    (tmp_path / "araclar").mkdir()
    (tmp_path / "araclar" / "notepad.exe").write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "araclar")
    monkeypatch.setenv("APPDATA", "")
    monkeypatch.setenv("PROGRAMDATA", "")
    assert desktop_win32_screen.resolve_app("notepad") is None
    monkeypatch.setenv("PATH", str(tmp_path / "araclar"))
    assert desktop_win32_screen.resolve_app("notepad.exe") == tmp_path / "araclar" / "notepad.exe"


def test_windows_desktop_open_bulunamayan_uygulamada_acik_hata(win, tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("APPDATA", "")
    monkeypatch.setenv("PROGRAMDATA", "")
    result = desktop.desktop_open({"app": "yokboyleuygulama"}, ToolContext(root=tmp_path))
    assert not result.ok and "bulunamadı" in result.output


def test_gercek_win32_katmani_windows_disinda_acilmaz() -> None:
    with pytest.raises(OSError):
        Win32Api()
