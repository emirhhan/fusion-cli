"""CLI komutları — Typer üzerinden uçtan uca (ağ yok)."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from fusion_cli import __version__
from fusion_cli.cli import app as app_module
from fusion_cli.core.types import FusionResult, VerdictSource

runner = CliRunner()

#: ANSI kaçış dizilerini ayıklar.
#
# `FORCE_COLOR` kurulu bir kabukta rich sürüm numarasını boyuyor ve düz metin
# bekleyen doğrulama kırılıyordu. Renk bir sunum ayrıntısıdır; bu testin ölçtüğü
# şey değildir. Global bir ortam düzeltmesi denendi ve rengi BEKLEYEN başka bir
# testi bozdu — çözüm o yüzden yerel.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _duz(metin: str) -> str:
    return _ANSI.sub("", metin)


def test_version_surumu_basar():
    result = runner.invoke(app_module.app, ["version"])

    assert result.exit_code == 0
    assert __version__ in _duz(result.stdout)


def test_config_show_varsayilanlari_basar():
    result = runner.invoke(app_module.app, ["config", "show"])

    assert result.exit_code == 0
    assert "Fusion adayları" in result.stdout
    assert "Hakem" in result.stdout
    assert "max_tokens" in result.stdout


def test_run_bos_gorevi_reddeder():
    result = runner.invoke(app_module.app, ["run", "   "])

    assert result.exit_code != 0


def test_mcp_add_config_yaml_a_yazar(tmp_path, monkeypatch):
    """`fusion mcp-add` kullanıcının config.yaml içine dış MCP sunucusu ekler.

    Agent'ın kendi dosya araçlarıyla değil bu komut üzerinden ekleyebildiğini —
    ve eklenenin gerçekten diskte kalıcı olduğunu — doğrular.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    result = runner.invoke(
        app_module.app,
        ["mcp-add", "github", "npx", "--", "-y", "server-github"],
    )

    assert result.exit_code == 0
    yazilan = (tmp_path / "fusion-cli" / "config.yaml").read_text(encoding="utf-8")
    assert "name: github" in yazilan
    assert "command: npx" in yazilan
    assert "server-github" in yazilan


def _sonuc(source):
    return FusionResult(
        task="t",
        task_type="general",
        winner="a",
        final_answer="cevap",
        source=source,
        candidates=(),
    )


def _sahte_tur(monkeypatch, source, kayit=None):
    async def _sahte(task, config, *, sinks, task_type="general", synthesis=None, memory=None):
        if kayit is not None:
            kayit.update(task_type=task_type, synthesis=synthesis)
        return _sonuc(source)

    monkeypatch.setattr(app_module, "run_task", _sahte)


def test_run_basarili_sonucta_sifir_doner(monkeypatch):
    _sahte_tur(monkeypatch, VerdictSource.JUDGE)

    assert runner.invoke(app_module.app, ["run", "merhaba", "--no-memory"]).exit_code == 0


def test_run_cevapsiz_sonucta_bir_doner(monkeypatch):
    _sahte_tur(monkeypatch, VerdictSource.NONE)

    assert runner.invoke(app_module.app, ["run", "merhaba", "--no-memory"]).exit_code == 1


def test_run_gecersiz_gorev_tipini_reddeder():
    result = runner.invoke(app_module.app, ["run", "merhaba", "--type", "olmayan"])

    assert result.exit_code != 0


def test_run_secenekleri_oturuma_gecirilir(monkeypatch):
    kayit = {}
    _sahte_tur(monkeypatch, VerdictSource.JUDGE, kayit)

    runner.invoke(
        app_module.app, ["run", "merhaba", "--type", "code", "--no-synthesis", "--no-memory"]
    )

    assert kayit == {"task_type": "code", "synthesis": False}


# --- Giriş ekranı ------------------------------------------------------------ #


def test_karsilama_kaydirma_gecmisini_de_temizler():
    """console.clear() yalnızca görünen ekranı siler; scrollback kalır.

    Kullanıcı fusion'a girip yukarı kaydırınca eski terminal mesajlarını görüyordu —
    bir CLI uygulamasına girilmiş hissi vermiyordu. `ESC [ 3 J` scrollback'i de siler.
    """
    import io

    from rich.console import Console

    from fusion_cli.ui import banner

    tampon = io.StringIO()
    console = Console(file=tampon, width=80, force_terminal=True)

    banner.print_welcome(console, banner.SessionInfo(**_ornek_oturum()), clear=True)

    assert "\x1b[3J" in tampon.getvalue(), "scrollback temizleme dizisi yazılmadı"


def test_temizleme_kapaliyken_scrollback_silinmez():
    """İlk mesajdan sonraki yeniden çizimlerde geçmiş korunmalı."""
    import io

    from rich.console import Console

    from fusion_cli.ui import banner

    tampon = io.StringIO()
    console = Console(file=tampon, width=80, force_terminal=True)

    banner.print_welcome(console, banner.SessionInfo(**_ornek_oturum()), clear=False)

    assert "\x1b[3J" not in tampon.getvalue()


def _ornek_oturum() -> dict:
    import dataclasses

    from fusion_cli.ui.banner import SessionInfo

    alanlar = {f.name: f for f in dataclasses.fields(SessionInfo)}
    ornek: dict = {}
    for ad, alan in alanlar.items():
        if alan.type in ("str", str) or "str" in str(alan.type):
            ornek[ad] = "x"
        elif "bool" in str(alan.type):
            ornek[ad] = True
        elif "int" in str(alan.type):
            ornek[ad] = 1
        else:
            ornek[ad] = "x"
    return ornek


def test_modul_olarak_calistirilinca_komut_isler():
    """`python -m fusion_cli.cli.app` konsol girişiyle AYNI yolu izlemeli.

    Ölçüldü: `__main__` bloğu yokken modül yalnız içe aktarılıyor, hiçbir komut
    çalıştırmadan sessizce 0 ile çıkıyordu. Kurulum sarmalayıcıları bu yolu
    kullandığı için `fusion` komutu hiçbir şey yapmıyormuş gibi görünüyordu —
    hata yalnız sarmalayıcıdan çağrılınca ortaya çıktığı için testlerden kaçıyordu.
    """
    import subprocess
    import sys

    sonuc = subprocess.run(
        [sys.executable, "-m", "fusion_cli.cli.app", "version"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert sonuc.returncode == 0, sonuc.stderr
    assert "fusion-cli" in sonuc.stdout


# --- Dalga 4: hata çıktısı stderr'e gider, traceback yerelleri basmaz (L1-11, L1-12) --- #


def test_beklenen_hata_stdout_yerine_stderr_e_yazilir(monkeypatch, capsys):
    """Ölçüldü (30 Ekim): `main()` FusionError'ı stdout'a basıyordu; `fusion mcp` ve
    `fusion app` protokol akışına düz metin karışıyordu."""
    import pytest

    from fusion_cli.cli import app as cli_app
    from fusion_cli.core.errors import FusionError

    def _patlat(**kwargs):
        raise FusionError("protokol dışı bozuk [/x]")

    monkeypatch.setattr(cli_app, "app", _patlat)

    with pytest.raises(SystemExit) as cikis:
        cli_app.main()

    yakalanan = capsys.readouterr()
    assert cikis.value.code == 1
    assert yakalanan.out == ""
    assert "protokol dışı bozuk [/x]" in yakalanan.err


def test_typer_beklenmeyen_hatada_yerel_degiskenleri_gostermez():
    from fusion_cli.cli.app import app

    assert app.pretty_exceptions_show_locals is False


# --- Dalga 4: REPL kapısı yalnız OpenRouter/NIM anahtarına bakmaz (L1-13) --------- #


def _anahtarsiz_ollama_kurulumu(monkeypatch):
    from dataclasses import replace

    from fusion_cli.config.keys import ProviderKeys
    from fusion_cli.config.loader import load_config

    gercek = load_config()
    yerel = replace(gercek.agent, model="ollama/qwen2.5-coder", fallback=())
    yapilandirma = replace(gercek, agent=yerel, web_sessions=())
    monkeypatch.setattr(app_module, "load_config", lambda: yapilandirma)
    monkeypatch.setattr(app_module, "detect", lambda: ProviderKeys(openrouter=False, nim=False))
    return yapilandirma


def test_anahtarsiz_varsayilan_kurulumda_repl_acilmaz(monkeypatch):
    from dataclasses import replace

    from fusion_cli.config.keys import ProviderKeys
    from fusion_cli.config.loader import load_config

    monkeypatch.setattr(app_module, "load_config", lambda: replace(load_config(), web_sessions=()))
    monkeypatch.setattr(app_module, "detect", lambda: ProviderKeys(openrouter=False, nim=False))

    assert runner.invoke(app_module.app, []).exit_code == 1


def test_yalniz_yerel_model_kullanan_repl_e_girebilir(monkeypatch):
    """Ölçüldü (30 Ekim): kapı `openrouter or nim` idi; yalnız Ollama kullanan çıkış 1 alıyordu."""
    _anahtarsiz_ollama_kurulumu(monkeypatch)
    cagrildi = []

    async def _sahte_repl(*args, **kwargs):
        cagrildi.append(1)
        return 0

    monkeypatch.setattr(app_module, "run_repl", _sahte_repl)
    monkeypatch.setattr(app_module, "open_memory", lambda *a, **k: None)

    sonuc = runner.invoke(app_module.app, [])

    assert cagrildi == [1]
    assert sonuc.exit_code == 0


def test_karsilama_terminal_degilse_kontrol_dizisi_yazmaz():
    """Boruya/dosyaya yönlendirilen çıktıya `ESC [ 3 J` bulaşmamalı (L1-39)."""
    import io

    from rich.console import Console

    from fusion_cli.ui import banner

    tampon = io.StringIO()
    console = Console(file=tampon, width=80, force_terminal=False)

    banner.print_welcome(console, banner.SessionInfo(**_ornek_oturum()), clear=True)

    assert "\x1b" not in tampon.getvalue()


# --- Dalga 4: agent çıkış kodu, kesilen koşuda temizlik, mcp-tools zaman aşımı (L1-26/28/46) --- #


def _agent_calistir(monkeypatch, sonuc):
    async def _sahte(*args, **kwargs):
        return sonuc

    monkeypatch.setattr(app_module, "run_agent_task", _sahte)
    return runner.invoke(app_module.app, ["agent", "gorev", "--no-memory", "--quiet"])


def test_agent_basarisiz_ama_metin_dolu_sonuc_sifirdan_farkli_doner(monkeypatch):
    from types import SimpleNamespace

    sonuc = SimpleNamespace(final_text="bütçe doldu, yarım kaldı", ok=False)

    assert _agent_calistir(monkeypatch, sonuc).exit_code == 1


def test_agent_basarili_sonuc_sifir_doner(monkeypatch):
    from types import SimpleNamespace

    assert _agent_calistir(monkeypatch, SimpleNamespace(final_text="tamam", ok=True)).exit_code == 0


def test_agent_hata_firlatinca_gosterge_ve_iz_kapatilir(monkeypatch):
    kapanis = []

    async def _patlat(*args, **kwargs):
        raise RuntimeError("motor çöktü")

    monkeypatch.setattr(app_module, "run_agent_task", _patlat)
    monkeypatch.setattr(
        app_module.ConsoleRenderer, "abort", lambda self: kapanis.append("abort"), raising=True
    )
    monkeypatch.setattr(
        app_module.Observers, "finish", lambda self: kapanis.append("finish"), raising=True
    )

    sonuc = runner.invoke(app_module.app, ["agent", "gorev", "--no-memory"])

    assert sonuc.exit_code != 0
    assert kapanis == ["abort", "finish"]


def test_mcp_tools_baglanamayan_sunucuda_zaman_asimi_fusion_hatasi_verir(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import pytest

    from fusion_cli.core.errors import FusionError

    class _Asili:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            await asyncio.sleep(30)

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr("fusion_cli.mcp_bridge.client.McpClient", _Asili)
    monkeypatch.setattr(
        app_module, "load_config", lambda: SimpleNamespace(mcp_servers=(SimpleNamespace(name="x"),))
    )
    monkeypatch.setattr(app_module, "MCP_TOOLS_TIMEOUT_S", 0.05)

    with pytest.raises(FusionError, match="bağlanılamadı"):
        app_module.mcp_tools()
