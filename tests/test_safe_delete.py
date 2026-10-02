"""Geri alınabilir silme: Fusion hiçbir klasörü kalıcı silmez.

Olay (1 Ekim 2026): "bu projeyi sil" isteğinde `~/Desktop/01-Projeler` altındaki
projelerin çoğu silindi. Kullanıcı (2 Ekim): "gerçekten bir şey silmek istersem
silemeyecek miyim" — bu yüzden sade silme reddedilmez, çöpe gider; yalnız kök ve ev
dizininin kendisi silinemez. Dikkat gerektiren yerler onay kartında söylenir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolContext
from fusion_cli.observability.audit import AuditSink
from fusion_cli.tools import forge, shell
from fusion_cli.tools.delete_preview import delete_caution, describe_delete
from fusion_cli.tools.safe_delete import (
    DeleteRefusedError,
    caution_reason,
    forbidden_reason,
    is_complex_recursive_delete,
    list_trash,
    move_to_trash,
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
        ("rm -rf *", ("*",)),
        ("rm -rf */build", None),
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


def test_ust_klasor_silinebilir_ama_kartta_dikkat_der_ve_cope_gider(ev, tmp_path):
    """Kullanıcı silmek isterse siler; ama kart bunun ne olduğunu açıkça söyler."""
    kok = _proje(ev)

    assert "ÜST klasörü" in (delete_caution("rm -rf ..", kok, ev) or "")
    sonuc = shell.run_shell({"command": "rm -rf .."}, ToolContext(root=kok))

    assert sonuc.ok and "Fusion çöpüne taşındı" in sonuc.output
    girdi = list_trash(tmp_path / "cop")[0]
    restore(tmp_path / "cop", girdi.id)
    assert (_proje(ev, "GATE HOLDING") / "index.php").exists()


def test_cok_projeli_klasor_silinirse_kart_uyarir_ve_geri_alinabilir(ev, tmp_path):
    kok = ev / "baska-calisma"
    kok.mkdir()
    hedef = ev / "Desktop" / "01-Projeler"

    assert "DIŞINDA" in (delete_caution(f"rm -rf '{hedef}'", kok, ev) or "")
    sonuc = shell.run_shell({"command": f"rm -rf '{hedef}'"}, ToolContext(root=kok))

    assert sonuc.ok and not hedef.exists()
    restore(tmp_path / "cop", list_trash(tmp_path / "cop")[0].id)
    assert (_proje(ev, "pizza-orbit") / "index.php").exists()


def test_jokerli_silme_her_ogeyi_cope_tasir_gizlileri_birakir(ev, tmp_path):
    kok = _proje(ev)
    (kok / "a.txt").write_text("a", encoding="utf-8")

    sonuc = shell.run_shell({"command": "rm -rf ./*"}, ToolContext(root=kok))

    assert sonuc.ok
    assert sorted(g.original.name for g in list_trash(tmp_path / "cop")) == ["a.txt", "index.php"]
    assert (kok / ".git").exists()


def test_karmasik_silme_reddedilmez_kart_kalici_oldugunu_soyler(ev):
    kok = _proje(ev)

    metin = describe_delete("find . -name '*.log' -delete", kok, ev)

    assert "KALICI" in metin


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


def test_yalniz_kok_ve_ev_dizini_yasak(ev):
    assert forbidden_reason(ev, ev) is not None
    assert forbidden_reason(Path("/"), ev) is not None
    assert forbidden_reason(ev / "Desktop", ev) is None


@pytest.mark.parametrize("hedef", ["Desktop", "Documents", ".ssh"])
def test_standart_klasorler_dikkat_ister(ev, hedef):
    assert caution_reason(ev / hedef, ev / "baska", ev) is not None


def test_yasak_hedef_varsa_hicbiri_tasinmaz(ev, tmp_path):
    kok = _proje(ev)
    (kok / "gecici.txt").write_text("x", encoding="utf-8")

    with pytest.raises(DeleteRefusedError):
        move_to_trash(
            ("gecici.txt", str(ev)), cwd=kok, root=kok, home=ev, trash_root=tmp_path / "cop"
        )

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
