"""Belleğin saf katmanları: parçalama, ders ayrıştırma, prompt bloğu, puanlama."""

from __future__ import annotations

from fusion_cli.core.memory import Feedback, Lesson, LessonKind, LessonSource
from fusion_cli.engines.agent.learning import parse_lessons
from fusion_cli.memory.chunking import CHUNK_LINES, build_chunks, chunk_file, iter_source_files
from fusion_cli.memory.lessons import as_prompt_block
from fusion_cli.memory.performance import _adjusted_score
from fusion_cli.memory.seed import SEED_LESSONS

# --- Parçalama --------------------------------------------------------------- #


def test_parca_kimligi_icerige_bagli(tmp_path):
    """Artımlı indekslemenin temeli: içerik değişmediyse kimlik de değişmemeli."""
    dosya = tmp_path / "a.py"
    dosya.write_text("x = 1\n", encoding="utf-8")

    ilk = chunk_file(dosya, tmp_path)[0].id
    dosya.write_text("x = 1\n", encoding="utf-8")
    ikinci = chunk_file(dosya, tmp_path)[0].id

    assert ilk == ikinci


def test_icerik_degisince_kimlik_degisir(tmp_path):
    dosya = tmp_path / "a.py"
    dosya.write_text("x = 1\n", encoding="utf-8")
    ilk = chunk_file(dosya, tmp_path)[0].id

    dosya.write_text("x = 2\n", encoding="utf-8")

    assert chunk_file(dosya, tmp_path)[0].id != ilk


def test_uzun_dosya_ortusen_parcalara_bolunur(tmp_path):
    dosya = tmp_path / "uzun.py"
    dosya.write_text("\n".join(f"satir{i}" for i in range(150)), encoding="utf-8")

    parcalar = chunk_file(dosya, tmp_path)

    assert len(parcalar) > 1
    # Örtüşme: ikinci parça birincinin bittiği yerden ÖNCE başlar.
    assert parcalar[1].start_line < parcalar[0].end_line
    assert all(p.end_line - p.start_line < CHUNK_LINES for p in parcalar)


def test_bos_dosya_parca_uretmez(tmp_path):
    (tmp_path / "bos.py").write_text("", encoding="utf-8")

    assert chunk_file(tmp_path / "bos.py", tmp_path) == []


def test_yol_koke_gore_kaydedilir(tmp_path):
    (tmp_path / "alt").mkdir()
    dosya = tmp_path / "alt" / "a.py"
    dosya.write_text("x = 1", encoding="utf-8")

    assert chunk_file(dosya, tmp_path)[0].path == "alt/a.py"


def test_gurultu_dizinleri_indekslenmez(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("kod", encoding="utf-8")
    (tmp_path / "kod.py").write_text("kod", encoding="utf-8")

    yollar = {p.name for p in iter_source_files(tmp_path)}

    assert yollar == {"kod.py"}


def test_desteklenmeyen_uzanti_atlanir(tmp_path):
    (tmp_path / "resim.png").write_bytes(b"\x89PNG")
    (tmp_path / "kod.py").write_text("x", encoding="utf-8")

    assert {p.name for p in iter_source_files(tmp_path)} == {"kod.py"}


def test_parca_ust_siniri_asilmaz(tmp_path):
    for i in range(5):
        (tmp_path / f"d{i}.py").write_text("\n".join(str(n) for n in range(200)), encoding="utf-8")

    assert len(build_chunks(tmp_path, limit=3)) == 3


# --- Ders ayrıştırma --------------------------------------------------------- #


def test_gecerli_json_derse_cevrilir():
    dersler = parse_lessons(
        '[{"kind":"mistake","lesson":"kor edit yapma"},{"kind":"success","lesson":"once oku"}]',
        "gorev",
    )

    assert len(dersler) == 2
    assert dersler[0].kind is LessonKind.MISTAKE
    assert dersler[0].source is LessonSource.LEARNED
    assert dersler[0].task == "gorev"


def test_aciklama_arasindaki_json_bulunur():
    dersler = parse_lessons('Iste dersler: [{"kind":"success","lesson":"x"}] umarim olur.', "g")

    assert len(dersler) == 1


def test_bozuk_json_ders_uretmez():
    assert parse_lessons("[bu json degil", "g") == ()


def test_json_olmayan_cikti_ders_uretmez():
    assert parse_lessons("hicbir ders cikmadi", "g") == ()


def test_bilinmeyen_tur_atilir():
    assert parse_lessons('[{"kind":"belirsiz","lesson":"x"}]', "g") == ()


def test_bos_ders_metni_atilir():
    assert parse_lessons('[{"kind":"success","lesson":"   "}]', "g") == ()


def test_ders_sayisi_sinirlanir():
    coklu = ",".join(f'{{"kind":"success","lesson":"ders{i}"}}' for i in range(10))

    assert len(parse_lessons(f"[{coklu}]", "g")) == 3


# --- Prompt bloğu ------------------------------------------------------------ #


def test_bos_ders_listesi_blok_uretmez():
    assert as_prompt_block(()) == ""


def test_prompt_blogu_tur_etiketi_tasir():
    blok = as_prompt_block(
        (
            Lesson(text="kor edit yapma", kind=LessonKind.MISTAKE),
            Lesson(text="once oku", kind=LessonKind.SUCCESS),
        )
    )

    assert "[KAÇIN] kor edit yapma" in blok
    assert "[UYGULA] once oku" in blok
    assert blok.startswith("<dersler>")


# --- Puanlama ---------------------------------------------------------------- #


def test_esit_puanda_hizli_model_kazanir():
    hizli = _adjusted_score([0.9], [1_000])
    yavas = _adjusted_score([0.9], [50_000])

    assert hizli > yavas


def test_gecikme_cezasi_kaliteyi_ezmez():
    """Ceza 0.1 ile sınırlı: çok yavaş ama çok iyi model, hızlı ve kötüyü yenmeli."""
    yavas_iyi = _adjusted_score([0.95], [600_000])
    hizli_kotu = _adjusted_score([0.80], [1])

    assert yavas_iyi > hizli_kotu


def test_geri_bildirim_deltalari():
    assert Feedback.GOOD.delta > 0
    assert Feedback.BAD.delta < 0
    assert Feedback.REVISE.delta < Feedback.BAD.delta


# --- Seed dersler ------------------------------------------------------------ #


def test_seed_dersleri_seed_kaynakli():
    assert all(lesson.source is LessonSource.SEED for lesson in SEED_LESSONS)


def test_seed_dersleri_benzersiz():
    metinler = [lesson.text for lesson in SEED_LESSONS]

    assert len(metinler) == len(set(metinler))


def test_seed_dersleri_hem_hata_hem_basari_icerir():
    turler = {lesson.kind for lesson in SEED_LESSONS}

    assert turler == {LessonKind.MISTAKE, LessonKind.SUCCESS}


# --- Dersler talimat değil ÖNERİDİR ----------------------------------------- #


def test_dersler_emir_kipiyle_dayatilmaz():
    """Ders bloğu "bunlara uy" demez.

    Dersler yerel olarak, agent'ın kendi turlarından çıkarılır; hiçbiri kullanıcı
    talimatı ya da güvenlik politikası kadar yetkili değildir. Emir kipiyle
    enjekte edilince model onları sistem kuralı gibi okuyor.
    """
    from fusion_cli.core.memory import Lesson, LessonKind

    blok = as_prompt_block((Lesson(text="testleri çalıştır", kind=LessonKind.SUCCESS),))

    assert "bunlara uy" not in blok.lower()


def test_ders_blogu_ustunluk_sinirini_yazar():
    """Bir ders güvenlik kararını, izin akışını ya da kullanıcı talimatını ezemez.

    Faz B ile kök kısıtlaması, kabuk beyaz listesi ve onay akışı geldi. "Onay
    istemene gerek yok" gibi bir ders talimat olarak enjekte edilirse bu kararların
    önüne geçebilir; sınır promptta AÇIKÇA yazılır.
    """
    from fusion_cli.core.memory import Lesson, LessonKind

    # Küçültme YOK: Türkçe'de "İ".lower() birleşik noktalı "i̇" üretir ve
    # metinde arama yanlış sonuç verir. Blok olduğu gibi denetlenir.
    blok = as_prompt_block((Lesson(text="onay isteme", kind=LessonKind.SUCCESS),))

    assert "güvenlik" in blok
    assert "kullanıcının talimatını" in blok
    assert "GEÇERSİZ KILAMAZ" in blok
    assert "ÖNERİDİR" in blok


def test_bos_ders_listesinde_uyari_da_basilmaz():
    """Ders yokken boş bir uyarı bloğu prompt bütçesi harcamamalı."""
    assert as_prompt_block(()) == ""
