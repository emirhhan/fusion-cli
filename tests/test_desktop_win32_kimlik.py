"""Windows computer use (#430) kimlik sınırları: Fusion ata zinciri, UWP çerçevesi, UIA hatası.

Sahte API gerçekçi zincirleri taklit eder: Başlat menüsünden açılan Fusion'ın atası
explorer.exe'dir; explorer'ın ebeveyni (userinit) çoktan ölmüş ve pid'i başka sürece geçmiş
olabilir. UWP uygulamalarının (Ayarlar) üst düzey çerçevesi ApplicationFrameHost.exe'nindir.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fusion_cli.core.desktop_settings import DesktopSettings
from fusion_cli.tools import desktop_policy, desktop_win32_screen
from fusion_cli.tools.win32_api import WindowInfo
from tests.test_desktop_win32 import APP_PID, FUSION_PID, FakeApi, _context
from tests.test_desktop_win32 import win as win  # fikstür

EXPLORER_PID = 650
STALE_PID = 333
FRAME_PID = 1200
SETTINGS_PID = 1300


class ChainApi(FakeApi):
    """sidecar → Fusion.exe → explorer.exe → (bayat pid: başka uygulama); UWP Ayarlar."""

    def __init__(self) -> None:
        super().__init__()
        self.images.update(
            {
                700: r"C:\Program Files\Fusion\Fusion.exe",
                EXPLORER_PID: r"C:\Windows\explorer.exe",
                STALE_PID: r"C:\Program Files\Zoom\Zoom.exe",
                FRAME_PID: r"C:\Windows\System32\ApplicationFrameHost.exe",
                SETTINGS_PID: r"C:\Windows\ImmersiveControlPanel\SystemSettings.exe",
            }
        )
        self.parents = {FUSION_PID: 700, 700: EXPLORER_PID, EXPLORER_PID: STALE_PID}
        self.window_pids.update({20: EXPLORER_PID, 21: STALE_PID, 30: FRAME_PID})
        self.children = {30: [31, 32]}
        self.child_window_pids = {31: FRAME_PID, 32: SETTINGS_PID}
        self.rows = [
            WindowInfo(14, 700, (0, 0, 400, 300), True, False, "Fusion", False),
            WindowInfo(30, FRAME_PID, (500, 500, 900, 900), True, False, "Ayarlar", False),
            WindowInfo(11, APP_PID, (100, 100, 900, 700), True, False, "Not Defteri", False),
            WindowInfo(21, STALE_PID, (1200, 0, 1400, 200), True, False, "Zoom", False),
            WindowInfo(20, EXPLORER_PID, (0, 0, 1920, 1080), True, False, "Program Manager", False),
        ]

    def child_pids(self, hwnd):
        return [self.child_window_pids[child] for child in self.children.get(hwnd, [])]


@pytest.fixture
def chain(monkeypatch) -> ChainApi:
    fake = ChainApi()
    monkeypatch.setattr(desktop_win32_screen.desktop_win32, "api", lambda: fake)
    return fake


def test_fusion_zinciri_fusion_exe_de_durur_explorer_ve_bayat_pid_dahil_degil(chain) -> None:
    assert desktop_win32_screen.fusion_pids(chain) == [FUSION_PID, 700]


def test_fusion_exe_bulunmazsa_kabuk_surecinde_durur(chain) -> None:
    chain.images[700] = r"C:\Python\python.exe"  # ara süreç (venv başlatıcısı)
    assert desktop_win32_screen.fusion_pids(chain) == [FUSION_PID, 700]


def test_explorer_penceresi_karartilmaz_ekran_tamamen_siyah_olmaz(chain) -> None:
    rects = desktop_win32_screen.mask_rects(chain, DesktopSettings(), (0, 0, 1920, 1080))
    assert rects == [(0, 0, 400, 300)]  # yalnız Fusion


def test_explorer_ve_bayat_pid_fusion_sayilmaz(chain) -> None:
    for hwnd, app in ((20, "explorer"), (21, "Zoom")):
        chain.at_point = hwnd
        answer = desktop_win32_screen.probe({"point": [1.0, 1.0]}, chain, element=lambda x, y: {})
        assert answer["app"] == app


async def test_gorev_cubuguna_tiklama_fusion_diye_engellenmez(chain, tmp_path) -> None:
    chain.at_point = 20
    context = _context(tmp_path, enabled=True)

    async def probe(request):
        return desktop_win32_screen.probe(request, chain, element=lambda x, y: {})

    assessment = await desktop_policy.assess("desktop_click", {"x": 5, "y": 5}, context, probe)
    assert assessment is not None and assessment.blocked is None


def test_uwp_cercevesi_barindirdigi_uygulamayla_tanimlanir(chain) -> None:
    chain.at_point = 30
    answer = desktop_win32_screen.probe({"point": [600.0, 600.0]}, chain, element=lambda x, y: {})
    assert (answer["app"], answer["bundle"], answer["pid"]) == (
        "SystemSettings",
        "systemsettings.exe",
        SETTINGS_PID,
    )


def test_cozulemeyen_uwp_cercevesi_hedef_sayilmaz(chain) -> None:
    chain.children = {}
    chain.at_point = 30
    assert desktop_win32_screen.probe({"point": [1.0, 1.0]}, chain)["ok"] is False


async def test_windows_ayarlari_her_eylemde_sorulur(chain, tmp_path) -> None:
    chain.at_point = 30
    context = _context(tmp_path, enabled=True)

    async def probe(request):
        return desktop_win32_screen.probe(request, chain, element=lambda x, y: {})

    assessment = await desktop_policy.assess("desktop_click", {"x": 5, "y": 5}, context, probe)
    assert assessment is not None and assessment.risky is not None
    assert "sistem ayarları" in assessment.risky


def test_reddedilen_uwp_uygulamasi_karartilir_ve_gizlemede_korunur(chain) -> None:
    settings = DesktopSettings(denied_apps=("SystemSettings",))
    rects = desktop_win32_screen.mask_rects(chain, settings, (0, 0, 1920, 1080))
    assert (500, 500, 900, 900) in rects
    assert "SystemSettings" in desktop_win32_screen.running_apps(chain)
    hidden = desktop_win32_screen.hide((SETTINGS_PID, FUSION_PID, 700), chain)
    assert SETTINGS_PID not in hidden and (30, 7) not in chain.shown


@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired("powershell.exe", 8), OSError("yok")],
)
def test_uia_hatasi_ogeyi_dogrulanamadi_isaretler(monkeypatch, failure) -> None:
    def boom(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(desktop_win32_screen.subprocess, "run", boom)
    assert desktop_win32_screen.element_at(1, 2) == {"unverified": "1"}


async def test_dogrulanamayan_ogeye_tiklama_her_seferinde_sorulur(win, tmp_path: Path) -> None:
    context = _context(tmp_path, enabled=True)

    async def probe(request):
        return desktop_win32_screen.probe(request, win, element=lambda x, y: {"unverified": "1"})

    assessment = await desktop_policy.assess("desktop_click", {"x": 5, "y": 5}, context, probe)
    assert assessment is not None and assessment.blocked is None
    assert assessment.risky is not None and "doğrulanamadı" in assessment.risky
