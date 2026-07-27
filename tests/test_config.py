"""Yapılandırma — birleştirme, doğrulama ve varsayılan tutarlılığı."""

from __future__ import annotations

import dataclasses

import pytest
import yaml

from fusion_cli.config.loader import load_config
from fusion_cli.config.models import RuntimeConfig
from fusion_cli.config.paths import bundled_defaults
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.types import ModelSpec

from .fakes import make_config


def _yaz(tmp_path, data):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_kullanici_dosyasi_yoksa_varsayilanlar_yuklenir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FUSION_CONFIG", raising=False)
    monkeypatch.delenv("FUSION_HOME", raising=False)

    config = load_config()

    assert config.source is None
    assert config.agent.model.startswith(("nvidia_nim/", "openrouter/"))


def test_kullanici_dosyasi_varsayilanin_uzerine_derin_birlestirilir(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"max_tokens": 99}})

    config = load_config(path)

    assert config.runtime.max_tokens == 99
    # Dokunulmayan alanlar varsayılandan gelir — bölüm tamamen değiştirilmez.
    assert config.runtime.temperature == 0.3
    assert config.source == path


def test_bilinmeyen_bolum_hata_verir(tmp_path):
    path = _yaz(tmp_path, {"bilinmeyen_bolum": {}})

    with pytest.raises(ConfigError, match="bilinmeyen anahtar"):
        load_config(path)


def test_bilinmeyen_alan_hata_verir(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"yanlis_alan": 1}})

    with pytest.raises(ConfigError, match="yanlis_alan"):
        load_config(path)


def test_yanlis_tip_hata_verir(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"max_tokens": "cok"}})

    with pytest.raises(ConfigError, match="tam sayı bekleniyordu"):
        load_config(path)


def test_boolean_tam_sayi_yerine_gecemez(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"max_tokens": True}})

    with pytest.raises(ConfigError, match="boolean"):
        load_config(path)


def test_liste_beklenen_yere_sayi_verilemez(tmp_path):
    """Tek METİN kabul edilir (bkz. eski biçim uyumu) ama sayı kabul edilmez."""
    path = _yaz(tmp_path, {"agent": {"fallback": 3}})

    with pytest.raises(ConfigError, match="liste bekleniyordu"):
        load_config(path)


def test_olmayan_dosya_anlasilir_hata_verir(tmp_path):
    with pytest.raises(ConfigError, match="bulunamadı"):
        load_config(tmp_path / "yok.yaml")


def test_bozuk_yaml_anlasilir_hata_verir(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("agent: [bozuk", encoding="utf-8")

    with pytest.raises(ConfigError, match="geçerli YAML değil"):
        load_config(path)


def test_varsayilanlar_dosyasi_tum_zorunlu_alanlari_icerir():
    """Kod ile dosya arasındaki varsayılan sapmasını imkânsız kılan koruma.

    Eski projede aynı varsayılan hem kodda hem YAML'da duruyordu ve zamanla ayrıştı.
    Artık varsayılanın tek kaynağı `defaults.yaml`; bir alan unutulursa bu test kırılır.
    """
    defaults = yaml.safe_load(bundled_defaults().read_text(encoding="utf-8"))

    for section, cls in (("agent", ModelSpec), ("runtime", RuntimeConfig)):
        zorunlu = {
            field.name
            for field in dataclasses.fields(cls)
            if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING
        }
        assert zorunlu <= set(defaults[section]), f"{section} bölümünde eksik alan var"


def test_models_birincil_ve_yedekleri_sirayla_tekilleştirir():
    spec = ModelSpec(name="a", model="m1", fallback=("m2", "m1", "m3"))

    assert spec.models == ("m1", "m2", "m3")


# --- Eski biçimle uyum --------------------------------------------------------- #


def test_tek_metin_yedek_liste_sayilir(tmp_path):
    """Önceki sürüm `fallback: str | list[str]` kabul ediyordu; kırılmamalı."""
    yol = tmp_path / "config.yaml"
    yol.write_text(
        "candidates:\n"
        "  - name: tek\n"
        "    model: saglayici/model\n"
        "    tags: [general]\n"
        "    fallback: saglayici/yedek\n"
        "task_model_map:\n"
        "  general: tek\n"
        "  code: tek\n"
        "  reasoning: tek\n"
        "  agent: tek\n",
        encoding="utf-8",
    )

    config = load_config(yol)

    assert config.candidates[0].fallback == ("saglayici/yedek",)


def test_tek_metin_etiket_de_liste_sayilir(tmp_path):
    yol = tmp_path / "config.yaml"
    yol.write_text("agent:\n  fallback: saglayici/yedek\n", encoding="utf-8")

    assert load_config(yol).agent.fallback == ("saglayici/yedek",)


def test_hata_mesaji_suclu_dosyayi_soyler(tmp_path):
    """Config birden çok yerde aranıyor; hangisinin bozuk olduğu yazmalı."""
    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  max_tokens: cok\n", encoding="utf-8")

    with pytest.raises(ConfigError) as hata:
        load_config(yol)

    assert str(yol) in str(hata.value)


def test_adi_degisen_ayar_eski_adiyla_da_calisir(tmp_path):
    """`agent_max_iterations` → `agent_max_steps`; yeniden adlandırma kullanıcıyı vurmamalı."""
    path = _yaz(tmp_path, {"runtime": {"agent_max_iterations": 42}})

    assert load_config(path).runtime.agent_max_steps == 42


def test_yeni_ad_yazilmissa_eski_ad_onu_ezmez(tmp_path):
    path = _yaz(tmp_path, {"runtime": {"agent_max_iterations": 42, "agent_max_steps": 7}})

    assert load_config(path).runtime.agent_max_steps == 7


def test_tasinmamis_ayar_sebebiyle_reddedilir(tmp_path):
    """Genel 'bilinmeyen anahtar' listesi yerine ne olduğunu söylemeli."""
    path = _yaz(tmp_path, {"runtime": {"live_input": True}})

    with pytest.raises(ConfigError, match="artık yok"):
        load_config(path)


# --- Agent rolü için görev tipine göre model seçimi -------------------------- #


def test_agent_modeli_gorev_tipine_gore_secilir():
    """`task_model_map` yalnızca fusion'a değil agent turuna da uygulanır."""
    from fusion_cli.config.model_select import select_agent_spec

    config = make_config(task_model_map={"code": "c"})

    secilen = select_agent_spec(config, "code")

    assert secilen.name == "c"


def test_haritada_karsiligi_yoksa_agent_rolu_kullanilir():
    from fusion_cli.config.model_select import select_agent_spec

    config = make_config(task_model_map={"code": "c"})

    assert select_agent_spec(config, "reasoning").name == config.agent.name


def test_haritadaki_ad_tanimsizsa_agent_rolune_dusulur():
    """Yapılandırmadaki yazım hatası turu çökertmemeli."""
    from fusion_cli.config.model_select import select_agent_spec

    config = make_config(task_model_map={"code": "boyle-bir-aday-yok"})

    assert select_agent_spec(config, "code").name == config.agent.name


def test_varsayilan_haritadaki_tum_adlar_tanimli_adaylardir():
    """Harita artık agent turunu da yönlendiriyor: yazım hatası sessizce kalite kaybı olur."""
    config = load_config()
    tanimli = {spec.name for spec in config.candidates}

    bilinmeyen = {tip: ad for tip, ad in config.task_model_map.items() if ad not in tanimli}

    assert not bilinmeyen, f"tanımlı aday olmayan adlar: {bilinmeyen}"


# --------------------------------------------------------------------------- #
# Model kademeleri
# --------------------------------------------------------------------------- #


def test_varsayilan_kademeler_yuklenir():
    config = load_config()

    assert [kademe.name for kademe in config.tiers] == [
        "low",
        "medium",
        "high",
        "ultra",
        "premium",
    ]


def test_her_kademe_rolunun_openrouter_yedegi_vardir():
    """NIM anahtarı olmayan kullanıcıda hiçbir rol boşta kalmamalıdır.

    Ürün ücretsiz LLM'lerle çalışmayı vaat ediyor ve OpenRouter anahtarı tek
    başına yeterli olmalı. Bir rolün zinciri yalnızca `nvidia_nim/` modellerden
    oluşursa o kademe NIM'siz kullanıcıda sessizce çöker — hata mesajı da
    "model yanıt vermedi" olur, sebebi görünmez.
    """
    config = load_config()

    yedeksiz = [
        (kademe.name, rol_adi, spec.models)
        for kademe in config.tiers
        for rol_adi, spec in [
            ("agent", kademe.agent),
            ("judge", kademe.judge),
            *[(f"aday:{aday.name}", aday) for aday in kademe.candidates],
        ]
        if not any(model.startswith("openrouter/") for model in spec.models)
    ]

    assert yedeksiz == []


def test_hicbir_kademede_ucretli_model_yoktur():
    """`/level` merdiveni kullanıcıya ASLA fatura çıkarmamalı.

    OpenRouter'da `:free` soneki olmayan her model ücretlidir. NIM modelleri
    ücretsiz geliştirici kotasından çalışır. Bir kademeye ücretli model sızarsa
    kullanıcı bunu ancak faturada fark ederdi — bu yüzden kural teste bağlıdır.
    """
    config = load_config()

    ucretli = [
        (kademe.name, model)
        for kademe in config.tiers
        for spec in (kademe.agent, kademe.judge, *kademe.candidates)
        for model in spec.models
        if model.startswith("openrouter/") and not model.endswith(":free")
    ]

    assert ucretli == [], f"kademelerde ücretli model var: {ucretli}"


def test_kademelerin_omurgasi_nim_modelleridir():
    """OpenRouter'ın ücretsiz kotası günde 50 istek; NIM'inki çok daha geniş.

    Her kademenin agent rolü NIM'den başlamalı ki günlük kota bir avuç turda
    tükenmesin. OpenRouter modelleri YEDEK olarak kalır — NIM anahtarı olmayan
    kullanıcı yine çalışır (bkz. `test_her_kademe_rolunun_openrouter_yedegi_vardir`).
    """
    config = load_config()

    nim_olmayan = [
        (kademe.name, kademe.agent.models[0])
        for kademe in config.tiers
        if not kademe.agent.models[0].startswith("nvidia_nim/")
    ]

    assert nim_olmayan == [], f"agent rolü NIM'den başlamayan kademeler: {nim_olmayan}"


def test_kademe_adiyla_bulunur_ve_buyuk_harf_duyarsizdir():
    config = load_config()

    assert config.tier_by_name("PREMIUM") is not None
    assert config.tier_by_name(" low ").name == "low"
    assert config.tier_by_name("boyle-bir-kademe-yok") is None


def test_kademe_uygulanınca_uc_rol_birden_degisir():
    from fusion_cli.config.model_select import apply_tier

    config = load_config()
    kademe = config.tier_by_name("premium")

    yeni = apply_tier(config, "premium")

    assert yeni.agent == kademe.agent
    assert yeni.judge == kademe.judge
    assert yeni.candidates == kademe.candidates


def test_kademe_uygulamak_config_i_mutasyona_ugratmaz():
    from fusion_cli.config.model_select import apply_tier

    config = load_config()
    onceki_agent = config.agent

    apply_tier(config, "premium")

    assert config.agent == onceki_agent


def test_kademe_gorev_haritasini_yeni_havuza_tasir():
    """Harita eski kademenin adlarını işaret ederse agent sessizce role düşerdi."""
    from fusion_cli.config.model_select import apply_tier

    config = load_config()

    yeni = apply_tier(config, "premium")

    tanimli = {spec.name for spec in yeni.candidates}
    assert set(yeni.task_model_map.values()) <= tanimli


def test_kademe_degisince_agent_turu_yeni_bas_modeli_calistirir():
    """Kademe seçmek agent turunu o kademenin BAŞ modeline bağlar.

    Regresyon: `nemotron-ultra` premium havuzunda da bulunduğu için, `ultra`'dan
    `premium`'a geçen kullanıcıda harita ona yapışıyordu; agent rolü `glm-5.2`
    olmasına rağmen agent turu `nemotron-ultra` çalıştırıyordu. Kademenin baş modeli
    (agent rolü) her görev tipi için koşulsuz seçilmeli.
    """
    from fusion_cli.config.model_select import apply_tier, select_agent_spec

    config = load_config()
    ustu = apply_tier(config, "ultra")

    premium = apply_tier(ustu, "premium")

    beklenen = premium.agent.name
    assert all(ad == beklenen for ad in premium.task_model_map.values())
    assert select_agent_spec(premium, "general").model == premium.agent.model


def test_yeniden_deneme_gecikmeleri_tanimli():
    """Gecikme listesi deneme sayısını da tanımlar; boş kalırsa yeniden deneme yok.

    Değerler NIM'in ölçülen sınırından gelir (60 saniyede 40 istek, MODEL BAŞINA):
    dakikalık pencereye takılan çağrı, pencere dönünce aynı modelde çalışır.
    """
    config = load_config()

    assert config.runtime.retry_delays_s, "yeniden deneme gecikmeleri tanımlı olmalı"
    assert all(delay > 0 for delay in config.runtime.retry_delays_s)


def test_gecikmeler_artan_sirada():
    """Geri çekilme artmalı: ikinci deneme birincilden daha uzun beklemeli.

    Azalan bir liste, sınır penceresi dönmeden ikinci kez sormak demektir — aynı
    429'u daha hızlı almaktan başka bir şey yapmaz.
    """
    gecikmeler = load_config().runtime.retry_delays_s

    assert list(gecikmeler) == sorted(gecikmeler)


def test_eski_pencere_ayari_anlasilir_hata_verir(tmp_path):
    """`hedge_delay_s` yazan eski config sessizce yok sayılmamalı.

    Kullanıcı bir ayar yaptığını sanıp beklentiye girmesin: zincir artık
    yarıştırılmıyor, o ayarın karşılığı kalmadı.
    """
    path = _yaz(tmp_path, {"runtime": {"hedge_delay_s": 2.5}})

    with pytest.raises(ConfigError, match="artık yok"):
        load_config(path)


def test_bilinmeyen_kademe_anlasilir_hata_verir():
    from fusion_cli.config.model_select import apply_tier

    with pytest.raises(ConfigError, match="kademe yok"):
        apply_tier(load_config(), "yok-boyle")


def test_kademe_adlari_benzersiz_olmali(tmp_path):
    config = load_config()
    ham = yaml.safe_load(bundled_defaults().read_text(encoding="utf-8"))
    ham["tiers"] = [ham["tiers"][0], ham["tiers"][0]]

    path = _yaz(tmp_path, {"tiers": ham["tiers"]})

    with pytest.raises(ConfigError, match="benzersiz"):
        load_config(path)
    assert config.tiers


def test_kademe_adi_kucuk_harf_olmali(tmp_path):
    ham = yaml.safe_load(bundled_defaults().read_text(encoding="utf-8"))
    kademe = dict(ham["tiers"][0])
    kademe["name"] = "LOW"

    path = _yaz(tmp_path, {"tiers": [kademe]})

    with pytest.raises(ConfigError, match="küçük harf"):
        load_config(path)


def test_kademe_listesi_bos_olamaz(tmp_path):
    path = _yaz(tmp_path, {"tiers": []})

    with pytest.raises(ConfigError, match="en az bir kademe"):
        load_config(path)


def test_her_kademede_en_az_bir_aday_vardir():
    config = load_config()

    for kademe in config.tiers:
        assert kademe.candidates, f"{kademe.name}: aday havuzu boş"


def test_kademe_modelleri_saglayici_onekiyle_yazilir():
    """Model kimliği `<sağlayıcı>/<model>` biçiminde olmalı; yoksa çağrı yönlenemez."""
    config = load_config()

    for kademe in config.tiers:
        for spec in (kademe.agent, kademe.judge, *kademe.candidates):
            assert "/" in spec.model, f"{kademe.name}: {spec.model}"


# --- .env yükleme sırası ----------------------------------------------------- #


def test_bos_env_satiri_gercek_anahtari_golgelemez(tmp_path, monkeypatch):
    """Boş bir anahtar satırı, sonraki dosyadaki gerçek anahtarı ezmemeli.

    Gerçek hata: `setup.sh` proje köküne boş anahtarlı bir `.env` bırakıyordu.
    O dosya önce yüklendiği ve `load_dotenv` boş string'i de bir DEĞER saydığı
    için, kullanıcının `~/.config/fusion-cli/.env` içine girdiği gerçek anahtar
    hiçbir zaman devreye girmiyordu — kurulum "tamam" diyor, ürün çalışmıyordu.
    """
    from fusion_cli.config import loader

    once = tmp_path / "proje" / ".env"
    sonra = tmp_path / "kullanici" / ".env"
    once.parent.mkdir()
    sonra.parent.mkdir()
    once.write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
    sonra.write_text("OPENROUTER_API_KEY=sk-gercek\n", encoding="utf-8")

    monkeypatch.setattr(loader, "env_file_candidates", lambda: (once, sonra))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    loader.load_environment()

    import os

    assert os.environ.get("OPENROUTER_API_KEY") == "sk-gercek"


def test_ortamda_var_olan_anahtar_env_dosyasiyla_ezilmez(tmp_path, monkeypatch):
    """Kabuğa elle verilen anahtar dosyadan daha önceliklidir."""
    from fusion_cli.config import loader

    dosya = tmp_path / ".env"
    dosya.write_text("OPENROUTER_API_KEY=sk-dosyadan\n", encoding="utf-8")

    monkeypatch.setattr(loader, "env_file_candidates", lambda: (dosya,))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-kabuktan")

    loader.load_environment()

    import os

    assert os.environ.get("OPENROUTER_API_KEY") == "sk-kabuktan"


def test_her_rol_her_saglayici_tercihinde_yedekli_kalir():
    """Tercih uygulanınca hiçbir rol TEK MODELLİ kalmamalı.

    Ölçüldü (2026-07-26): NVIDIA NIM'in hız sınırı MODEL BAŞINADIR, hesap başına
    değil — aynı anahtarla aynı saniyede `nemotron-super` 429 verirken dört başka
    NIM modeli çalışıyordu. Dolayısıyla tek modelli bir rol, o model kısıtlanınca
    tamamen ölür ve kullanıcı "kotam bitti" sanır.

    Zincirlerde AYNI sağlayıcıdan alternatif bulunmalı ki `/provider` ile tek
    sağlayıcıya kilitlenen kullanıcı da yedeksiz kalmasın.
    """
    from fusion_cli.config.keys import ProviderPreference, apply_preference

    config = load_config()

    yedeksiz = []
    for tercih in (ProviderPreference.NVIDIA, ProviderPreference.OPENROUTER):
        secilmis = apply_preference(config, tercih)
        # ÜST DÜZEY roller de denetlenir: kademe seçilmemişken kullanılan onlardır.
        # Test önce yalnızca kademelere bakıyordu ve gerçek akış kırıkken yeşil
        # veriyordu — canlı koşuda agent tek modelle 429 alıp turu bitirdi.
        # Agent ve hakem denetlenir. ADAYLAR bilinçli olarak DIŞARIDA: fusion
        # motoru `min_successful_candidates` ile aday kaybını tolere eder, bir aday
        # 429 alsa da tur yaşar. Agent ve hakem ise tekildir; onlar düşerse tur
        # ölür. Agent'ın `task_model_map` üzerinden gelen zinciri ayrıca
        # `test_gorev_tipi_yonlendirmesi_yedek_zinciri_dusurmez` ile korunur.
        gruplar = [("varsayılan", secilmis.agent, secilmis.judge)]
        gruplar += [(k.name, k.agent, k.judge) for k in secilmis.tiers]
        for grup_adi, agent, hakem in gruplar:
            for rol_adi, spec in (("agent", agent), ("hakem", hakem)):
                if len(spec.models) < 2:
                    yedeksiz.append(f"{tercih.value}/{grup_adi}/{rol_adi}")

    assert yedeksiz == [], f"tek modelli roller: {yedeksiz}"


def test_gorev_tipi_yonlendirmesi_yedek_zinciri_dusurmez():
    """`task_model_map` agent rolünü bir adaya yönlendirdiğinde YEDEK KAYBOLMAMALI.

    Gerçek hata (canlı koşuda görüldü): `agent:` rolüne yedek zinciri yazılmıştı
    ama tur `task_model_map` üzerinden ADAY spec'ini kullanıyor ve adayların
    yedeği yok. Model 429 alınca tur bitiyordu — kullanıcı "kotam bitti" sanıyor,
    oysa NIM'de sınır model başınadır ve başka bir model çalışıyor.

    Yönlendirme birincil modeli DEĞİŞTİRİR; dayanıklılığı düşürmemeli.
    """
    from fusion_cli.config.keys import ProviderPreference, apply_preference
    from fusion_cli.config.model_select import select_agent_spec

    config = load_config()

    yedeksiz = []
    # Tercihler de denetlenir: `auto` kipte zincir iki sağlayıcıya yayıldığı için
    # sorun görünmüyordu, tek sağlayıcıya kilitlenince ortaya çıkıyordu.
    for tercih in (
        ProviderPreference.AUTO,
        ProviderPreference.NVIDIA,
        ProviderPreference.OPENROUTER,
    ):
        secilmis = apply_preference(config, tercih)
        for task_type in secilmis.task_model_map:
            secilen = select_agent_spec(secilmis, task_type)
            if len(secilen.models) < 2:
                yedeksiz.append(f"{tercih.value}/{task_type}: {secilen.models}")

    assert yedeksiz == [], f"yedeksiz agent zincirleri: {yedeksiz}"
