"""Yerel görsele bakma aracı — dosya adı içeriği anlatmaz."""

from __future__ import annotations

import base64

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelResult, ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.engines.agent.loop import AgentDeps

from .fakes import AlwaysApprove, make_config

#: Geçerli 1x1 PNG (base64) — testin gerçek bir görsel dosyası olması için.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class _Publisher:
    def publish(self, event):
        del event


async def _hicbir_alt_ajan(*args, **kwargs):  # pragma: no cover - çağrılmaz
    raise AssertionError("alt ajan çalışmamalı")


def _deps(tmp_path, **overrides):
    return AgentDeps(
        config=make_config(**overrides),
        publisher=_Publisher(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _registry(deps):
    return build_agent_registry(deps, depth=0, run_agent=_hicbir_alt_ajan)


class _GorenSaglayici:
    """Kendisine gelen mesajı kaydeden sahte görsel modeli."""

    def __init__(self, text="256x256 boyutunda mavi bir uygulama ikonu; karakter sprite'ı değil."):
        self.text = text
        self.seen = []

    @property
    def label(self):
        return "sahte-goz"

    async def complete(self, request):
        self.seen.append(request)
        return ModelResult(name="goz", model="sahte", text=self.text, latency_ms=1, ok=True)


@pytest.fixture
def goren(monkeypatch):
    saglayici = _GorenSaglayici()

    def _build(spec, **kwargs):
        del spec, kwargs
        return saglayici

    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", _build)
    return saglayici


def test_gorsel_modeli_yoksa_arac_hic_sunulmaz(tmp_path):
    """Araç yalnız gerçekten bakabilecek bir model varken kaydedilir."""
    deps = _deps(tmp_path, vision=None)

    assert _registry(deps).get("view_image") is None


def test_gorsel_modeli_varsa_arac_sunulur(tmp_path):
    deps = _deps(tmp_path, vision=ModelSpec(name="goz", model="sahte/vl"))

    assert _registry(deps).get("view_image") is not None


async def test_gorsel_okunur_ve_model_aciklamasi_donulur(tmp_path, goren):
    (tmp_path / "player.png").write_bytes(_PNG)
    deps = _deps(tmp_path, vision=ModelSpec(name="goz", model="sahte/vl"))
    registry = _registry(deps)

    sonuc = await registry.execute("view_image", {"path": "player.png"}, deps.tool_context)

    assert sonuc.ok is True
    assert "uygulama ikonu" in sonuc.output
    mesaj = goren.seen[0].messages[0]
    assert mesaj.images and mesaj.images[0].startswith("data:image/png;base64,")


async def test_soru_verilirse_modele_iletilir(tmp_path, goren):
    (tmp_path / "a.png").write_bytes(_PNG)
    deps = _deps(tmp_path, vision=ModelSpec(name="goz", model="sahte/vl"))

    await _registry(deps).execute(
        "view_image", {"path": "a.png", "question": "Bu bir karakter mi?"}, deps.tool_context
    )

    assert "Bu bir karakter mi?" in goren.seen[0].messages[0].content


async def test_gorsel_olmayan_dosya_anlasilir_hata_verir(tmp_path, goren):
    (tmp_path / "not.txt").write_text("merhaba", encoding="utf-8")
    deps = _deps(tmp_path, vision=ModelSpec(name="goz", model="sahte/vl"))

    sonuc = await _registry(deps).execute("view_image", {"path": "not.txt"}, deps.tool_context)

    assert sonuc.ok is False
    assert "görsel" in sonuc.output.lower()


async def test_olmayan_dosya_anlasilir_hata_verir(tmp_path, goren):
    deps = _deps(tmp_path, vision=ModelSpec(name="goz", model="sahte/vl"))

    sonuc = await _registry(deps).execute("view_image", {"path": "yok.png"}, deps.tool_context)

    assert sonuc.ok is False


async def test_cok_buyuk_gorsel_reddedilir(tmp_path, goren):
    from fusion_cli.engines.agent.image_view import MAX_IMAGE_BYTES

    (tmp_path / "dev.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_IMAGE_BYTES + 1))
    deps = _deps(tmp_path, vision=ModelSpec(name="goz", model="sahte/vl"))

    sonuc = await _registry(deps).execute("view_image", {"path": "dev.png"}, deps.tool_context)

    assert sonuc.ok is False
    assert "büyük" in sonuc.output.lower()


async def test_gorsel_modeli_hatasi_yutulmaz(tmp_path, monkeypatch):
    """Ölçüldü: yapılandırılmış görsel modeli (nemotron-nano-12b-v2-vl) EOL oldu ve
    410 Gone dönüyordu.

    "Yanıt vermedi" demek kullanıcıyı da modeli de yanlış yöne iter; asıl sebep
    modelin kaldırılmış olmasıydı ve config değişmeden hiçbir deneme tutmaz.
    """
    from fusion_cli.core.types import ModelResult

    class _Olu:
        @property
        def label(self):
            return "olu"

        async def complete(self, request):
            del request
            return ModelResult(
                name="goz",
                model="olu",
                text="",
                latency_ms=1,
                ok=False,
                error="APIError: 410 Gone - model has reached its end of life",
            )

    monkeypatch.setattr("fusion_cli.providers.factory.build_provider", lambda spec, **kw: _Olu())
    (tmp_path / "a.png").write_bytes(_PNG)
    deps = _deps(tmp_path, vision=ModelSpec(name="goz", model="sahte/vl"))

    sonuc = await _registry(deps).execute("view_image", {"path": "a.png"}, deps.tool_context)

    assert sonuc.ok is False
    assert "410" in sonuc.output or "end of life" in sonuc.output


def test_kucuk_modelin_tekrar_dongusu_ayiklanir():
    """Ölçüldü: 11b görsel modeli aynı cümleyi sekiz kez tekrarladı.

    Küçük modeller uzun/çok parçalı soruda döngüye giriyor. Tekrar, cevabın
    bilgisini artırmaz ama isteme giren metni şişirir ve okunmasını zorlaştırır.
    """
    from fusion_cli.engines.agent.image_view import collapse_repeats

    ham = (
        "Görselde KENNEY StarterKit logosu var. Bir oyun logosu olarak kullanılabilir. "
        "Bir oyun logosu olarak kullanılabilir. Bir oyun logosu olarak kullanılabilir."
    )

    assert collapse_repeats(ham) == (
        "Görselde KENNEY StarterKit logosu var. Bir oyun logosu olarak kullanılabilir."
    )


def test_farkli_cumleler_korunur():
    metin = "Bu bir sprite. Saydam arka planı var. Ana renk mavi."

    from fusion_cli.engines.agent.image_view import collapse_repeats

    assert collapse_repeats(metin) == metin
