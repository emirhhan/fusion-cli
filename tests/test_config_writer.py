"""Seçilen modellerin kullanıcı yapılandırmasına kalıcı yazılması."""

from __future__ import annotations

import multiprocessing
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from fusion_cli.config.loader import load_config
from fusion_cli.config.model_select import apply_tier
from fusion_cli.config.models import McpServerConfig
from fusion_cli.config.writer import write_mcp_servers, write_model_section, write_provider
from fusion_cli.core.errors import ConfigError


def _paused_model_write(
    path: Path,
    read_finished: multiprocessing.synchronize.Event,
    resume: multiprocessing.synchronize.Event,
) -> None:
    """İlk okumadan sonra yazımı durdur; yarış sırasını deterministik yap."""
    from fusion_cli.config import writer

    original_read = writer._read_existing

    def paused_read(target: Path) -> dict[str, object]:
        existing = original_read(target)
        read_finished.set()
        if not resume.wait(timeout=10):
            raise TimeoutError("eşzamanlı config testi devam sinyali alamadı")
        return existing

    writer._read_existing = paused_read
    writer.write_model_section(apply_tier(load_config(), "premium"), path)


def _provider_write(
    path: Path,
    started: multiprocessing.synchronize.Event,
    finished: multiprocessing.synchronize.Event,
) -> None:
    started.set()
    write_provider(load_config(), "openrouter", path)
    finished.set()


def test_yazilan_dosya_geri_okununca_ayni_modelleri_verir(tmp_path):
    """Round-trip: yazmak ile yüklemek birbirinin tersi olmalı."""
    hedef = tmp_path / "config.yaml"
    secilen = apply_tier(load_config(), "premium")

    write_model_section(secilen, hedef)
    geri = load_config(hedef)

    assert geri.agent == secilen.agent
    assert geri.judge == secilen.judge
    assert geri.candidates == secilen.candidates


def test_her_kademe_yazilip_geri_okunabilir(tmp_path):
    """Bir kademe yazıldığında yükleyicinin doğrulamasından geçmeli."""
    config = load_config()

    for kademe in config.tiers:
        hedef = tmp_path / f"{kademe.name}.yaml"
        secilen = apply_tier(config, kademe.name)

        write_model_section(secilen, hedef)

        assert load_config(hedef).agent == secilen.agent


def test_gorev_haritasi_da_yazilir(tmp_path):
    """Harita yazılmazsa dosya yüklenemez: harita eski kademenin adlarını işaret eder.

    Aday havuzu değişip harita eski hâlinde kalsaydı yükleyici "adlı aday tanımlı
    değil" hatası verir ve kullanıcı uygulamayı bir daha hiç açamazdı.
    """
    hedef = tmp_path / "config.yaml"
    secilen = apply_tier(load_config(), "premium")

    write_model_section(secilen, hedef)

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))
    adaylar = {aday["name"] for aday in yazilan["candidates"]}
    assert set(yazilan["task_model_map"].values()) <= adaylar


def test_diger_bolumlere_dokunulmaz(tmp_path):
    """Kullanıcının elle ayarladığı bölümler yeniden yazımda kaybolmamalı."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text(
        yaml.safe_dump({"runtime": {"max_tokens": 99}, "embedding": {"provider": "nim"}}),
        encoding="utf-8",
    )

    write_model_section(apply_tier(load_config(), "high"), hedef)

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))
    assert yazilan["runtime"]["max_tokens"] == 99
    assert yazilan["embedding"]["provider"] == "nim"


def test_kademe_tanimlari_yazilmaz(tmp_path):
    """`tiers` varsayılanların işidir; kopyalanırsa ikinci bir kaynak oluşurdu."""
    hedef = tmp_path / "config.yaml"

    write_model_section(apply_tier(load_config(), "ultra"), hedef)

    assert "tiers" not in yaml.safe_load(hedef.read_text(encoding="utf-8"))


def test_dosya_yoksa_olusturulur(tmp_path):
    hedef = tmp_path / "yeni" / "config.yaml"

    yazilan = write_model_section(load_config(), hedef)

    assert yazilan == hedef
    assert hedef.is_file()


def test_bos_alanlar_yazilmaz(tmp_path):
    """`tags: []` ve `fallback: []` satırları gürültüden başka bir şey değil."""
    hedef = tmp_path / "config.yaml"

    write_model_section(apply_tier(load_config(), "low"), hedef)

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))
    assert all(deger for aday in yazilan["candidates"] for deger in aday.values())


def test_bozuk_yaml_uzerine_yazilmaz(tmp_path):
    """Sessizce ezmek kullanıcının ayarlarını kaybettirirdi."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text("agent: [kapanmamis\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="geçerli YAML değil"):
        write_model_section(load_config(), hedef)


def test_yazim_atomiktir_gecici_dosya_birakilmaz(tmp_path):
    hedef = tmp_path / "config.yaml"

    write_model_section(load_config(), hedef)

    assert hedef.is_file()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.skipif(sys.platform == "win32", reason="fork yalnız macOS/Linux'ta var")
def test_iki_surec_farkli_config_bolumlerini_yazarken_guncellemeler_kaybolmaz(tmp_path):
    """Panel ve CLI'nin read-modify-write işlemleri tek transaction olmalı."""
    context = multiprocessing.get_context("fork")
    read_finished = context.Event()
    resume = context.Event()
    provider_started = context.Event()
    provider_finished = context.Event()
    hedef = tmp_path / "config.yaml"

    model_process = context.Process(
        target=_paused_model_write,
        args=(hedef, read_finished, resume),
    )
    provider_process = context.Process(
        target=_provider_write,
        args=(hedef, provider_started, provider_finished),
    )
    model_process.start()
    assert read_finished.wait(timeout=5)
    provider_process.start()
    assert provider_started.wait(timeout=5)

    provider_was_serialized = not provider_finished.wait(timeout=2)
    resume.set()
    model_process.join(timeout=10)
    provider_process.join(timeout=10)

    assert provider_was_serialized, "ikinci süreç ilk read-modify-write bitmeden yazdı"
    assert model_process.exitcode == 0
    assert provider_process.exitcode == 0
    written = yaml.safe_load(hedef.read_text(encoding="utf-8"))
    assert written["runtime"]["provider"] == "openrouter"
    assert written["agent"]["name"] == apply_tier(load_config(), "premium").agent.name


# --- MCP sunucu listesi ------------------------------------------------------ #


def test_mcp_sunucusu_yazilip_geri_okunabilir(tmp_path):
    """Round-trip: `fusion mcp-add` ile eklenen sunucu yükleyiciden aynen döner."""
    hedef = tmp_path / "config.yaml"
    sunucu = McpServerConfig(name="github", command="npx", args=("-y", "server-github"))
    config = replace(load_config(), mcp_servers=(sunucu,))

    write_mcp_servers(config, hedef)
    geri = load_config(hedef)

    assert geri.mcp_servers == (sunucu,)


def test_mcp_sunucusu_ayni_ada_yazilinca_uzerine_yazilir(tmp_path):
    """`mcp-add` aynı adla tekrar çağrılırsa eski komut değil yenisi kalmalı."""
    hedef = tmp_path / "config.yaml"
    eski = McpServerConfig(name="github", command="npx", args=("-y", "eski-paket"))
    write_mcp_servers(replace(load_config(), mcp_servers=(eski,)), hedef)

    yeni = McpServerConfig(name="github", command="npx", args=("-y", "yeni-paket"))
    write_mcp_servers(replace(load_config(), mcp_servers=(yeni,)), hedef)

    assert load_config(hedef).mcp_servers == (yeni,)


def test_mcp_sunucusu_diger_bolumlere_dokunmaz(tmp_path):
    """Kullanıcının elle ayarladığı `runtime` gibi bölümler MCP yazımında kaybolmamalı."""
    hedef = tmp_path / "config.yaml"
    hedef.write_text(yaml.safe_dump({"runtime": {"max_tokens": 99}}), encoding="utf-8")
    sunucu = McpServerConfig(name="github", command="npx")

    write_mcp_servers(replace(load_config(), mcp_servers=(sunucu,)), hedef)

    yazilan = yaml.safe_load(hedef.read_text(encoding="utf-8"))
    assert yazilan["runtime"] == {"max_tokens": 99}
