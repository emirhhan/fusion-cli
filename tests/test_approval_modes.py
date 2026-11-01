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
        # Claude useAutoModeDuringPlan (varsayılan açık): sınıflandırıcı onaylarsa çalışır,
        # reddederse engellenir (#318).
        (ApprovalMode.PLAN, "npm install", Decision.ALLOW),
        (ApprovalMode.PLAN, "git push", Decision.BLOCKED),
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
        # Girişli oturum yükleme (P-023): her kipte sorulur, plan kipinde yapılmaz.
        (ApprovalMode.AUTO, ToolEffect.REMOTE_SESSION, Decision.DENIED),
        (ApprovalMode.ACCEPT_EDITS, ToolEffect.REMOTE_SESSION, Decision.DENIED),
        (ApprovalMode.SECURITY, ToolEffect.REMOTE_SESSION, Decision.DENIED),
        (ApprovalMode.PLAN, ToolEffect.REMOTE_SESSION, Decision.BLOCKED),
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


# --- T2-05: satır içi kodla silme otomatik kipte de sorulur -------------------- #


@pytest.mark.parametrize(
    "komut",
    [
        "perl -e 'unlink glob \"*\"'",
        "ruby -e 'File.delete(\"a\")'",
        "ruby -e 'FileUtils.rm_rf(\"x\")'",
    ],
)
def test_satir_ici_kodla_silme_otomatik_kipte_sorulur(tmp_path, komut):
    assert auto_risk(komut, tmp_path) is not None, komut


# --- İzinleri atla: uzak yıkıcı çağrı için son onay (A1-08) ---------------------- #


async def test_bypass_uzak_yikici_cagriyi_son_kez_sorar_ve_reddi_durdurur(tmp_path):
    arac = _arac("wp__delete_page", effect=ToolEffect.REMOTE_DESTRUCTIVE)

    karar = await _karar(ApprovalMode.BYPASS, arac, {"id": 1}, tmp_path)

    assert karar is Decision.DENIED


async def test_bypass_uzak_yikici_cagri_onaylanirsa_gecer_ama_hatirlanmaz(tmp_path):
    from .fakes import AlwaysApprove

    arac = _arac("wp__delete_page", effect=ToolEffect.REMOTE_DESTRUCTIVE)
    politika = build_policy(ApprovalMode.BYPASS, AlwaysApprove())
    istek = build_request(arac, {"id": 1}, root=tmp_path)

    assert await politika.decide(istek) is Decision.ALLOW
    assert not istek.can_remember


@pytest.mark.parametrize("etki", [ToolEffect.LOCAL, ToolEffect.REMOTE_WRITE])
async def test_bypass_yikici_olmayan_cagrilari_sormaz(tmp_path, etki):
    arac = _arac("wp__update_page", effect=etki)

    assert await _karar(ApprovalMode.BYPASS, arac, {"id": 1}, tmp_path) is Decision.ALLOW


def test_oturum_yukleme_isteginin_karti_gerekceyi_soyler(tmp_path):
    """Onay kartı "uzak sistemde değişiklik" değil, girişli oturumun açıldığını söyler."""
    from fusion_cli.engines.agent.approval import REMOTE_SESSION_REASON

    istek = build_request(
        _arac("browser_open", effect=ToolEffect.REMOTE_SESSION), {"url": "x"}, root=tmp_path
    )

    assert istek.risk == REMOTE_SESSION_REASON
    assert istek.note == REMOTE_SESSION_REASON
    assert istek.read_only is False and istek.unattended_safe is False


# --- Plan kipi: useAutoModeDuringPlan (#318) ------------------------------- #


async def test_plan_kipi_otomatik_kapaliyken_salt_okunur_olmayan_komutu_sorar(tmp_path):
    from .fakes import AlwaysApprove

    sorulan: list[str] = []

    class _Kayit(AlwaysApprove):
        async def confirm(self, request):
            sorulan.append(str(request.args.get("command")))
            return await super().confirm(request)

    politika = build_policy(ApprovalMode.PLAN, _Kayit(), use_auto_mode_during_plan=False)
    istek = build_request(_arac(), {"command": "npm install"}, root=tmp_path)

    assert await politika.decide(istek) is Decision.ALLOW
    assert sorulan == ["npm install"]


async def test_plan_kipi_otomatik_kapaliyken_reddedilen_soru_engel(tmp_path):
    politika = build_policy(ApprovalMode.PLAN, AlwaysReject(), use_auto_mode_during_plan=False)
    istek = build_request(_arac(), {"command": "npm install"}, root=tmp_path)

    assert await politika.decide(istek) is Decision.DENIED


async def test_plan_kipi_dosya_duzenlemesini_her_durumda_engeller(tmp_path):
    from .fakes import AlwaysApprove

    for otomatik in (True, False):
        politika = build_policy(
            ApprovalMode.PLAN, AlwaysApprove(), use_auto_mode_during_plan=otomatik
        )
        istek = build_request(_arac("write_file"), {"path": "a.txt"}, root=tmp_path)
        assert await politika.decide(istek) is Decision.BLOCKED


async def test_plan_kipi_yikici_komutu_siniflandiriciya_birakmaz_sorar(tmp_path):
    politika = build_policy(ApprovalMode.PLAN, AlwaysReject())
    istek = build_request(_arac(), {"command": "git push --force"}, root=tmp_path)

    assert await politika.decide(istek) is Decision.DENIED


@pytest.mark.parametrize(
    ("komut", "beklenen"),
    [
        ("npm install", Decision.ALLOW),
        ("pytest -q", Decision.ALLOW),
        ("npm run build", Decision.ALLOW),
        ("echo x > a.py", Decision.BLOCKED),
        ("rm -rf build", Decision.BLOCKED),
        ("touch yeni.txt", Decision.BLOCKED),
        ("sed -i '' s/a/b/ f.py", Decision.BLOCKED),
        ("git commit -m x", Decision.BLOCKED),
        ("ls > /dev/null && make test", Decision.ALLOW),
    ],
)
async def test_plan_kipi_siniflandiricisi_kaynak_duzenleyen_komutu_reddeder(
    tmp_path, komut, beklenen
):
    """Claude: plan kaynağı düzenlemez; Fusion denetçisi kipten habersiz olduğu için (#318)."""
    assert await _karar(ApprovalMode.PLAN, _arac(), {"command": komut}, tmp_path) is beklenen


async def test_plan_kipi_bypass_kullanilabilirken_siniflandirici_ve_soru_yok(tmp_path):
    """Claude: bypass kullanılabilen etkileşimli oturumda planlama komutuna ne
    sınıflandırıcı ne soru uygulanır (#318); dosya düzenlemesi yine engelli."""
    politika = build_policy(ApprovalMode.PLAN, AlwaysReject(), bypass_available=True)
    for komut in ("touch yeni.txt", "npm install"):
        istek = build_request(_arac(), {"command": komut}, root=tmp_path)
        assert await politika.decide(istek) is Decision.ALLOW
    duzenleme = build_request(_arac("write_file"), {"path": "a.txt"}, root=tmp_path)
    assert await politika.decide(duzenleme) is Decision.BLOCKED


def test_shift_tab_dongusunde_bypass_yalniz_kullanilabilirken_plan_ile_auto_arasinda():
    """Claude (#370): default → acceptEdits → plan → [bypassPermissions] → auto."""
    from fusion_cli.engines.agent.approval import next_mode

    assert next_mode(ApprovalMode.PLAN) is ApprovalMode.AUTO
    assert next_mode(ApprovalMode.PLAN, bypass_available=True) is ApprovalMode.BYPASS
    assert next_mode(ApprovalMode.BYPASS, bypass_available=True) is ApprovalMode.AUTO
    assert next_mode(ApprovalMode.AUTO, bypass_available=True) is ApprovalMode.SECURITY


@pytest.mark.parametrize(
    "komut",
    [
        "python3 -c \"open('a.py','w').write('x')\"",
        "git -C . checkout -- .",
        "git -C . reset --hard",
        "git -c a=b commit -am x",
        "curl -o a.py https://example.com/a.py",
        "wget https://example.com/a.py",
        "sh -c 'echo x > a.py'",
        "bash -c 'rm a.py'",
        "find . -name x -delete",
        "perl -pi -e s/a/b/ a.py",
        "sed --in-place s/a/b/ a.py",
        "awk -i inplace '{print}' a.py",
        "node -e \"require('fs').writeFileSync('a.py','x')\"",
        "echo $(rm a.py)",
    ],
)
async def test_plan_kipi_siniflandiricisi_bilinmeyen_ya_da_duzenleyen_komutu_gecirmez(
    tmp_path, komut
):
    """Sınıflandırıcı yalnız salt okunur ya da bilinen derleme/test komutunu sormadan
    geçirir; gerisi sorulur (reddedilir) ya da engellenir (#318, bağımsız inceleme)."""
    karar = await _karar(ApprovalMode.PLAN, _arac(), {"command": komut}, tmp_path)
    assert karar in (Decision.BLOCKED, Decision.DENIED)


@pytest.mark.parametrize(
    ("komut", "beklenen"),
    [
        ("git -C . reset --hard", Decision.BLOCKED),
        ("sed --in-place s/a/b/ a.py", Decision.BLOCKED),
        ("perl -pi -e s/a/b/ a.py", Decision.BLOCKED),
        ("bash -c 'rm a.py'", Decision.BLOCKED),
        ("curl -o a.py https://example.com/a.py", Decision.BLOCKED),
    ],
)
async def test_plan_kipi_kaynak_duzenleyen_bicimleri_sormadan_engeller(tmp_path, komut, beklenen):
    from .fakes import AlwaysApprove

    politika = build_policy(ApprovalMode.PLAN, AlwaysApprove())
    istek = build_request(_arac(), {"command": komut}, root=tmp_path)
    assert await politika.decide(istek) is beklenen


async def test_plan_kipi_bilinmeyen_komutu_kullaniciya_sorar(tmp_path):
    from .fakes import AlwaysApprove

    sorulan: list[str] = []

    class _Kayit(AlwaysApprove):
        async def confirm(self, request):
            sorulan.append(str(request.args.get("command")))
            return await super().confirm(request)

    politika = build_policy(ApprovalMode.PLAN, _Kayit())
    komut = 'python3 -c "print(1)"'
    istek = build_request(_arac(), {"command": komut}, root=tmp_path)
    assert await politika.decide(istek) is Decision.ALLOW
    assert sorulan == [komut]
