"""Geri alınabilir silme: Fusion hiçbir klasörü kalıcı silmez, korumalı yerlere dokunmaz.

Olay (1 Ekim 2026): "bu projeyi sil" isteğinde `~/Desktop/01-Projeler` altındaki
projelerin çoğu silindi. Bu testler o olayı ve benzerlerini canlandırır.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolContext
from fusion_cli.observability.audit import AuditSink
from fusion_cli.tools import forge, shell
from fusion_cli.tools.safe_delete import (
    DeleteRefusedError,
    is_complex_recursive_delete,
    list_trash,
    move_to_trash,
    protected_reason,
    restore,
    simple_rm_targets,
)


@pytest.fixture
def ev(tmp_path, monkeypatch) -> Path:
    """Sahte ev dizini: Desktop/01-Projeler/projeler altında birkaç proje."""
    home = tmp_path / "ev"
    projeler = home / "Desktop" / "01-Projeler" / "projeler"
    for ad in ("GATE HOLDING", "pizza-orbit", "sneaksup-wp"):
        (projeler / ad / ".git").mkdir(parents=True)
        (projeler / ad / "index.php").write_text("<?php", encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(shell, "trash_dir", lambda: tmp_path / "cop")
    return home


def _proje(ev: Path, ad: str = "sneaksup-wp") -> Path:
    return ev / "Desktop" / "01-Projeler" / "projeler" / ad


@pytest.mark.parametrize(
    ("komut", "beklenen"),
    [
        ("rm -rf build", ("build",)),
        ("rm -r -f 'GATE HOLDING' dist", ("GATE HOLDING", "dist")),
        ("rm -- -garip", ("-garip",)),
        ("rm -rf build && ls", None),
        ("rm -rf *", None),
        ("rm -rf $HOME/x", None),
        ("rm --no-preserve-root /", None),
        ("echo rm -rf x", None),
    ],
)
def test_sade_rm_ayrisimi(komut, beklenen):
    assert simple_rm_targets(komut) == beklenen


@pytest.mark.parametrize(
    "komut",
    ["cd .. && rm -rf projeler", "find . -name x -delete", "ls | xargs rm -rf", "git clean -fdx"],
)
def test_karmasik_ozyinelemeli_silme_taninir(komut):
    assert is_complex_recursive_delete(komut)


def test_olay_proje_kokunden_ust_klasor_silinemez(ev):
    kok = _proje(ev)

    sonuc = shell.run_shell({"command": "rm -rf .."}, ToolContext(root=kok))

    assert not sonuc.ok and "SİLME REDDEDİLDİ" in sonuc.output
    assert (_proje(ev, "GATE HOLDING") / "index.php").exists()


def test_olay_cok_projeli_klasor_mutlak_yolla_da_silinemez(ev):
    # Fusion bambaşka bir klasörde açıkken bile proje deposu silinemez.
    kok = ev / "baska-calisma"
    kok.mkdir()
    hedef = ev / "Desktop" / "01-Projeler"

    sonuc = shell.run_shell({"command": f"rm -rf '{hedef}'"}, ToolContext(root=kok))

    assert not sonuc.ok and "birden çok proje" in sonuc.output
    assert (_proje(ev, "pizza-orbit") / "index.php").exists()


def test_karmasik_silme_komutu_hic_calismaz(ev):
    kok = _proje(ev)

    sonuc = shell.run_shell({"command": "cd ../.. && rm -rf projeler"}, ToolContext(root=kok))

    assert not sonuc.ok and "sade biçimde" in sonuc.output
    assert _proje(ev, "GATE HOLDING").exists()


def test_proje_silme_kalici_degil_cope_tasinir_ve_geri_alinir(ev, tmp_path):
    projeler = _proje(ev).parent

    sonuc = shell.run_shell({"command": "rm -rf sneaksup-wp"}, ToolContext(root=projeler))

    assert sonuc.ok and "Fusion çöpüne taşındı" in sonuc.output
    assert not _proje(ev).exists()
    assert _proje(ev, "GATE HOLDING").exists()
    girdiler = list_trash(tmp_path / "cop")
    assert [girdi.original.name for girdi in girdiler] == ["sneaksup-wp"]

    restore(tmp_path / "cop", girdiler[0].id)

    assert (_proje(ev) / "index.php").read_text(encoding="utf-8") == "<?php"
    assert list_trash(tmp_path / "cop") == []


@pytest.mark.parametrize("hedef", ["", "Desktop", "Documents", ".ssh"])
def test_ev_ve_standart_klasorler_korunur(ev, hedef):
    assert protected_reason(ev / hedef, ev / "baska", ev) is not None


def test_korumali_hedef_varsa_hicbiri_tasinmaz(ev, tmp_path):
    kok = _proje(ev)
    (kok / "gecici.txt").write_text("x", encoding="utf-8")

    with pytest.raises(DeleteRefusedError):
        move_to_trash(("gecici.txt", ".."), cwd=kok, root=kok, home=ev, trash_root=tmp_path / "cop")

    assert (kok / "gecici.txt").exists()


def test_geri_alma_dolu_yeri_ezmez(ev, tmp_path):
    kok = _proje(ev)
    (kok / "a.txt").write_text("eski", encoding="utf-8")
    girdi = move_to_trash(("a.txt",), cwd=kok, root=kok, home=ev, trash_root=tmp_path / "cop")[0][0]
    (kok / "a.txt").write_text("yeni", encoding="utf-8")

    with pytest.raises(DeleteRefusedError, match="ezilmedi"):
        restore(tmp_path / "cop", girdi.id)

    assert (kok / "a.txt").read_text(encoding="utf-8") == "yeni"


@pytest.mark.parametrize(
    "kaynak",
    [
        "import shutil\ndef run(args):\n    shutil.rmtree(args['path'])\n",
        "import os\ndef run(args):\n    os.remove('x')\n",
        "from pathlib import Path\ndef run(args):\n    Path('x').unlink()\n",
        "def run(args):\n    __import__('os').system('rm -rf ~')\n",
        "import subprocess\ndef run(args):\n    subprocess.run(['ls'])\n",
    ],
)
def test_uretilen_arac_silme_ve_komut_calistiramaz(tmp_path, kaynak):
    sonuc = forge.forge_tool({"name": "temizle", "source": kaynak}, ToolContext(root=tmp_path))

    assert not sonuc.ok and "run_shell" in sonuc.output
    assert not (tmp_path / forge.FORGE_DIR / "temizle.py").exists()


def test_zararsiz_uretilen_arac_kabul_edilir(tmp_path):
    kaynak = "def run(args):\n    return str(len(args.get('metin', '')))\n"

    sonuc = forge.forge_tool({"name": "say", "source": kaynak}, ToolContext(root=tmp_path))

    assert sonuc.ok


def test_denetim_gunlugu_her_arac_sonucunu_ekler_ve_sirri_maskeler(tmp_path):
    sink = AuditSink(tmp_path / "audit", "sohbet/1", root=tmp_path)
    sir = "sk-or-v1-" + "b" * 48

    sink.handle(
        ToolExecuted(
            name="run_shell",
            args={"command": f"OPENROUTER_API_KEY={sir} rm -rf x"},
            outcome=ToolOutcome.OK,
            output="tamam",
            agent_id="kodcu-1",
        )
    )
    sink.handle(
        ToolExecuted(name="read_file", args={"path": "a"}, outcome=ToolOutcome.OK, output="")
    )

    satirlar = sink.path.read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 2
    ilk = json.loads(satirlar[0])
    assert ilk["arac"] == "run_shell" and ilk["ajan"] == "kodcu-1"
    assert "rm -rf x" in ilk["argumanlar"]
    assert sir not in satirlar[0]
