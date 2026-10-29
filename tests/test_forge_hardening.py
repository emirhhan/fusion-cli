"""Üretilen araç: yasak liste ADLA değil NİTELİKLİ kullanıma bakar (T1-09, T1-10).

T1-10 ölçüldü (29 Ekim): `"a-b".replace("-", " ")`, `lst.remove(x)`, `re.compile(...)`
çağrı ADI yüzünden reddediliyordu; metin dönüştüren araçların çoğu düşüyordu.
T1-09: `socket`, `urllib`, `importlib.import_module("subprocess")`, `os.execl`, `os.environ`
ve `().__class__.__bases__[0].__subclasses__()` zinciri engellenmiyordu; araç kendi
`open()` çağrılarında kök denetiminden de geçmiyordu.

Bu bir kum havuzu DEĞİLDİR (AST denetimi süreç içi `exec`'tir); gerçek yalıtım yoktur.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools.forge import forge_tool, load_forged_tools


def _forge(tmp_path, kaynak: str, ad: str = "deneme"):
    return forge_tool({"name": ad, "source": kaynak}, ToolContext(root=tmp_path))


@pytest.mark.parametrize(
    "govde",
    [
        "return 'a-b'.replace('-', ' ')",
        "x = [1, 2, 3]\n    x.remove(2)\n    return str(x)",
        "import re\n    return str(re.compile(r'\\d+').findall('a1b22'))",
        "return args['metin'].replace('a', 'b')",
        "import json\n    return json.dumps({'a': 1})",
        "from pathlib import Path\n    return Path('a/b.txt').name",
        "d = {'a': 1}\n    d.pop('a')\n    return str(d)",
        "import os\n    return os.path.join('a', 'b')",
        "import re\n    return re.sub(r'x', 'y', args['m'])",
        "return str(len(args))",
    ],
)
def test_zararsiz_metot_adlari_reddedilmez(tmp_path, govde):
    sonuc = _forge(tmp_path, f"def run(args):\n    {govde}\n")

    assert sonuc.ok, sonuc.output


@pytest.mark.parametrize(
    "govde",
    [
        "import os\n    os.remove('x')",
        "import os\n    os.replace('a', 'b')",
        "import os\n    os.rename('a', 'b')",
        "from os import remove\n    remove('x')",
        "import os as o\n    o.unlink('x')",
        "from pathlib import Path\n    Path('x').unlink()",
        "from pathlib import Path\n    Path('x').rename('y')",
        "from pathlib import Path\n    Path('x').replace('y')",
        "from pathlib import Path\n    Path('x').rmdir()",
        "import os\n    os.system('ls')",
        "import os\n    os.popen('ls')",
        "import os\n    os.execl('/bin/sh', 'sh')",
        "import os\n    os.execvpe('sh', ['sh'], {})",
        "import os\n    os.spawnlp(os.P_WAIT, 'ls', 'ls')",
        "import os\n    os.posix_spawn('/bin/ls', ['ls'], {})",
        "import os\n    os.fork()",
        "import os\n    os.startfile('x')",
        "import os\n    os.truncate('x', 0)",
        "import os\n    os.kill(1, 9)",
        "import socket\n    socket.create_connection(('x', 80))",
        "import urllib.request\n    urllib.request.urlopen('http://x')",
        "from urllib.request import urlopen\n    urlopen('http://x')",
        "import http.client",
        "import requests",
        "import importlib\n    importlib.import_module('subprocess')",
        "import runpy",
        "import pickle",
        "import os\n    return str(os.environ)",
        "import os\n    return os.environ['API_KEY']",
        "import os\n    return os.getenv('API_KEY')",
        "from os import environ\n    return str(environ)",
        "return str(().__class__.__bases__[0].__subclasses__())",
        "return str(run.__globals__)",
        "return str(__builtins__)",
        "import sys\n    return str(sys.modules)",
        "eval('1')",
        "exec('x=1')",
        "compile('1', 'x', 'eval')",
        "getattr(object, 'x')",
        "__import__('os')",
    ],
)
def test_nitelikli_tehlikeli_kullanim_reddedilir(tmp_path, govde):
    sonuc = _forge(tmp_path, f"def run(args):\n    {govde}\n")

    assert not sonuc.ok, govde
    assert not (tmp_path / ".fusion" / "tools" / "deneme.py").exists()


def test_aracin_kendi_open_cagrisi_kok_denetiminden_gecer(tmp_path):
    """`path`/`yol` adı taşımayan argümanla yapılan open() de kök dışına yazamaz."""
    kaynak = (
        "def run(args):\n"
        "    with open(args['hedef'], 'w') as f:\n"
        "        f.write('sizinti')\n"
        "    return 'yazdim'\n"
    )
    context = ToolContext(root=tmp_path)
    assert _forge(tmp_path, kaynak, "yaz").ok
    arac = load_forged_tools(tmp_path)[0]
    disari = tmp_path.parent / "disari-open.txt"

    sonuc = arac.run({"hedef": str(disari)}, context)

    assert not sonuc.ok
    assert not disari.exists()


def test_aracin_open_cagrisi_kok_icinde_calisir(tmp_path):
    kaynak = (
        "def run(args):\n"
        "    with open('cikti.txt', 'w') as f:\n"
        "        f.write('merhaba')\n"
        "    with open('cikti.txt') as f:\n"
        "        return f.read()\n"
    )
    context = ToolContext(root=tmp_path)
    assert _forge(tmp_path, kaynak, "yaz").ok
    arac = load_forged_tools(tmp_path)[0]

    sonuc = arac.run({}, context)

    assert sonuc.ok and sonuc.output == "merhaba"
    assert (tmp_path / "cikti.txt").read_text(encoding="utf-8") == "merhaba"


def test_aracin_open_cagrisi_gizli_dosyayi_okuyamaz(tmp_path):
    kaynak = "def run(args):\n    return open(args['hedef']).read()\n"
    context = ToolContext(root=tmp_path)
    assert _forge(tmp_path, kaynak, "oku").ok
    arac = load_forged_tools(tmp_path)[0]
    disari = tmp_path.parent / "gizli-open.txt"
    disari.write_text("parola", encoding="utf-8")

    sonuc = arac.run({"hedef": str(disari)}, context)

    assert not sonuc.ok
    assert "parola" not in sonuc.output
