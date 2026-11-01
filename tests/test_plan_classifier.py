"""Plan kipinde auto sınıflandırıcısı (#52) ve auto kipte varsayılan açık denetçi (#54).

Claude Code (code.claude.com/docs/en/settings-reference `useAutoModeDuringPlan`;
permission-modes): varsayılan `true`; auto kullanılabiliyorsa sınıflandırıcı planlama
komutlarını sormadan inceler, kritik yol silmesi hariç. `false` ise yerleşik salt okunur
küme dışındaki her komut sorulur. Kullanıcı, yerel ve yönetilen dosyadaki `false` geçerli;
`.claude/settings.json`'daki `false` yok sayılır. Auto kipte eylemi sınıflandırıcı inceler.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from fusion_cli.config.models import RuntimeConfig
from fusion_cli.config.permission_settings import use_auto_mode_during_plan
from fusion_cli.core.auto_review import AutoClassifierMode
from fusion_cli.core.events import AutoModeFellBack, AutoReviewDecided
from fusion_cli.core.tools import Tool, ToolContext
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import risk_classifier
from fusion_cli.engines.agent.approval import (
    ApprovalMemory,
    ApprovalMode,
    Decision,
    build_policy,
    build_request,
)
from fusion_cli.engines.agent.risk_classifier import review_auto_request

from .fakes import AlwaysReject, RecordingSink, ScriptedProvider, make_config, model_result


class _Publisher:
    def __init__(self) -> None:
        self.sink = RecordingSink()

    def publish(self, event: object) -> None:
        self.sink.handle(event)


@dataclass
class _Deps:
    config: object
    publisher: _Publisher
    tool_context: ToolContext
    memory: ApprovalMemory = field(default_factory=ApprovalMemory)
    mode: ApprovalMode = ApprovalMode.PLAN
    history: list[Message] = field(default_factory=lambda: [Message("user", "planla")])

    @property
    def auto_review(self):
        return self.memory.auto_review

    @property
    def approval_mode(self):
        return lambda: self.mode

    @property
    def live_history(self):
        return lambda: self.history


def _deps(root: Path, setting: AutoClassifierMode = AutoClassifierMode.ON) -> _Deps:
    config = make_config(runtime={"auto_classifier": setting, "auto_classifier_timeout_s": 2.0})
    return _Deps(config, _Publisher(), ToolContext(root=root))


def _model(monkeypatch, *cevaplar: str) -> ScriptedProvider:
    provider = ScriptedProvider([model_result(cevap) for cevap in cevaplar])
    monkeypatch.setattr(risk_classifier, "build_provider", lambda spec, **_kw: provider)
    return provider


def _json(karar: str) -> str:
    return json.dumps({"karar": karar, "gerekce": "planlama keşfi"}, ensure_ascii=False)


def _kabuk(komut: str, root: Path):
    arac = Tool(name="run_shell", description="", parameters={}, run=lambda a, c: None)
    return build_request(arac, {"command": komut}, root=root)


def _yaz(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _proje(tmp_path: Path) -> Path:
    root = tmp_path / "proje"
    root.mkdir()
    return root


# --- #54: auto kipte denetçi varsayılan açık ------------------------------------ #


def test_auto_classifier_varsayilan_acik():
    from dataclasses import fields

    varsayilan = next(f.default for f in fields(RuntimeConfig) if f.name == "auto_classifier")
    assert varsayilan is AutoClassifierMode.ON
    import yaml

    from fusion_cli.config import loader

    defaults = Path(loader.__file__).with_name("defaults.yaml")
    runtime = yaml.safe_load(defaults.read_text(encoding="utf-8"))["runtime"]
    assert AutoClassifierMode(runtime["auto_classifier"]) is AutoClassifierMode.ON


# --- #52: plan kipinde sınıflandırıcı ------------------------------------------- #


async def test_plan_kipinde_guvenli_karar_sormadan_calistirir(monkeypatch, tmp_path):
    root = _proje(tmp_path)
    saglayici = _model(monkeypatch, _json("guvenli"))
    deps = _deps(root)
    istek = await review_auto_request(_kabuk("npm install", root), deps)
    politika = build_policy(ApprovalMode.PLAN, AlwaysReject(), deps.memory)
    assert await politika.decide(istek) is Decision.ALLOW
    assert saglayici.calls == 1
    olay = next(e for e in deps.publisher.sink.events if isinstance(e, AutoReviewDecided))
    assert olay.summary == "npm install"


async def test_plan_kipinde_riskli_karar_sorar_ve_kip_dusurmez(monkeypatch, tmp_path):
    root = _proje(tmp_path)
    _model(monkeypatch, *([_json("riskli")] * 4))
    deps = _deps(root)
    politika = build_policy(ApprovalMode.PLAN, AlwaysReject(), deps.memory)
    for sira in range(4):
        istek = await review_auto_request(_kabuk(f"npm install paket{sira}", root), deps)
        assert await politika.decide(istek) is Decision.DENIED
    assert not any(isinstance(e, AutoModeFellBack) for e in deps.publisher.sink.events)
    assert deps.memory.auto_review.fell_back is False


async def test_kullanici_ayari_false_plan_siniflandiricisini_kapatir(monkeypatch, tmp_path):
    root = _proje(tmp_path)
    _yaz(Path.home() / ".claude" / "settings.json", {"useAutoModeDuringPlan": False})
    saglayici = _model(monkeypatch, _json("guvenli"))
    deps = _deps(root)
    istek = _kabuk("npm install", root)
    assert await review_auto_request(istek, deps) is istek
    assert saglayici.calls == 0
    assert use_auto_mode_during_plan(root) is False


def test_proje_ayarindaki_false_yok_sayilir_yereldeki_gecerli(tmp_path):
    root = _proje(tmp_path)
    _yaz(root / ".claude" / "settings.json", {"useAutoModeDuringPlan": False})
    assert use_auto_mode_during_plan(root) is True
    _yaz(root / ".claude" / "settings.local.json", {"useAutoModeDuringPlan": False})
    assert use_auto_mode_during_plan(root) is False


async def test_auto_kapaliysa_ya_da_denetci_kapaliysa_plan_sorar(monkeypatch, tmp_path):
    root = _proje(tmp_path)
    saglayici = _model(monkeypatch, _json("guvenli"))
    kapali = _deps(root, AutoClassifierMode.OFF)
    istek = _kabuk("npm install", root)
    assert await review_auto_request(istek, kapali) is istek
    _yaz(Path.home() / ".claude" / "settings.json", {"permissions": {"disableAutoMode": "disable"}})
    assert await review_auto_request(istek, _deps(root)) is istek
    assert saglayici.calls == 0


async def test_kritik_silme_okuma_ve_bypass_plan_siniflandiricisina_gitmez(monkeypatch, tmp_path):
    root = _proje(tmp_path)
    saglayici = _model(monkeypatch, _json("guvenli"))
    deps = _deps(root)
    for komut in ("rm -rf /", "rm -rf ~", "ls -la", "sudo npm i"):
        istek = _kabuk(komut, root)
        assert await review_auto_request(istek, deps) is istek
    deps.memory.plan_bypass = True
    istek = _kabuk("npm install", root)
    assert await review_auto_request(istek, deps) is istek
    assert saglayici.calls == 0


async def test_model_yoksa_plan_kipi_eskisi_gibi_sorar(monkeypatch, tmp_path):
    root = _proje(tmp_path)
    _model(monkeypatch, "bozuk cevap")
    deps = _deps(root)
    istek = await review_auto_request(_kabuk("npm install", root), deps)
    politika = build_policy(ApprovalMode.PLAN, AlwaysReject(), deps.memory)
    assert await politika.decide(istek) is Decision.DENIED
