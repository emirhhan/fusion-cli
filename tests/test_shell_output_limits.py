"""Claude Code Bash çıktı sınırları (#357, tools-reference "Output limits").

Geçerli sonuç ~30.000 karaktere kadar satır içi; aşınca oturum dizinindeki dosyanın yolu +
ilk 2.000 karakter önizleme. Hatalı sonuç ~10.000 karaktere kadar; aşınca o boyda baş+son
kesit, dosya yolu yok. `BASH_MAX_OUTPUT_LENGTH` geri okuma penceresi (tavan 150.000);
`bashOutputMaxChars` (≤128.000) satır içi sınırı ve pencereyi birlikte ayarlar.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.core.artifacts import ArtifactStore
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import shell
from fusion_cli.tools.shell_output import is_benign_exit, output_limits, shape_output


def _ctx(tmp_path):
    return ToolContext(
        root=tmp_path / "proje", artifacts=ArtifactStore(tmp_path / "art"), shell_fingerprint=False
    )


def test_gecerli_uzun_cikti_dosya_yolu_ve_2000_onizleme(tmp_path):
    (tmp_path / "proje").mkdir()
    context = _ctx(tmp_path)
    sonuc = shell.run_shell({"command": "python3 -c \"print('a'*40000)\""}, context)
    assert sonuc.ok
    assert sonuc.artifact_path, sonuc.output[:300]
    assert len(sonuc.output) < 3_000
    tam = Path(sonuc.artifact_path).read_text(encoding="utf-8")
    assert tam.count("a") >= 40_000


def test_gecerli_25000_karakter_satir_icinde_kalir(tmp_path):
    (tmp_path / "proje").mkdir()
    context = _ctx(tmp_path)
    sonuc = shell.run_shell({"command": "python3 -c \"print('b'*25000)\""}, context)
    assert sonuc.ok and not sonuc.artifact_path
    assert sonuc.output.count("b") == 25_000


def test_hatali_uzun_cikti_bas_son_kesit_yolsuz(tmp_path):
    (tmp_path / "proje").mkdir()
    context = _ctx(tmp_path)
    komut = "python3 -c \"print('BAS'+'x'*40000+'SON')\"; exit 2"
    sonuc = shell.run_shell({"command": komut}, context)
    assert not sonuc.ok and not sonuc.artifact_path
    assert "BAS" in sonuc.output and "SON" in sonuc.output
    assert len(sonuc.output) < 11_000


def test_grep_cikis_1_gecerli_sayilir():
    assert is_benign_exit("grep foo x.txt", 1)
    assert is_benign_exit("git diff --stat", 1)
    assert is_benign_exit("[ -f a ]", 1)
    assert not is_benign_exit("pgrep foo", 1)
    assert not is_benign_exit("grep foo x.txt", 2)


def test_sinirlar_ortamdan_ve_ayardan(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "ev" / ".claude"))
    monkeypatch.delenv("BASH_MAX_OUTPUT_LENGTH", raising=False)
    assert output_limits(tmp_path) == (30_000, 30_000)
    monkeypatch.setenv("BASH_MAX_OUTPUT_LENGTH", "999999")
    assert output_limits(tmp_path) == (30_000, 150_000)
    ayar = tmp_path / "ev" / ".claude" / "settings.json"
    ayar.parent.mkdir(parents=True)
    ayar.write_text(json.dumps({"bashOutputMaxChars": 50_000}), encoding="utf-8")
    assert output_limits(tmp_path) == (50_000, 50_000)
    ayar.write_text(json.dumps({"bashOutputMaxChars": 900_000}), encoding="utf-8")
    assert output_limits(tmp_path) == (128_000, 128_000)


@pytest.mark.parametrize("gecerli", [True, False])
def test_depo_yoksa_kirpilir_ve_soylenir(gecerli):
    metin, yol = shape_output("z" * 50_000, valid=gecerli, inline=30_000, window=30_000, store=None)
    assert (yol is None and "KIRPILDI" in metin) or "atıldı" in metin
    assert len(metin) < 31_000


@pytest.mark.parametrize(
    ("komut", "beklenen"),
    [
        ("cat f | grep x", True),
        ("cd src && grep x f", True),
        ("FOO=1 grep x f", True),
        ("git -C . diff --exit-code", True),
        ("git --no-pager diff", True),
        ("grep x f | wc -l", False),
        ("git -C . push", False),
    ],
)
def test_cikis_kodu_bir_son_komuta_gore_degerlendirilir(komut, beklenen):
    """Boru ve zincirde çıkış kodu son komutundur (bağımsız inceleme #7)."""
    from fusion_cli.tools.shell_output import is_benign_exit

    assert is_benign_exit(komut, 1) is beklenen
