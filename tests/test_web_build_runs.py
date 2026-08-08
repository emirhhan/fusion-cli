"""Uçtan uca web görevi koşuları — gerçek agent döngüsü, betiklenmiş model.

Bu dosya kullanıcının GERÇEK başarısız koşusunu yeniden oynatır. O koşuda model
`scaffold_web` çağırdı, ardından iskele dosyasını doldurmak için `write_file`
denedi, toptan-yazma kısıtına takıldı, `edit_file` ile 'old' metnini tutturamadı,
içeriği öğrenmek için yeniden okumaya kalkınca tekrar kapısına takıldı ve tur
"3 turdur ilerleme yok" ile öldü. Tek satır gerçek içerik üretilmedi.

Buradaki testler sahte bir sağlayıcı kullanır ama SAHTE OLMAYAN her şeyi gerçek
çalıştırır: araç kayıt defteri, onay politikası, sözleşme doğrulaması, tekrar
kapısı, boşta-tur kapısı ve dosya sistemi. Ağ erişimi yoktur.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

#: Ölçülen koşuda kullanılan sağlayıcı. Toptan-yazma kısıtı YALNIZCA web
#: modellerinde çalışır; API modeliyle koşmak hatayı hiç göstermezdi.
WEB_MODEL = "gemini_web/pro"

#: Modelin iskeleyi doldururken yazdığı gerçek sayfa. İçeriğin kendisi önemli
#: değil; diske BU metnin inip inmediği önemli.
DOLU_SAYFA = """<!DOCTYPE html>
<html lang="tr">
<head><meta charset="UTF-8"><title>Ekipman Zinciri</title></head>
<body>
  <header class="site-header"><a class="logo" href="/">Ekipman Zinciri</a></header>
  <main>
    <section class="section"><h1>Spor Ekipmanları</h1></section>
  </main>
  <footer class="site-footer"><small>&copy; 2026</small></footer>
</body>
</html>
"""


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self._sink = sink

    def publish(self, event: object) -> None:
        self._sink.handle(event)


def _web_deps(tmp_path: Path, sink: RecordingSink) -> AgentDeps:
    """Gerçek web oturumu yapılandırmasıyla bağımlılıklar — is_web=True olsun."""
    config = make_config(
        agent=ModelSpec(name="agent", model=WEB_MODEL),
        web_sessions=(
            WebSessionConfig(model=WEB_MODEL, transport="browser", tool_support="emulated"),
        ),
        runtime={"agent_max_idle_rounds": 3, "agent_max_steps": 20},
    )
    return AgentDeps(
        config=config,
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _kur(monkeypatch: pytest.MonkeyPatch, provider: ScriptedProvider) -> ScriptedProvider:
    monkeypatch.setattr(agent_loop, "build_provider", lambda *a, **k: provider)
    return provider


def _arac_olaylari(sink: RecordingSink) -> list[ToolExecuted]:
    return [olay for olay in sink.events if isinstance(olay, ToolExecuted)]


def _bloklananlar(sink: RecordingSink) -> list[str]:
    return [
        olay.name
        for olay in _arac_olaylari(sink)
        if olay.outcome in (ToolOutcome.BLOCKED, ToolOutcome.FAILED)
    ]


@pytest.fixture
def sink() -> RecordingSink:
    return RecordingSink()


# --------------------------------------------------------------------------- #
# Koşu 1 — kullanıcının başarısız koşusunun birebir tekrarı
# --------------------------------------------------------------------------- #


async def test_kosu_iskele_kurup_doldurma_tamamlanir(monkeypatch, tmp_path, sink):
    """Gerçek koşu: iskele kur, sonra sayfayı doldur. Eskiden burada kilitleniyordu."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=(tool_call("scaffold_web", path="."),)),
                model_result(
                    tool_calls=(tool_call("write_file", path="index.html", content=DOLU_SAYFA),)
                ),
                model_result("Sayfa hazırlandı ve `index.html:1` içine yazıldı."),
            ]
        ),
    )
    deps = _web_deps(tmp_path, sink)

    sonuc = await run_agent("spor ekipmanları için web sitesi yap", deps, verify=False)

    assert sonuc.ok, "tur temiz bitmeliydi"
    assert not sonuc.hit_step_limit, "boşta-tur kapısına takılmamalıydı"
    assert _bloklananlar(sink) == [], f"hiçbir araç bloklanmamalıydı: {_bloklananlar(sink)}"
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == DOLU_SAYFA


async def test_kosu_kullanicinin_dosyasi_hala_korunur(monkeypatch, tmp_path, sink):
    """Kilit açıldı diye koruma kalkmamalı: agent'ın yazmadığı dosya korunur."""
    (tmp_path / "index.html").write_text("<h1>kullanıcının emeği</h1>", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=(tool_call("write_file", path="index.html", content=DOLU_SAYFA),)
                ),
                model_result("Var olan dosyayı ezmedim."),
            ]
        ),
    )
    deps = _web_deps(tmp_path, sink)

    await run_agent("index.html'i yeniden yaz", deps, verify=False)

    korunan = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert korunan == "<h1>kullanıcının emeği</h1>", "kullanıcının dosyası EZİLDİ"
    assert "write_file" in _bloklananlar(sink)


# --------------------------------------------------------------------------- #
# Koşu 2 — çok dosyalı büyük görev, tur boyunca kilitlenmeden
# --------------------------------------------------------------------------- #


async def test_kosu_cok_dosyali_site_tek_turda_bitirilir(monkeypatch, tmp_path, sink):
    """İskele + üç dosya doldurma + doğrulama okuması: gerçek bir sitenin akışı."""
    stil = ":root { --brand: #0a5; }\n.site-header { position: sticky; top: 0; }\n"
    betik = "import { placeholderImage } from './format.js';\ninit();\n"
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=(tool_call("scaffold_web", path="."),)),
                model_result(
                    tool_calls=(tool_call("write_file", path="index.html", content=DOLU_SAYFA),)
                ),
                model_result(
                    tool_calls=(tool_call("write_file", path="style.css", content=stil),)
                ),
                model_result(
                    tool_calls=(tool_call("write_file", path="script.js", content=betik),)
                ),
                model_result(tool_calls=(tool_call("read_file", path="index.html"),)),
                model_result("Üç dosya yazıldı ve `index.html:1` doğrulandı."),
            ]
        ),
    )
    deps = _web_deps(tmp_path, sink)

    sonuc = await run_agent("spor sitesi yap: sayfa, stil ve betik", deps, verify=False)

    assert sonuc.ok
    assert _bloklananlar(sink) == []
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == DOLU_SAYFA
    assert (tmp_path / "style.css").read_text(encoding="utf-8") == stil
    assert (tmp_path / "script.js").read_text(encoding="utf-8") == betik
    # İskele dosyaları korunmalı: model onları yeniden yazmadı.
    assert "--space-1" in (tmp_path / "tokens.css").read_text(encoding="utf-8")


async def test_kosu_ayni_dosyayi_iki_kez_yazma_hala_tekrar_sayilir(monkeypatch, tmp_path, sink):
    """Kilit açıldı diye tekrar kapısı gevşememeli: aynı yazma iki kez istenmez."""
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=(tool_call("scaffold_web", path="."),)),
                model_result(
                    tool_calls=(tool_call("write_file", path="index.html", content=DOLU_SAYFA),)
                ),
                model_result(
                    tool_calls=(tool_call("write_file", path="index.html", content=DOLU_SAYFA),)
                ),
                model_result("bitti"),
            ]
        ),
    )
    deps = _web_deps(tmp_path, sink)

    await run_agent("siteyi kur", deps, verify=False)

    engellenen = [
        olay for olay in _arac_olaylari(sink) if olay.outcome is ToolOutcome.BLOCKED
    ]
    assert engellenen, "birebir aynı yazma ikinci kez çalıştırılmamalıydı"
    assert "TOOL_CALL_DUPLICATE" in engellenen[0].output


# --------------------------------------------------------------------------- #
# Koşu 3 — var olan siteyi taklit görevi: iskele dayatılmamalı, uydurulmamalı
# --------------------------------------------------------------------------- #


async def test_kosu_var_olan_site_uzerinde_iskele_uyarisi_cikar(monkeypatch, tmp_path, sink):
    """Dizinde zaten site varken iskele çağrılırsa araç sonucu modeli uyarmalı."""
    (tmp_path / "urunler.html").write_text("<h1>mevcut site</h1>", encoding="utf-8")
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=(tool_call("scaffold_web", path="."),)),
                model_result("Dizinde zaten bir site var; iskeleyi doldurmadım."),
            ]
        ),
    )
    deps = _web_deps(tmp_path, sink)

    await run_agent("bu klasördeki siteyi düzenle", deps, verify=False)

    iskele = next(olay for olay in _arac_olaylari(sink) if olay.name == "scaffold_web")
    assert "DİKKAT" in iskele.output
    assert "urunler.html" in iskele.output
