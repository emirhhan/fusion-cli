"""Kurulumda ve arayüzde ücretsiz API çırağına dönüş yolu (Faz 3, Görev 2, C5/C9).

Kullanıcı `/development` ile bir web modeline (`chatgpt_web/main/auto`, `tags:
[strict]`) kilitlenebilir; bu bilinçli bir seçimdir ama geri dönüşü yoktur. Bu
modül iki şeyi doğrular:

1. `providers/capabilities.py::apprentice_active` — agent şu an ücretsiz bir API
   modeliyle mi çalışıyor, yoksa (web/browser oturumuna) kilitli mi?
2. `config/model_select.py::reset_to_apprentice_default` — kullanıcı AÇIKÇA
   çağırdığında `strict` kilidini kaldırıp `low` kademesine (paketin gömülü
   ücretsiz varsayılanı) döner. Hiçbir arka plan kodu bunu kendiliğinden
   çağırmaz (RULES: kullanıcıya sorulmadan varsayılmaz).
"""

from __future__ import annotations

import json
from dataclasses import replace

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.config.loader import load_config
from fusion_cli.config.model_select import (
    SINGLE_MODEL_NAME,
    apply_single_model,
    reset_to_apprentice_default,
)
from fusion_cli.providers.capabilities import apprentice_active


def _gercek_kullanici_kilidi(config):
    """Bu makinedeki gerçek `~/.config/fusion-cli/config.yaml` şeklini üret (anahtarsız kopya).

    Kilit yalnız `agent`'ta değil: `/development` ile TEK model seçildiğinde
    `agent`, `judge` VE `candidates`'ın üçü de aynı `chatgpt_web/main/auto` +
    `tags: [strict]` spec'ine iner, `task_model_map`'teki her görev tipi de
    `secilen` adına bağlanır (`apply_single_model`, `config/model_select.py`).
    "Çırağa dön" yalnızca `agent.model`'i değiştirirse kullanıcı hakem/aday
    turlarında hâlâ web modeline takılı kalır; bu yüzden testin başlangıç
    durumu üçünü BİRDEN kilitli üretir.
    """
    return apply_single_model(config, "chatgpt_web/main/auto")


def test_strict_web_modelden_cirak_varsayilanina_donus():
    config = load_config()
    web_kilitli = _gercek_kullanici_kilidi(config)
    assert web_kilitli.agent.strict is True
    assert web_kilitli.judge.strict is True
    assert all(candidate.strict for candidate in web_kilitli.candidates)
    assert set(web_kilitli.task_model_map.values()) == {SINGLE_MODEL_NAME}

    donen = reset_to_apprentice_default(web_kilitli)

    beklenen = config.tier_by_name("low")
    assert beklenen is not None
    # Üçü BİRDEN API modeline döner; hiçbiri artık `chatgpt_web` ya da `strict` değil.
    assert donen.agent == beklenen.agent
    assert donen.judge == beklenen.judge
    assert donen.candidates == beklenen.candidates
    assert donen.agent.strict is False
    assert donen.judge.strict is False
    assert all(not candidate.strict for candidate in donen.candidates)
    assert all(not model.startswith("chatgpt_web/") for model in donen.agent.models)
    assert all(not model.startswith("chatgpt_web/") for model in donen.judge.models)
    for candidate in donen.candidates:
        assert all(not model.startswith("chatgpt_web/") for model in candidate.models)
    # `task_model_map` de yeni baş modele (agent rolü) bağlanır; eski `secilen`
    # adı havuzda artık yok, haritada da kalmamalı.
    assert set(donen.task_model_map.values()) == {donen.agent.name}
    assert SINGLE_MODEL_NAME not in donen.task_model_map.values()


def test_cirak_aktif_web_oturumunda_false_doner():
    config = load_config()
    web_kilitli = apply_single_model(config, "chatgpt_web/main/auto")

    assert apprentice_active(web_kilitli) is False


def test_cirak_aktif_api_modelinde_true_doner():
    config = load_config()
    cirak = reset_to_apprentice_default(apply_single_model(config, "chatgpt_web/main/auto"))

    assert apprentice_active(cirak) is True


class _MemorySecrets:
    available = True

    def list_names(self) -> tuple[str, ...]:
        return ()

    def set(self, name: str, value: str) -> None:  # pragma: no cover - kullanılmıyor
        raise NotImplementedError

    def delete(self, name: str) -> bool:  # pragma: no cover - kullanılmıyor
        raise NotImplementedError


async def _request(session: AppSession, lines: list[str], name: str, data: dict[str, object]):
    await session.handle(Request(id=name, name=name, data=data))
    return json.loads(lines[-1])["veri"]


async def test_kontrol_durumu_web_kilitliyken_cirak_aktif_false_ve_onerilen_model_doner(
    tmp_path, monkeypatch
):
    # Bu test agent'ı BİLEREK web'e kilitler; `kontrol.durum` bu durumda tek
    # seferlik bildirim işaretini KONTROL EDER (`_cirak_bildirimi_gerekli_mi`).
    # İşaret gerçek `~/.config/fusion-cli/`'a DOKUNMAMALI — XDG_CONFIG_HOME izole
    # bir geçici dizine yönlendirilir (bkz. `config/apprentice_notice.py`).
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    root = tmp_path / "project"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "home")
    session._secret_store = _MemorySecrets()  # type: ignore[assignment]
    session._state.config = apply_single_model(session._state.config, "chatgpt_web/main/auto")

    result = await _request(session, lines, "kontrol.durum", {})
    ikinci = await _request(session, lines, "kontrol.durum", {})
    await session.close()

    beklenen = load_config().tier_by_name("low")
    assert result["ok"] is True
    assert result["model"]["cirak_aktif"] is False
    assert result["model"]["onerilen_cirak"] == beklenen.agent.model
    # Bildirim TEK SEFERLİK: ilk çağrıda True, aynı işaretle ikinci çağrıda False.
    assert result["model"]["cirak_bildirim_goster"] is True
    assert ikinci["model"]["cirak_bildirim_goster"] is False


async def test_kontrol_cirak_varsayilanina_don_web_kilidini_kaldirir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    root = tmp_path / "project"
    root.mkdir()
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=tmp_path / "home")
    session._secret_store = _MemorySecrets()  # type: ignore[assignment]
    web_kilitli = apply_single_model(session._state.config, "chatgpt_web/main/auto")
    # Kalıcılaştırma gerçek `~/.config/fusion-cli/config.yaml`'a DOKUNMAMALI;
    # `config.source` açıkça geçici bir dosyaya bağlanır (bkz. `writer._target_path`).
    session._state.config = replace(web_kilitli, source=tmp_path / "config.yaml")

    result = await _request(session, lines, "kontrol.cirak_varsayilanina_don", {})
    durum = await _request(session, lines, "kontrol.durum", {})
    await session.close()

    assert result["ok"] is True
    assert session._state.config.agent.strict is False
    assert durum["model"]["cirak_aktif"] is True


def test_acilis_bildirimi_web_kilitliyken_bir_kez_gorunur_sonra_hic(tmp_path, monkeypatch):
    """CLI açılışı: `cli/repl/loop.py::apprentice_switch_notice` (Görev 2, §6.1)."""
    from fusion_cli.cli.repl.loop import apprentice_switch_notice

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    web_kilitli = apply_single_model(load_config(), "chatgpt_web/main/auto")

    ilk = apprentice_switch_notice(web_kilitli)
    ikinci = apprentice_switch_notice(web_kilitli)

    assert ilk is not None
    assert "chatgpt_web/main/auto" in ilk
    assert "/level cirak" in ilk
    assert ikinci is None


def test_acilis_bildirimi_cirak_zaten_aktifken_hic_cikmaz(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.loop import apprentice_switch_notice

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))

    assert apprentice_switch_notice(load_config()) is None


def test_level_cirak_takma_adi_ayni_kademeyi_uygular(tmp_path):
    """CLI/panel: `/level cirak`, `/level low` ile AYNI kademeyi uygular.

    İkinci bir kademe tanımı açılmaz (RULES "Genel Tasarım"); yalnızca isim
    çözümlemesi `low`'a düşer. Var olan `_level` komut işleyicisi kullanılır.
    """
    from fusion_cli.cli.repl.commands import _level
    from fusion_cli.cli.repl.state import Engine, ReplState
    from fusion_cli.memory.factory import null_memory

    # `source` açıkça geçici bir dosyaya bağlanır: `_level` kalıcılaştırma
    # DENER (`writer.write_model_section`) ve `source` boşsa gerçek kullanıcı
    # dizinine düşer — testler gerçek `~/.config/fusion-cli/`'a DOKUNMAMALI.
    baslangic = replace(load_config(), source=tmp_path / "config.yaml")
    state = ReplState(config=baslangic, memory=null_memory(), root=tmp_path, home=tmp_path / "ev")
    state.engine = Engine.AGENT

    _level(state, "cirak")
    cirak_sonucu = state.config

    state.config = replace(load_config(), source=tmp_path / "config-2.yaml")
    _level(state, "low")
    low_sonucu = state.config

    assert cirak_sonucu.agent == low_sonucu.agent
    assert cirak_sonucu.judge == low_sonucu.judge
    assert cirak_sonucu.candidates == low_sonucu.candidates
