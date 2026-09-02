"""Keşif, kabuk ve git araçları."""

from __future__ import annotations

import asyncio
import subprocess
import threading

import pytest

from fusion_cli.core.tools import Tool, ToolContext
from fusion_cli.tools import build_registry
from fusion_cli.tools import search as search_tools


@pytest.fixture
def context(tmp_path):
    return ToolContext(root=tmp_path)


@pytest.fixture
def registry():
    return build_registry()


async def _calistir(registry, context, ad, **args):
    return await registry.execute(ad, args, context)


async def test_search_code_eslesmeleri_dosya_satir_ile_dondurur(registry, context, tmp_path):
    (tmp_path / "a.py").write_text("def merhaba():\n    return 1\n", encoding="utf-8")

    cikti = (await _calistir(registry, context, "search_code", pattern="def ")).output

    assert "a.py:1:" in cikti and "def merhaba" in cikti


async def test_search_code_gurultu_dizinlerini_atlar(registry, context, tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("hedef", encoding="utf-8")
    (tmp_path / "kod.py").write_text("hedef", encoding="utf-8")

    cikti = (await _calistir(registry, context, "search_code", pattern="hedef")).output

    assert "kod.py" in cikti and "node_modules" not in cikti


async def test_search_code_sistem_cache_ve_vendor_koklerini_daha_taramadan_budar(
    registry, context, tmp_path
):
    noisy = tmp_path / "Library/Application Support/Google/Chrome/Cache"
    noisy.mkdir(parents=True)
    (noisy / "runaway.log").write_text("hedef", encoding="utf-8")
    vendor = tmp_path / "vendor/package"
    vendor.mkdir(parents=True)
    (vendor / "dependency.py").write_text("hedef", encoding="utf-8")
    (tmp_path / "project.py").write_text("hedef", encoding="utf-8")

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef")

    assert sonuc.ok
    assert "project.py" in sonuc.output
    assert "runaway.log" not in sonuc.output
    assert "dependency.py" not in sonuc.output


async def test_search_code_projedeki_library_kaynak_dizinini_gizlemez(
    registry, context, tmp_path
):
    source = tmp_path / "Library"
    source.mkdir()
    (source / "source.py").write_text("hedef", encoding="utf-8")

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef")

    assert sonuc.ok
    assert "Library/source.py" in sonuc.output


async def test_search_code_aday_sinirinda_kismi_sonuc_ve_daraltma_yolu_doner(
    registry, context, tmp_path, monkeypatch
):
    for index in range(5):
        (tmp_path / f"{index}.txt").write_text(
            "hedef" if index == 0 else "başka", encoding="utf-8"
        )
    monkeypatch.setattr(search_tools, "MAX_SEARCH_CANDIDATES", 2)

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef")

    assert not sonuc.ok
    assert "0.txt:1: hedef" in sonuc.output
    assert "2 dosya" in sonuc.output
    assert "'path' alanını" in sonuc.output


async def test_search_code_sure_sinirinda_opaque_timeout_yerine_kismi_hata_doner(
    registry, context, tmp_path, monkeypatch
):
    (tmp_path / "a.txt").write_text("hedef", encoding="utf-8")
    monkeypatch.setattr(search_tools, "SEARCH_DEADLINE_S", 0.0)

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef")

    assert not sonuc.ok
    assert "süre sınırına" in sonuc.output
    assert "'path' alanını" in sonuc.output


async def test_search_code_env_ve_sir_satirlarini_disari_vermez(registry, context, tmp_path):
    (tmp_path / ".env").write_text("API_TOKEN=sk-12345678901234567890\n", encoding="utf-8")
    (tmp_path / "config.py").write_text(
        "API_TOKEN=sk-12345678901234567890\nhedef\n", encoding="utf-8"
    )

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef|TOKEN")

    assert sonuc.ok
    assert ".env" not in sonuc.output
    assert "sk-12345678901234567890" not in sonuc.output
    assert "[gizlendi]" in sonuc.output


async def test_search_code_common_auth_files_and_json_tokens_are_excluded(
    registry, context, tmp_path
):
    for name in (".npmrc", "credentials.json", "token.json", "config.json"):
        (tmp_path / name).write_text(
            '{"access_token":"abcdefghijklmnopqrstuvwxyz123456","hedef":true}',
            encoding="utf-8",
        )
    (tmp_path / "source.py").write_text("hedef\n", encoding="utf-8")

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef")

    assert sonuc.ok and "source.py" in sonuc.output
    assert all(name not in sonuc.output for name in (".npmrc", "credentials.json", "token.json"))
    assert "abcdefghijklmnopqrstuvwxyz123456" not in sonuc.output


async def test_search_code_symlink_dosya_kok_disina_cikmaz(registry, context, tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("hedef dışarıda", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink oluşturulamıyor")

    sonuc = await _calistir(registry, context, "search_code", pattern="hedef")

    assert sonuc.ok and "outside-secret" not in sonuc.output


async def test_search_code_patolojik_regexi_dosya_okumadan_reddeder(
    registry, context, tmp_path
):
    (tmp_path / "large.txt").write_text("a" * 100_000, encoding="utf-8")

    sonuc = await _calistir(registry, context, "search_code", pattern="(a+)+$")

    assert not sonuc.ok
    assert "güvenli" in sonuc.output or "karmaşık" in sonuc.output


async def test_search_code_gercek_esleme_sirasinda_iptal_edilir_ve_sonraki_cagri_temizdir(
    registry, context, tmp_path, monkeypatch
):
    (tmp_path / "many.txt").write_text("hedef\n" + "başka\n" * 1000, encoding="utf-8")
    original = search_tools._matching_lines

    def cancel_after_first(path, regex, scan):
        for hit in original(path, regex, scan):
            yield hit
            scan.context.cancelled.set()

    monkeypatch.setattr(search_tools, "_matching_lines", cancel_after_first)
    sonuc = await _calistir(registry, context, "search_code", pattern="hedef")

    assert not sonuc.ok and "iptal edildi" in sonuc.output
    monkeypatch.undo()
    (tmp_path / "next.txt").write_text("hedef\n", encoding="utf-8")
    sonraki = await _calistir(registry, context, "search_code", pattern="hedef")
    assert sonraki.ok and "next.txt" in sonraki.output


async def test_iptal_edilen_sync_arac_isci_threadine_iptal_sinyali_verir(registry, context):
    started = threading.Event()
    stopped = threading.Event()

    def cancellable_search(_args, tool_context):
        started.set()
        while not tool_context.cancelled.wait(0.01):
            pass
        stopped.set()
        return search_tools.ToolResult("iptal edildi", ok=False)

    registry.register(
        Tool(
            name="cancellable_search",
            description="test",
            parameters={"type": "object", "properties": {}},
            run=cancellable_search,
        )
    )
    task = asyncio.create_task(_calistir(registry, context, "cancellable_search"))
    assert await asyncio.to_thread(started.wait, 1.0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await asyncio.to_thread(stopped.wait, 1.0)


async def test_iptal_sinyali_sonraki_arac_cagrisini_zehirlemez(
    registry, context, tmp_path
):
    started = threading.Event()

    def cancellable_search(_args, tool_context):
        started.set()
        tool_context.cancelled.wait(1.0)
        return search_tools.ToolResult("iptal edildi", ok=False)

    registry.register(
        Tool(
            name="cancellable_search_once",
            description="test",
            parameters={"type": "object", "properties": {}},
            run=cancellable_search,
        )
    )
    task = asyncio.create_task(_calistir(registry, context, "cancellable_search_once"))
    assert await asyncio.to_thread(started.wait, 1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    (tmp_path / "sonraki.txt").write_text("hedef", encoding="utf-8")
    sonuc = await _calistir(registry, context, "search_code", pattern="hedef")

    assert sonuc.ok
    assert "sonraki.txt" in sonuc.output


async def test_gecersiz_regex_anlasilir_hata_verir(registry, context):
    sonuc = await _calistir(registry, context, "search_code", pattern="[bozuk")

    assert not sonuc.ok and "Geçersiz regex" in sonuc.output


async def test_eslesme_yoksa_bilgilendirir(registry, context, tmp_path):
    (tmp_path / "a.py").write_text("bos", encoding="utf-8")

    assert (
        await _calistir(registry, context, "search_code", pattern="yok")
    ).output == "(eşleşme yok)"


async def test_glob_desene_uyan_dosyalari_bulur(registry, context, tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    (tmp_path / "alt").mkdir()
    (tmp_path / "alt" / "c.py").write_text("x", encoding="utf-8")

    cikti = (await _calistir(registry, context, "glob", pattern="**/*.py")).output

    assert "a.py" in cikti and "c.py" in cikti and "b.txt" not in cikti


async def test_glob_gurultu_dizinlerini_atlar(registry, context, tmp_path):
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text("x", encoding="utf-8")

    assert (
        await _calistir(registry, context, "glob", pattern="**/*.py")
    ).output == "(eşleşen dosya yok)"


async def test_run_shell_ciktiyi_ve_cikis_kodunu_dondurur(registry, context):
    sonuc = await _calistir(registry, context, "run_shell", command="echo merhaba")

    assert sonuc.ok and "merhaba" in sonuc.output and "çıkış kodu 0" in sonuc.output


async def test_run_shell_basarisiz_komutu_isaretler(registry, context):
    sonuc = await _calistir(registry, context, "run_shell", command="exit 3")

    assert not sonuc.ok and "çıkış kodu 3" in sonuc.output


async def test_run_shell_calisma_dizininde_calisir(registry, context, tmp_path):
    (tmp_path / "isaret.txt").write_text("x", encoding="utf-8")

    cikti = (await _calistir(registry, context, "run_shell", command="ls")).output

    assert "isaret.txt" in cikti


async def test_git_yalnizca_salt_okunur_komutlara_izin_verir(registry, context):
    sonuc = await _calistir(registry, context, "git", subcommand="push origin main")

    assert not sonuc.ok and "salt-okunur" in sonuc.output


async def test_git_bos_alt_komut_cokertmez(registry, context):
    # Boş/yalnızca-boşluk subcommand IndexError ile çökmemeli; anlaşılır hata dönmeli.
    sonuc = await _calistir(registry, context, "git", subcommand="   ")

    assert not sonuc.ok and "boş olmayan" in sonuc.output


async def test_git_status_calisir(registry, context, tmp_path):
    # Depo kurulumu bloklayan bir çağrı; olay döngüsünü tıkamaması için ayrı thread'de.
    await asyncio.to_thread(subprocess.run, ["git", "init", "-q"], cwd=tmp_path, check=True)

    sonuc = await _calistir(registry, context, "git", subcommand="status --short")

    assert sonuc.ok


async def test_bilinmeyen_arac_kullanilabilir_listeyi_gosterir(registry, context):
    sonuc = await registry.execute("olmayan_arac", {}, context)

    assert not sonuc.ok
    assert "Bilinmeyen araç" in sonuc.output and "read_file" in sonuc.output


async def test_executor_patlarsa_tur_dusmez(registry, context):
    """Araç sınırı: beklenmedik bir istisna turu düşürmez, modele iletilir."""
    from fusion_cli.core.tools import Tool

    def _patla(args, ctx):
        raise RuntimeError("beklenmedik")

    registry.register(Tool(name="patlayan", description="test", parameters={}, run=_patla))

    sonuc = await registry.execute("patlayan", {}, context)

    assert not sonuc.ok
    assert "beklenmedik hata" in sonuc.output and "RuntimeError" in sonuc.output


async def test_ayni_ad_iki_kez_kaydedilemez(registry):
    from fusion_cli.core.errors import FusionError
    from fusion_cli.core.tools import Tool

    with pytest.raises(FusionError, match="zaten kayıtlı"):
        registry.register(
            Tool(name="read_file", description="x", parameters={}, run=lambda a, c: None)
        )


async def test_takma_adlar_ayni_executoru_kullanir(registry, context, tmp_path):
    (tmp_path / "a.txt").write_text("icerik", encoding="utf-8")

    dogrudan = await registry.execute("read_file", {"path": "a.txt"}, context)
    takma = await registry.execute("view_file", {"path": "a.txt"}, context)

    assert dogrudan.output == takma.output


async def test_semalar_izin_listesiyle_filtrelenir(registry):
    semalar = registry.schemas(allowed={"read_file", "glob"})

    adlar = {sema["function"]["name"] for sema in semalar}
    assert adlar == {"read_file", "glob"}


async def test_semalar_function_calling_bicimindedir(registry):
    sema = next(s for s in registry.schemas() if s["function"]["name"] == "edit_file")

    assert sema["type"] == "function"
    assert sema["function"]["parameters"]["required"] == ["path", "old", "new"]


# --- zaman aşımı: kısmi çıktı KAYBEDİLMEZ ---------------------------------- #
#
# Gerçek koşuda model `npm run start:all` çalıştırdı — üç servisi birlikte ayağa
# kaldıran bir dev sunucusu. O komut hiç bitmez; 120 saniye beklendi ve tur iki
# dakika kaybetti. Daha kötüsü, dönen tek şey "zaman aşımı" idi: sunucunun
# "listening on :3000" çıktısı ATILDI. Model ne olduğunu anlamadı, komutun
# başarısız olduğunu sandı ve tekrar denemeye yöneldi.


async def test_zaman_asiminda_kismi_cikti_dondurulur(registry, context, monkeypatch):
    import subprocess

    from fusion_cli.tools import shell as shell_module

    def _patla(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd="npm run start:all",
            timeout=1.0,
            output="ready - started server on 0.0.0.0:3000",
            stderr="",
        )

    monkeypatch.setattr(shell_module.subprocess, "run", _patla)
    sonuc = await _calistir(registry, context, "run_shell", command="npm run start:all")

    assert sonuc.ok is False
    assert "0.0.0.0:3000" in sonuc.output, "kısmi çıktı kaybedildi"
    assert "aynı komutu tekrar çalıştırma" in sonuc.output.lower()


async def test_zaman_asiminda_cikti_yoksa_da_yol_gosterilir(registry, context, monkeypatch):
    import subprocess

    from fusion_cli.tools import shell as shell_module

    def _patla(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="sleep 999", timeout=1.0)

    monkeypatch.setattr(shell_module.subprocess, "run", _patla)
    sonuc = await _calistir(registry, context, "run_shell", command="sleep 999")

    assert sonuc.ok is False
    assert "çıktı üretmedi" in sonuc.output


# --- glob: mutlak desen ham istisna fırlatıyordu --------------------------- #
#
# Ölçüldü (canlı koşu): model `glob("/*")` çağırdı, `Path.glob` ham
# `NotImplementedError: Non-relative patterns are unsupported` fırlattı ve model
# ekranda Python istisnası gördü. Ne olduğunu ne yapacağını anlayamadı; tur
# "3 turdur ilerleme yok" ile öldü.


async def test_mutlak_glob_deseni_anlasilir_hata_verir(registry, context):
    sonuc = await _calistir(registry, context, "glob", pattern="/*")

    assert sonuc.ok is False
    assert "göreli" in sonuc.output.lower()
    assert "path" in sonuc.output


async def test_windows_mutlak_deseni_de_reddedilir(registry, context):
    sonuc = await _calistir(registry, context, "glob", pattern="C:/**/*.py")

    assert sonuc.ok is False


async def test_goreli_desen_calismaya_devam_eder(registry, context, tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")

    sonuc = await _calistir(registry, context, "glob", pattern="**/*.py")

    assert sonuc.ok is True
    assert "a.py" in sonuc.output


async def test_glob_sonuclari_proje_kokune_goreli(registry, context, tmp_path):
    """Mutlak yollar hem gürültü hem yanıltıcı; hata mesajlarıyla da tutarsızdı."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "page.tsx").write_text("x", encoding="utf-8")

    sonuc = await _calistir(registry, context, "glob", pattern="**/*.tsx")

    assert "app/page.tsx" in sonuc.output
    assert str(tmp_path) not in sonuc.output
