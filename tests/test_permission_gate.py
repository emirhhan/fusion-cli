"""İzin kuralları onay akışında (P-001/P-002/P-003/P-013).

Karar sırası: deny (her kipte, bypass dahil) → yıkıcı → ask → allow → kip → hafıza → soru.
Korumalı proje yolları (`.git/`, `.claude/`) yıkıcı sayılır; kök-dışı engel açıkken
sorulmadan kapatılır; "bir daha sorma" kalıcı kural yazar; ret notu modele gider ve
tur SÜRER.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config import trust
from fusion_cli.config.permission_rules import (
    PermissionDecision,
    PermissionRuleSet,
    parse_rule,
    user_permissions_file,
)
from fusion_cli.core.tools import Tool, ToolContext, ToolEffect
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMemory,
    ApprovalMode,
    ApprovalReply,
    Decision,
    Denial,
    build_policy,
    build_request,
)
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.agent.permission_persist import (
    persist_target,
    remember_always,
    rule_for_request,
)
from fusion_cli.tools.files import resolve_path, writable_path
from fusion_cli.tools.protected_paths import protected_path_reason

from .fakes import RecordingSink, ScriptedProvider, make_config, model_result, tool_call


@pytest.fixture(autouse=True)
def _izole_ev(tmp_path, monkeypatch):
    ev = tmp_path / "ev"
    ev.mkdir()
    monkeypatch.setenv("HOME", str(ev))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ev / ".config"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ev))
    monkeypatch.setattr(trust, "trust_store_file", lambda: ev / "guven.json")
    return ev


def _arac(ad: str = "run_shell", effect: ToolEffect = ToolEffect.LOCAL) -> Tool:
    return Tool(name=ad, description="", parameters={}, run=lambda a, c: None, effect=effect)


def _kurallar(*ciftler: tuple[str, str], **engeller: bool) -> PermissionRuleSet:
    return PermissionRuleSet(
        rules=tuple(parse_rule(m, PermissionDecision(k), source="test") for m, k in ciftler),
        **engeller,
    )


class _Kaydeden:
    """Sorulup sorulmadığını kaydeden ve sabit cevap veren prompter."""

    def __init__(self, cevap=ApprovalAnswer.ONCE):
        self.cevap = cevap
        self.soruldu: list[str] = []

    async def confirm(self, request):
        self.soruldu.append(request.tool.name)
        return self.cevap


async def _karar(mod, arac, args, root, rules=None, prompter=None, memory=None):
    prompter = prompter or _Kaydeden()
    politika = build_policy(mod, prompter, memory)
    return await politika.decide(build_request(arac, args, root=root, rules=rules)), prompter


# --- P-001: deny / ask / allow ------------------------------------------------- #


@pytest.mark.parametrize("mod", list(ApprovalMode))
async def test_deny_kurali_her_kipte_sorulmadan_engeller(tmp_path, mod):
    kurallar = _kurallar(("Bash(git push *)", "deny"))
    karar, prompter = await _karar(
        mod, _arac(), {"command": "git push origin main"}, tmp_path, kurallar
    )
    assert karar is Decision.BLOCKED
    assert prompter.soruldu == []


async def test_deny_kurali_dosya_aracini_bypass_kipinde_de_engeller(tmp_path):
    kurallar = _kurallar(("Edit(/.env)", "deny"))
    karar, _ = await _karar(
        ApprovalMode.BYPASS,
        _arac("write_file"),
        {"path": ".env", "content": "x"},
        tmp_path,
        kurallar,
    )
    assert karar is Decision.BLOCKED
    istek = build_request(_arac("write_file"), {"path": ".env"}, root=tmp_path, rules=kurallar)
    assert istek.pre_denied is not None and "Edit(/.env)" in istek.pre_denied


async def test_ask_kurali_otomatik_kipte_bile_sorar_ve_allow_kurali_manuelde_sormaz(tmp_path):
    kurallar = _kurallar(("Bash(npm run *)", "ask"), ("Edit(/src/**)", "allow"))
    # Otomatik kip `npm run build`i sormazdı; `ask` kuralı sordurur.
    karar, prompter = await _karar(
        ApprovalMode.AUTO, _arac(), {"command": "npm run build"}, tmp_path, kurallar
    )
    assert karar is Decision.ALLOW and prompter.soruldu == ["run_shell"]
    # Manuel kip her yazmayı sorardı; `allow` kuralı sormaz.
    karar, prompter = await _karar(
        ApprovalMode.SECURITY,
        _arac("write_file"),
        {"path": "src/a.py", "content": ""},
        tmp_path,
        kurallar,
    )
    assert karar is Decision.ALLOW and prompter.soruldu == []


async def test_ask_kurali_oturum_hafizasiyla_susturulamaz(tmp_path):
    """Ölçüldü (31 Ekim): `decide` pre_ask varken de `is_remembered`a bakıyordu ve kart
    'bu oturumda tekrar sorma' seçeneğini sunuyordu; ikinci `git push` sorulmadan geçiyordu."""
    kurallar = _kurallar(("Bash(git push *)", "ask"))
    bellek = ApprovalMemory()
    istek = build_request(
        _arac(), {"command": "git push origin dev"}, root=tmp_path, rules=kurallar
    )
    assert istek.pre_ask is not None and not istek.can_remember
    karar, prompter = await _karar(
        ApprovalMode.AUTO,
        _arac(),
        {"command": "git push origin dev"},
        tmp_path,
        kurallar,
        prompter=_Kaydeden(ApprovalAnswer.SESSION),
        memory=bellek,
    )
    assert karar is Decision.ALLOW and prompter.soruldu == ["run_shell"]
    karar, prompter = await _karar(
        ApprovalMode.AUTO,
        _arac(),
        {"command": "git push origin dev"},
        tmp_path,
        kurallar,
        prompter=_Kaydeden(ApprovalAnswer.ONCE),
        memory=bellek,
    )
    assert karar is Decision.ALLOW and prompter.soruldu == ["run_shell"]


async def test_yikici_komut_allow_kuraliyla_bile_sorulur(tmp_path):
    kurallar = _kurallar(("Bash(*)", "allow"))
    karar, prompter = await _karar(
        ApprovalMode.AUTO, _arac(), {"command": "git push --force"}, tmp_path, kurallar
    )
    assert karar is Decision.ALLOW and prompter.soruldu == ["run_shell"]


async def test_kural_yokken_eski_davranis_korunur(tmp_path):
    karar, prompter = await _karar(ApprovalMode.AUTO, _arac(), {"command": "ls"}, tmp_path, None)
    assert karar is Decision.ALLOW and prompter.soruldu == []


# --- P-002: korumalı yollar ve kök-dışı engel ------------------------------------ #


@pytest.mark.parametrize(
    ("arac", "args"),
    [
        ("write_file", {"path": ".claude/settings.local.json", "content": "{}"}),
        ("edit_file", {"path": ".git/config", "old": "a", "new": "b"}),
        ("write_file", {"path": ".fusion/tools/x.py", "content": ""}),
        ("run_shell", {"command": "rm -rf .git"}),
        ("run_shell", {"command": "echo '{}' > .claude/settings.local.json"}),
        ("run_shell", {"command": "sed -i 's/a/b/' .github/workflows/ci.yml"}),
    ],
)
async def test_korumali_yola_yazma_her_kipte_sorulur_ve_hatirlanmaz(tmp_path, arac, args):
    bellek = ApprovalMemory()
    for mod in (ApprovalMode.AUTO, ApprovalMode.ACCEPT_EDITS):
        prompter = _Kaydeden(ApprovalAnswer.SESSION)
        karar, _ = await _karar(mod, _arac(arac), args, tmp_path, prompter=prompter, memory=bellek)
        assert karar is Decision.ALLOW
        assert prompter.soruldu == [arac], (mod, arac)
    istek = build_request(_arac(arac), args, root=tmp_path)
    assert istek.danger is not None and "korumalı" in istek.danger
    assert not istek.can_remember and not istek.can_persist


@pytest.mark.parametrize(
    ("arac", "args"),
    [
        ("read_file", {"path": ".claude/settings.local.json"}),
        ("run_shell", {"command": "git log --oneline"}),
        ("run_shell", {"command": "cat .claude/agents/x.md"}),
        ("write_file", {"path": "src/.gitignore", "content": ""}),
    ],
)
def test_korumali_yolu_okumak_ve_benzer_adlar_yikici_degil(tmp_path, arac, args):
    assert protected_path_reason(arac, args, tmp_path, is_shell=arac == "run_shell") is None


@pytest.mark.parametrize(
    ("arac", "args"),
    [
        ("download_file", {"url": "https://x/y", "path": ".git/hooks/pre-commit"}),
        ("extract_archive", {"path": "a.tgz", "dest": ".git/hooks"}),
        ("extract_archive", {"path": ".claude/a.zip"}),
        ("generate_image", {"prompt": "x", "path": ".github/workflows/a.png"}),
        ("optimize_image", {"path": "a.png", "out": ".claude/b.webp"}),
        ("write_file", {"path": ".GIT/config", "content": ""}),
        ("run_shell", {"command": "cd .git && rm -rf hooks"}),
        ("run_shell", {"command": "cd .claude; echo x > settings.local.json"}),
        ("run_shell", {"command": "tar -C .git/hooks -xf a.tgz"}),
        ("run_shell", {"command": "curl -o .git/hooks/pre-commit https://x/y"}),
        ("run_shell", {"command": "unzip a.zip -d .claude"}),
    ],
)
def test_korumali_yol_tum_yazma_araclarini_ve_cd_zincirini_kapsar(tmp_path, arac, args):
    """Ölçüldü (31 Ekim): yalnız write_file/edit_file/multi_edit/create_file ve düz kabuk hedefleri
    bakılıyordu; `download_file .git/hooks/pre-commit`, `extract_archive dest=.git/hooks`,
    `cd .git && rm -rf hooks`, `.GIT/config` korumasızdı (auto kipte sorulmadan geçiyordu)."""
    sebep = protected_path_reason(arac, args, tmp_path, is_shell=arac == "run_shell")
    assert sebep is not None and "korumalı" in sebep, (arac, args)
    assert build_request(_arac(arac), args, root=tmp_path).danger is not None


async def test_kok_disina_yazma_engeli_acikken_sorulmadan_kapatilir(tmp_path):
    kurallar = _kurallar(block_writes_outside_root=True)
    disari = tmp_path / "disari" / "x.txt"
    karar, prompter = await _karar(
        ApprovalMode.AUTO,
        _arac("write_file"),
        {"path": str(disari), "content": ""},
        tmp_path / "proje",
        kurallar,
    )
    assert karar is Decision.BLOCKED and prompter.soruldu == []
    istek = build_request(
        _arac("write_file"), {"path": str(disari)}, root=tmp_path / "proje", rules=kurallar
    )
    assert "--add-dir" in (istek.pre_denied or "")


@pytest.mark.parametrize(
    "komut", ["echo x > ~/.zshrc", "cat a | tee /etc/hosts", "ls >> ../disari.txt"]
)
async def test_kok_disina_yazma_engeli_kabuk_yonlendirmesini_de_kapatir(tmp_path, komut):
    """Ölçüldü (31 Ekim): engel yalnız dosya araçlarında uygulanıyordu; `echo x > ~/.zshrc`
    bypass kipinde sorulmadan çalışıyordu, Ayarlar ise 'onay bile sorulmadan engellenir' diyordu."""
    kurallar = _kurallar(block_writes_outside_root=True)
    proje = tmp_path / "proje"
    proje.mkdir()
    for mod in (ApprovalMode.BYPASS, ApprovalMode.AUTO):
        karar, prompter = await _karar(mod, _arac(), {"command": komut}, proje, kurallar)
        assert karar is Decision.BLOCKED and prompter.soruldu == [], (mod, komut)
    istek = build_request(_arac(), {"command": komut}, root=proje, rules=kurallar)
    assert "--add-dir" in (istek.pre_denied or "")
    # Proje içine yönlendirme serbesttir; engel kapalıyken dışarı yazma yine sorulur.
    istek = build_request(_arac(), {"command": "echo x > cikti.txt"}, root=proje, rules=kurallar)
    assert istek.pre_denied is None
    karar, prompter = await _karar(
        ApprovalMode.AUTO, _arac(), {"command": komut}, proje, _kurallar()
    )
    assert karar is Decision.ALLOW and prompter.soruldu == ["run_shell"]


def test_kok_disi_engel_dosya_araci_duzeyinde_tek_yonludur(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    disari = tmp_path / "disari.txt"
    disari.write_text("x", encoding="utf-8")
    baglam = ToolContext(root=proje, restrict_to_root=False, block_writes_outside_root=True)
    # Yazma kapalı, okuma serbest.
    with pytest.raises(Exception, match="block_writes_outside_root"):
        writable_path(baglam, str(disari))
    assert resolve_path(baglam, str(disari)) == disari
    baglam = ToolContext(root=proje, restrict_to_root=False, block_reads_outside_root=True)
    with pytest.raises(Exception, match="--add-dir"):
        resolve_path(baglam, str(disari))
    # `--add-dir` ile açılan dizin serbesttir.
    acik = ToolContext(
        root=proje, restrict_to_root=False, block_reads_outside_root=True, extra_roots=(tmp_path,)
    )
    assert resolve_path(acik, str(disari)) == disari.resolve()


# --- P-003: kalıcı "bir daha sorma" -------------------------------------------- #


def test_kural_onerisi_dar_uretilir(tmp_path):
    istek = build_request(_arac(), {"command": "git status --short"}, root=tmp_path)
    assert rule_for_request(istek, tmp_path).pattern == "Bash(git status *)"
    istek = build_request(_arac(), {"command": "pytest"}, root=tmp_path)
    assert rule_for_request(istek, tmp_path).pattern == "Bash(pytest)"
    istek = build_request(_arac(), {"command": "git status && git diff"}, root=tmp_path)
    assert rule_for_request(istek, tmp_path).pattern == "Bash(git status && git diff)"
    istek = build_request(_arac("write_file"), {"path": "src/alt/a.py"}, root=tmp_path)
    assert rule_for_request(istek, tmp_path).pattern == "Edit(/src/alt/**)"
    istek = build_request(_arac("desktop_click"), {"x": 1}, root=tmp_path)
    assert rule_for_request(istek, tmp_path).pattern == "desktop_click"


@pytest.mark.parametrize(
    ("komut", "kural"),
    [
        ("python -m pytest", "Bash(python -m pytest)"),
        ('python3 -c "import os"', 'Bash(python3 -c "import os")'),
        ("node script.js", "Bash(node script.js)"),
        ("bash deploy.sh", "Bash(bash deploy.sh)"),
        ("find . -name x -delete", "Bash(find . -name x -delete)"),
        ("ls -la", "Bash(ls -la)"),
        ("npm test -- --watch=false", "Bash(npm test *)"),
        ("git status --short", "Bash(git status *)"),
    ],
)
def test_kural_onerisi_yorumlayicida_ve_bayrakli_komutta_genel_on_eke_dusmez(
    tmp_path, komut, kural
):
    """Ölçüldü (31 Ekim): `python -m pytest` için `Bash(python *)` yazılıyordu; bu, her projede
    `python -c '…'` dahil sınırsız izin demekti."""
    istek = build_request(_arac(), {"command": komut}, root=tmp_path)
    assert rule_for_request(istek, tmp_path).pattern == kural


async def test_bir_daha_sorma_kurali_dosyaya_yazilir_ve_oturumda_hatirlanir(tmp_path):
    proje = tmp_path / "proje"
    proje.mkdir()
    bellek = ApprovalMemory()
    bellek.rule_writer = lambda request: remember_always(proje, request)
    prompter = _Kaydeden(ApprovalAnswer.ALWAYS)
    karar, _ = await _karar(
        ApprovalMode.SECURITY,
        _arac(),
        {"command": "npm test -- --watch=false"},
        proje,
        prompter=prompter,
        memory=bellek,
    )
    assert karar is Decision.ALLOW
    # Güvenilmeyen (kayıtsız, izin dosyasız) projede yerel dosyaya yazılır ve karma kaydedilir.
    hedef = proje / trust.PROJECT_PERMISSIONS_PATH
    assert persist_target(proje) == hedef
    veri = json.loads(hedef.read_text(encoding="utf-8"))
    assert veri["permissions"]["allow"] == ["Bash(npm test *)"]
    assert trust.is_permissions_trusted(proje)
    assert bellek.take_notices() == [f"Bash(npm test *) → {hedef}"]
    # Aynı oturumda ikinci çağrı sorulmaz (hafıza).
    prompter2 = _Kaydeden(ApprovalAnswer.DENY)
    karar, _ = await _karar(
        ApprovalMode.SECURITY,
        _arac(),
        {"command": "npm test -- --watch=false"},
        proje,
        prompter=prompter2,
        memory=bellek,
    )
    assert karar is Decision.ALLOW and prompter2.soruldu == []


def test_guvenilmeyen_izin_dosyasi_varsa_kullanici_dosyasina_yazilir(tmp_path):
    proje = tmp_path / "proje"
    (proje / ".claude").mkdir(parents=True)
    (proje / trust.PROJECT_PERMISSIONS_PATH).write_text('{"permissions":{"allow":["Bash(*)"]}}')
    assert persist_target(proje) == user_permissions_file()


def test_kalici_kural_aciklamasi_kullanici_dosyasina_dusuyorsa_tum_projeler_der(tmp_path):
    """Ölçüldü (31 Ekim): proje izin dosyası güvenilmiyorken kural sessizce kullanıcının
    permissions.json'ına yazılıyor, kart 'her oturumda geçerli olur' deyip kapsamı söylemiyordu."""
    from fusion_cli.appserver.bridges import _approval_options
    from fusion_cli.engines.agent.permission_persist import always_description

    proje = tmp_path / "proje"
    (proje / ".claude").mkdir(parents=True)
    istek = build_request(_arac(), {"command": "npm test"}, root=proje)
    # İzin dosyası yok → projeye yazılır; açıklama kapsam genişletmez.
    assert "tüm projeler" not in always_description(istek, proje).lower()
    (proje / trust.PROJECT_PERMISSIONS_PATH).write_text('{"permissions":{"allow":["Bash(*)"]}}')
    aciklama = always_description(istek, proje)
    assert "tüm projeler" in aciklama.lower() and "Bash(npm test *)" in aciklama
    assert str(user_permissions_file()) in aciklama
    secenekler = {s["deger"]: s for s in _approval_options(istek, proje)}
    assert "tüm projeler" in secenekler["always"]["aciklama"].lower()


async def test_yazici_bagli_degilse_bir_daha_sorma_oturumda_hatirlanir_bildirim_uretmez(tmp_path):
    """`rule_writer is None` dalı (paperclip gibi yazıcısız yüzey): izin verilir, oturumda
    hatırlanır, dosyaya yazılmaz, bildirim yoktur."""
    bellek = ApprovalMemory()
    assert bellek.rule_writer is None
    karar, _ = await _karar(
        ApprovalMode.SECURITY,
        _arac(),
        {"command": "npm test"},
        tmp_path,
        prompter=_Kaydeden(ApprovalAnswer.ALWAYS),
        memory=bellek,
    )
    assert karar is Decision.ALLOW and bellek.take_notices() == []
    assert not (tmp_path / trust.PROJECT_PERMISSIONS_PATH).exists()
    karar, prompter = await _karar(
        ApprovalMode.SECURITY,
        _arac(),
        {"command": "npm test"},
        tmp_path,
        prompter=_Kaydeden(ApprovalAnswer.DENY),
        memory=bellek,
    )
    assert karar is Decision.ALLOW and prompter.soruldu == []


async def test_yikici_istekte_bir_daha_sorma_kural_yazmaz(tmp_path):
    bellek = ApprovalMemory()
    yazildi: list[str] = []
    bellek.rule_writer = lambda request: yazildi.append(request.tool.name) or "x"
    karar, _ = await _karar(
        ApprovalMode.AUTO,
        _arac(),
        {"command": "git push --force"},
        tmp_path,
        prompter=_Kaydeden(ApprovalAnswer.ALWAYS),
        memory=bellek,
    )
    assert karar is Decision.ALLOW and yazildi == []


# --- P-013: ret gerekçesi ------------------------------------------------------- #


async def test_gerekceli_ret_denial_dondurur_notsuz_ret_denied(tmp_path):
    karar, _ = await _karar(
        ApprovalMode.SECURITY,
        _arac(),
        {"command": "pytest"},
        tmp_path,
        prompter=_Kaydeden(ApprovalReply(ApprovalAnswer.DENY, " önce lint ")),
    )
    assert karar == Denial("önce lint")
    assert karar.decision is Decision.DENIED
    karar, _ = await _karar(
        ApprovalMode.SECURITY,
        _arac(),
        {"command": "pytest"},
        tmp_path,
        prompter=_Kaydeden(ApprovalReply(False, "")),
    )
    assert karar is Decision.DENIED


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


class _NotluRed:
    async def confirm(self, request):
        return ApprovalReply(ApprovalAnswer.DENY, "pytest yerine `make test` kullan")


async def test_gerekceli_ret_turu_durdurmaz_model_gerekceyi_gorur(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("run_shell", command="pytest -q")]),
            model_result(
                "Tamam, `make test` ile çalıştırdım; sonuç `src/app.py:12` satırında doğrulandı."
            ),
        ]
    )
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.SECURITY, _NotluRed()),
        tool_context=ToolContext(root=tmp_path),
    )
    outcome = await run_agent("testleri koş", deps)
    # Tur DURMADI: model gerekçeyi gördü ve en az bir kez daha çağrıldı.
    assert provider.calls >= 2
    tool_mesajlari = [m for m in outcome.messages if m.role == "tool"]
    assert "make test" in tool_mesajlari[0].content
    assert "nasıl devam edeyim" not in outcome.final_text.lower()


# --- Döngü entegrasyonu: kurallar DEĞİŞTİRMEYEN araçlarda da uygulanır ----------- #


async def _dongu(monkeypatch, tmp_path, cagri, kurallar, mod=ApprovalMode.AUTO, prompter=None):
    """Tek araç çağrısını `_execute` üzerinden geçir; araç mesajlarını ve prompter'ı döndür."""
    sink = RecordingSink()
    provider = ScriptedProvider([model_result(tool_calls=[cagri]), model_result("bitti")])
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    prompter = prompter or _Kaydeden()
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(sink),
        policy=build_policy(mod, prompter),
        tool_context=ToolContext(root=tmp_path),
        permission_rules=kurallar,
    )
    outcome = await run_agent("oku", deps)
    return [m for m in outcome.messages if m.role == "tool"], prompter


@pytest.mark.parametrize("mod", [ApprovalMode.AUTO, ApprovalMode.BYPASS, ApprovalMode.PLAN])
async def test_deny_kurali_okuma_aracini_dongude_her_kipte_engeller(monkeypatch, tmp_path, mod):
    # Ölçüldü (31 Ekim): `_execute` kuralları yalnız `tool.mutating` araçta değerlendiriyordu;
    # `Read(~/.ssh/**)` gibi belgenin ana örneği `read_file` için hiç çalışmıyordu.
    (tmp_path / ".env").write_text("SIR=1", encoding="utf-8")
    kurallar = _kurallar(("Read(/.env)", "deny"))
    mesajlar, prompter = await _dongu(
        monkeypatch, tmp_path, tool_call("read_file", path=".env"), kurallar, mod
    )
    assert "izin kuralıyla engellendi" in mesajlar[0].content
    assert "SIR=1" not in mesajlar[0].content
    assert prompter.soruldu == []


async def test_deny_kurali_web_fetch_dongude_engeller(monkeypatch, tmp_path):
    kurallar = _kurallar(("WebFetch(domain:evil.com)", "deny"))
    mesajlar, _ = await _dongu(
        monkeypatch,
        tmp_path,
        tool_call("web_fetch", url="https://evil.com/x"),
        kurallar,
        ApprovalMode.BYPASS,
    )
    assert "izin kuralıyla engellendi" in mesajlar[0].content
    assert "WebFetch(domain:evil.com)" in mesajlar[0].content


async def test_ask_kurali_okuma_aracini_otomatik_kipte_sordurur(monkeypatch, tmp_path):
    (tmp_path / "gizli.txt").write_text("ICERIK", encoding="utf-8")
    kurallar = _kurallar(("Read(/gizli.txt)", "ask"))
    mesajlar, prompter = await _dongu(
        monkeypatch, tmp_path, tool_call("read_file", path="gizli.txt"), kurallar
    )
    assert prompter.soruldu == ["read_file"]
    assert "ICERIK" in mesajlar[0].content
    # Kuralsız okuma hiç sorulmaz (eski davranış korunur).
    mesajlar, prompter = await _dongu(
        monkeypatch, tmp_path, tool_call("read_file", path="gizli.txt"), _kurallar()
    )
    assert prompter.soruldu == [] and "ICERIK" in mesajlar[0].content
