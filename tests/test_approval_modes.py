"""Claude'un izin kipleri: Otomatik, Manuel, Düzenlemeleri kabul et, Plan, İzinleri atla.

Kullanıcı (2 Ekim 2026): "modlarımız claude gibi çalışmıyor … otomatik modunda bile
bazen gereksiz yerlerde bana soru soruyor sormasın".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.tools import Tool, ToolEffect
from fusion_cli.engines.agent.approval import (
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
    parse_mode,
)
from fusion_cli.tools.auto_policy import auto_risk, is_read_only_command

from .fakes import AlwaysReject


def _arac(ad: str = "run_shell", effect: ToolEffect = ToolEffect.LOCAL) -> Tool:
    return Tool(name=ad, description="", parameters={}, run=lambda a, c: None, effect=effect)


async def _karar(mod: ApprovalMode, arac: Tool, args: dict, root: Path) -> Decision:
    politika = build_policy(mod, AlwaysReject())
    return await politika.decide(build_request(arac, args, root=root))


# --- Otomatik: sıradan iş sorulmaz ------------------------------------------ #


@pytest.mark.parametrize(
    "komut",
    [
        "php -l functions.php",
        "lsof -i :3000",
        "unzip theme.zip",
        "wget https://example.com/a.zip",
        'for f in *.png; do mv "$f" img/; done',
        "composer install",
        "docker compose up -d",
        "cp ~/Downloads/logo.png img/",
        "curl -X POST localhost:3000/api",
        "kill 1234",
        "rm -rf node_modules",
    ],
)
def test_otomatik_kip_siradan_isi_sormaz(tmp_path, komut):
    assert auto_risk(komut, tmp_path) is None


@pytest.mark.parametrize(
    ("komut", "neden"),
    [
        ("git push origin main", "git push"),
        ("sudo npm i", "sudo"),
        ("brew install php", "brew install"),
        ("npm i -g vercel", "global"),
        ("curl -d a=1 https://api.example.com", "veri gönderiyor"),
        ("ssh user@sunucu ls", "uzak sunucu"),
        ("rsync -av dist/ user@sunucu:/var/www", "uzak sunucu"),
        ("cp img/a.png ~/Desktop/", "proje dışındaki"),
        ("echo x > ~/.zshrc", "proje dışına yazıyor"),
        ("cd /baska/proje && npm test", "proje dışındaki bir klasörde"),
        ("mysql -e 'DROP DATABASE shop'", "veritabanını"),
        ("vercel --prod", "dağıtım"),
        ("./deploy.sh", "dağıtım"),
        ("npm run deploy", "yayınlıyor"),
        ("printenv", "ortam değişkenlerini"),
        ("killall Finder", "kapatıyor"),
        ("echo $(sudo whoami)", "sudo"),
        ("node -e \"require('fs').rmSync('x')\"", "satır içi kod"),
    ],
)
def test_otomatik_kip_yalniz_riskli_isi_sorar(tmp_path, komut, neden):
    assert neden in (auto_risk(komut, tmp_path) or "")


def test_salt_okuma_tespiti():
    assert is_read_only_command("git log --oneline | head -5")
    assert is_read_only_command("grep -rn foo src 2>/dev/null")
    assert not is_read_only_command("ls > liste.txt")
    assert not is_read_only_command("sed -i '' s/a/b/ x.txt")
    assert not is_read_only_command("npm install")


# --- Beş kip ------------------------------------------------------------------ #


@pytest.mark.parametrize(
    ("mod", "komut", "beklenen"),
    [
        (ApprovalMode.AUTO, "php -l a.php", Decision.ALLOW),
        (ApprovalMode.AUTO, "unzip a.zip", Decision.ALLOW),
        (ApprovalMode.AUTO, "git push", Decision.DENIED),
        (ApprovalMode.ACCEPT_EDITS, "unzip a.zip", Decision.DENIED),
        (ApprovalMode.ACCEPT_EDITS, "pytest -q", Decision.ALLOW),
        (ApprovalMode.SECURITY, "git status", Decision.ALLOW),
        (ApprovalMode.SECURITY, "pytest -q", Decision.DENIED),
        (ApprovalMode.PLAN, "git log", Decision.ALLOW),
        (ApprovalMode.PLAN, "npm install", Decision.BLOCKED),
        (ApprovalMode.BYPASS, "git push", Decision.ALLOW),
        (ApprovalMode.BYPASS, "git reset --hard", Decision.ALLOW),
    ],
)
async def test_kabuk_komutu_kiplere_gore(tmp_path, mod, komut, beklenen):
    assert await _karar(mod, _arac(), {"command": komut}, tmp_path) is beklenen


@pytest.mark.parametrize(
    ("mod", "beklenen"),
    [
        (ApprovalMode.AUTO, Decision.ALLOW),
        (ApprovalMode.ACCEPT_EDITS, Decision.ALLOW),
        (ApprovalMode.SECURITY, Decision.DENIED),
        (ApprovalMode.PLAN, Decision.BLOCKED),
        (ApprovalMode.BYPASS, Decision.ALLOW),
    ],
)
async def test_dosya_duzenleme_kiplere_gore(tmp_path, mod, beklenen):
    arac = _arac("write_file")
    assert await _karar(mod, arac, {"path": "a.txt"}, tmp_path) is beklenen


@pytest.mark.parametrize(
    ("mod", "etki", "beklenen"),
    [
        (ApprovalMode.AUTO, ToolEffect.REMOTE_INTERACT, Decision.ALLOW),
        (ApprovalMode.AUTO, ToolEffect.REMOTE_WRITE, Decision.DENIED),
        (ApprovalMode.SECURITY, ToolEffect.REMOTE_READ, Decision.ALLOW),
        (ApprovalMode.SECURITY, ToolEffect.REMOTE_INTERACT, Decision.DENIED),
        (ApprovalMode.PLAN, ToolEffect.REMOTE_READ, Decision.ALLOW),
        (ApprovalMode.PLAN, ToolEffect.REMOTE_INTERACT, Decision.BLOCKED),
    ],
)
async def test_tarayici_ve_uzak_araclar_kiplere_gore(tmp_path, mod, etki, beklenen):
    arac = _arac("chrome_click", effect=etki)
    assert await _karar(mod, arac, {"ref": "e1"}, tmp_path) is beklenen


async def test_yikici_komut_otomatik_ve_duzenleme_kipinde_yine_sorulur(tmp_path):
    for mod in (ApprovalMode.AUTO, ApprovalMode.ACCEPT_EDITS):
        karar = await _karar(mod, _arac(), {"command": "git reset --hard"}, tmp_path)
        assert karar is Decision.DENIED


def test_kip_adlari_ve_takma_adlar():
    assert parse_mode("Manual") is ApprovalMode.SECURITY
    assert parse_mode("edits") is ApprovalMode.ACCEPT_EDITS
    assert parse_mode("bypass") is ApprovalMode.BYPASS
    with pytest.raises(ValueError):
        parse_mode("hepsi")
