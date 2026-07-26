"""Agent yardımcı katmanları: geçmiş, refleksiyon sezgiseli, denetim, sıkıştırma."""

from __future__ import annotations

from fusion_cli.core.types import Message, ModelResult, ToolCall
from fusion_cli.engines.agent import compaction, history, reflexion, review

from .fakes import make_config


def _mesajlar():
    return [
        Message("system", "sistem"),
        Message("user", "ilk gorev"),
        Message("assistant", "", tool_calls=(ToolCall("1", "read_file", '{"path":"a"}'),)),
        Message("tool", "icerik", tool_call_id="1", name="read_file", ok=True),
        Message("assistant", "bitti"),
        Message("user", "ikinci gorev"),
        Message("assistant", "tamam"),
    ]


# --- Geçmiş ----------------------------------------------------------------- #


def test_kesme_noktasi_user_sinirina_kaydirilir():
    """Araç çağrısı ile sonucu asla ayrılmamalı; aksi halde sağlayıcı hata verir."""
    mesajlar = _mesajlar()

    kesim = history.safe_cut(mesajlar, keep_recent=5)

    assert mesajlar[kesim].role == "user"


def test_guvenli_kesim_yoksa_sifir_doner():
    mesajlar = [Message("assistant", "a"), Message("tool", "b", tool_call_id="1")]

    assert history.safe_cut(mesajlar, keep_recent=1) == 0


def test_esik_altinda_sikistirma_gerekmez():
    assert not history.needs_compression([Message("user", "kisa")])


def test_esik_ustunde_sikistirma_gerekir():
    buyuk = [Message("user", "x" * (history.COMPRESS_THRESHOLD_CHARS + 1))]

    assert history.needs_compression(buyuk)


def test_siradan_kodlama_oturumu_sikistirmaya_takilmaz():
    """Birkaç dosya okuyan normal bir tur, geçmişini kaybetmemeli.

    Eski eşik (24.000 karakter ≈ 6k token) modelin bağlam penceresinin %1'inden azdı:
    agent üç beş dosya okur okumaz geçmişi 600 token'lık bir özete iniyor, az önce
    okuduğu dosyayı unutup uydurmaya başlıyordu.
    """
    oturum = [Message("user", "şu hatayı düzelt")]
    for sira in range(5):
        oturum.append(Message("assistant", "", tool_calls=(_arac_cagrisi(str(sira)),)))
        # 8 KB ≈ 200 satırlık sıradan bir kaynak dosya.
        oturum.append(Message("tool", "k" * 8_000, tool_call_id=str(sira), name="read_file"))

    assert not history.needs_compression(oturum)


def test_korunan_mesaj_sayisi_birkac_arac_turunu_kapsar():
    """Bir araç turu 2 mesajdır (çağrı + sonuç); 6 mesaj yalnızca 3 tura yeterdi."""
    assert history.KEEP_RECENT_MESSAGES >= 16


def _arac_cagrisi(kimlik: str) -> ToolCall:
    return ToolCall(id=kimlik, name="read_file", arguments="{}")


def test_iz_arac_cagrilarini_ve_sonuclarini_korur():
    iz = history.transcript(_mesajlar())

    assert "[araç çağrısı] read_file" in iz
    assert "[sonuç read_file]" in iz
    assert "[kullanıcı] ilk gorev" in iz


def test_iz_hatali_sonuclari_isaretler():
    iz = history.transcript([Message("tool", "Dosya yok: a.txt", name="read_file", ok=False)])

    assert "⟵ HATA" in iz


# --- Yarım kalma sezgiseli --------------------------------------------------- #


def test_tamamlanmamis_todo_isi_yarim_yapar():
    assert reflexion.looks_unfinished("bitti", tool_calls_last_turn=0, has_pending_todos=True)


def test_arac_sonrasi_kisa_cevap_yarim_sayilir():
    assert reflexion.looks_unfinished("bak", tool_calls_last_turn=2, has_pending_todos=False)


def test_kod_iceren_kisa_cevap_yarim_sayilmaz():
    assert not reflexion.looks_unfinished(
        "`x = 1`", tool_calls_last_turn=2, has_pending_todos=False
    )


def test_uzun_cevap_yarim_sayilmaz():
    assert not reflexion.looks_unfinished(
        "u" * 100, tool_calls_last_turn=2, has_pending_todos=False
    )


def test_arac_cagrilmadiysa_kisa_cevap_yarim_sayilmaz():
    assert not reflexion.looks_unfinished("evet", tool_calls_last_turn=0, has_pending_todos=False)


def test_israrci_not_farkli_metin_kullanir():
    assert reflexion.note(persistent=True).content != reflexion.note(persistent=False).content


# --- Öz-denetim çıktısı ------------------------------------------------------ #


def test_tamam_cevabi_sorun_yok_demektir():
    assert review.parse_feedback("TAMAM") == ""


def test_tamam_ile_baslayan_cevap_da_temiz_sayilir():
    assert review.parse_feedback("TAMAM, her şey yolunda.") == ""


def test_bos_cevap_temiz_sayilir():
    assert review.parse_feedback("   ") == ""


def test_cok_kisa_cevap_talimat_sayilmaz():
    assert review.parse_feedback("hmm") == ""


def test_somut_talimat_dondurulur():
    talimat = "Testleri çalıştırmadın, önce pytest koş."

    assert review.parse_feedback(talimat) == talimat


# --- Sıkıştırma -------------------------------------------------------------- #


async def test_esik_altinda_gecmise_dokunulmaz():
    mesajlar = [Message("user", "kisa")]

    assert await compaction.compress(mesajlar, config=make_config()) is mesajlar


async def test_ozet_uretilemezse_gecmis_degismez(monkeypatch):
    async def _bos(trace, config, publisher):
        return ""

    monkeypatch.setattr(compaction, "_summarize", _bos)
    mesajlar = [
        Message("user", "x" * 30_000),
        Message("assistant", "a"),
        Message("user", "b"),
        Message("assistant", "c"),
        Message("user", "d"),
        Message("assistant", "e"),
        Message("user", "f"),
    ]

    assert await compaction.compress(mesajlar, config=make_config()) == mesajlar


async def test_ozet_uretilirse_eski_turlar_tek_nota_iner(monkeypatch):
    async def _ozet(trace, config, publisher):
        return "kisa ozet"

    monkeypatch.setattr(compaction, "_summarize", _ozet)
    # Eşiği ve korunan mesaj sayısını sabitten türet: değerler ayarlandığında test
    # yanlış sebeple kırılmasın.
    mesajlar = [Message("user", "x" * (history.COMPRESS_THRESHOLD_CHARS + 1))] + [
        Message("user" if i % 2 == 0 else "assistant", f"m{i}")
        for i in range(history.KEEP_RECENT_MESSAGES + 2)
    ]

    sonuc = await compaction.compress(mesajlar, config=make_config())

    assert len(sonuc) < len(mesajlar)
    assert sonuc[0].content.startswith("[önceki konuşmanın özeti]")


def test_dosya_satir_referansi_somut_teslim_sayilir():
    """Kısa ama tam bir cevap ("src/app.py:42") yarım sanılıp tekrarlatılmamalı."""
    assert not reflexion.looks_unfinished(
        "src/fusion_cli/observability/bus.py:24",
        tool_calls_last_turn=2,
        has_pending_todos=False,
    )


def test_dosya_yolu_iceren_kisa_cevap_somut_sayilir():
    assert not reflexion.looks_unfinished(
        "Tanım src/core/events.py dosyasında.",
        tool_calls_last_turn=1,
        has_pending_todos=False,
    )


def test_somut_isaret_tasimayan_kisa_cevap_hala_yarim():
    assert reflexion.looks_unfinished("bakiyorum", tool_calls_last_turn=1, has_pending_todos=False)


def test_iz_sinira_dayaninca_en_son_adimlari_korur():
    """Denetçi işin sonucunu görmeli; başlangıçtaki keşif çağrılarını değil.

    Gerçek bir hatanın izi: 60 adımlık bir turda denetçiye yalnızca ilk 10 adım
    gidiyordu. Denetçi üretilen tek bir dosyayı bile görmeden "TAMAM" diyordu.
    """
    mesajlar = [Message("user", "görev")]
    for sira in range(60):
        mesajlar.append(Message("tool", f"ADIM-{sira:02d} " + "dolgu " * 40, name="write_file"))

    iz = history.transcript(mesajlar, limit=3_000)

    assert "ADIM-59" in iz, "son adım denetçiye ulaşmalı"
    assert "ADIM-00" not in iz, "sınır aşıldığında eski adımlar atılmalı"


def test_iz_atlanan_kismi_acikca_bildirir():
    """Denetçi eksik bilgiyle çalıştığını bilmeli; tam sanmamalı."""
    mesajlar = [Message("tool", f"ADIM-{s:02d} " + "dolgu " * 40, name="w") for s in range(60)]

    iz = history.transcript(mesajlar, limit=3_000)

    assert "atlandı" in iz.lower()


def test_iz_sinira_sigiyorsa_oldugu_gibi_kalir():
    mesajlar = [Message("user", "kısa görev")]

    iz = history.transcript(mesajlar, limit=3_000)

    assert "atlandı" not in iz.lower()
    assert "kısa görev" in iz


async def test_denetci_uzun_turda_son_isi_gorur(monkeypatch):
    """Denetçiye giden iz, üretilen dosyaları kapsayacak kadar geniş olmalı."""
    yakalanan: dict[str, str] = {}

    async def _sor(prompt, config, publisher):
        yakalanan["prompt"] = prompt
        return ModelResult(name="h", model="m", text="TAMAM", latency_ms=1, ok=True)

    monkeypatch.setattr(review, "_ask", _sor)
    mesajlar = [Message("user", "site yap")]
    for sira in range(60):
        mesajlar.append(
            Message("tool", f"ADIM-{sira:02d} " + "dolgu " * 40, name="write_file", ok=True)
        )

    await review.review_turn("site yap", "bitti", mesajlar, config=make_config())

    assert "ADIM-59" in yakalanan["prompt"], "denetçi turun sonucunu görmeli"
    assert "ADIM-40" in yakalanan["prompt"], "denetçi yalnızca son bir iki adımı değil"


async def test_yarim_kalan_denetim_talimati_uygulanmaz(monkeypatch):
    """Kelime ortasında kesilmiş bir talimat, hiç talimattan kötüdür."""

    async def _kesik(prompt, config, publisher):
        return ModelResult(
            name="h", model="m", text="CSS dosyas", latency_ms=1, ok=True, truncated=True
        )

    monkeypatch.setattr(review, "_ask", _kesik)

    geri = await review.review_turn("görev", "bitti", [Message("user", "x")], config=make_config())

    assert geri == ""


# --- Alt-ajan değişiklikleri ana kapıya girer -------------------------------- #


def test_alt_ajan_baglami_touched_kumesini_paylasir():
    """Alt-ajanın yazdığı dosya ana doğrulama kapısından KAÇMAMALI.

    Gerçek boşluk: alt-ajan kendi ToolContext'iyle çalışıyordu, `depth>0` olduğu
    için kendi kapısı hiç kurulmuyordu ve yazdığı dosya ana bağlamın `touched`
    kümesine girmediği için ana kapı da onu görmüyordu. Dosya iki kapı arasından
    sızıyordu.

    Görev listesi ayrı kalır (alt-ajan ana listeyi ezmemeli); paylaşılan tek şey
    değişiklik kümesidir.
    """
    from pathlib import Path

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.engine_tools import derive_sub_context

    ana = ToolContext(root=Path("/proje"), extra_roots=(Path("/paylasilan"),))
    alt = derive_sub_context(ana)

    alt.touched.add(Path("/proje/index.html"))

    assert Path("/proje/index.html") in ana.touched, "değişiklik ana kapıya görünmeli"
    assert alt.todos is not ana.todos, "görev listesi ayrı kalmalı"
    assert alt.extra_roots == ana.extra_roots, "izin sınırı alt-ajanda gevşememeli"
    assert alt.restrict_to_root == ana.restrict_to_root
