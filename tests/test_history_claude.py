"""Claude Code JSONL okuyucusu."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fusion_cli.history.claude_source import ClaudeSource, slug_for


def _oturum_yaz(
    home: Path, slug: str, session_id: str, kayitlar: list[dict], mtime: float | None = None
) -> Path:
    hedef = home / ".claude" / "projects" / slug
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / f"{session_id}.jsonl"
    yol.write_text("\n".join(json.dumps(k) for k in kayitlar), encoding="utf-8")
    if mtime is not None:
        os.utime(yol, (mtime, mtime))
    return yol


def test_slug_yol_ayraclarini_tireye_cevirir():
    assert slug_for(Path("/Users/x/Desktop/proje")) == "-Users-x-Desktop-proje"


def test_iz_yoksa_kurulu_degil(tmp_path):
    assert ClaudeSource(tmp_path).is_installed() is False


def test_iz_varsa_kurulu(tmp_path):
    (tmp_path / ".claude" / "projects").mkdir(parents=True)

    assert ClaudeSource(tmp_path).is_installed() is True


def test_ai_title_varsa_baslik_odur(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s1",
        [
            {"type": "user", "message": {"role": "user", "content": "ilk soru"}},
            {"type": "ai-title", "aiTitle": "Gerçek Başlık", "sessionId": "s1"},
        ],
    )

    (ref,) = ClaudeSource(tmp_path).list()

    assert ref.title == "Gerçek Başlık"
    assert ref.source == "claude"


def test_ai_title_yoksa_ilk_kullanici_mesaji_baslik_olur(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s2",
        [{"type": "user", "message": {"role": "user", "content": "düşmanlar ölmüyor"}}],
    )

    (ref,) = ClaudeSource(tmp_path).list()

    assert ref.title == "düşmanlar ölmüyor"


def test_bozuk_satir_oturumu_dusurmez(tmp_path):
    yol = _oturum_yaz(
        tmp_path,
        "-p",
        "s3",
        [{"type": "user", "message": {"role": "user", "content": "sağlam"}}],
    )
    with yol.open("a", encoding="utf-8") as fh:
        fh.write("\n{bozuk json")

    (ref,) = ClaudeSource(tmp_path).list()

    assert ref.session_id == "s3"


def test_parca_listesi_iceren_mesaj_duz_metne_cevrilir(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s4",
        [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "parça bir"}],
                },
            }
        ],
    )

    (turn,) = ClaudeSource(tmp_path).read("s4")

    assert turn.text == "parça bir"


def test_imlec_ve_limit_uygulanir(tmp_path):
    kayitlar = [{"type": "user", "message": {"role": "user", "content": f"m{i}"}} for i in range(5)]
    _oturum_yaz(tmp_path, "-p", "s5", kayitlar)

    turlar = ClaudeSource(tmp_path).read("s5", cursor=1, limit=2)

    assert [t.text for t in turlar] == ["m1", "m2"]


def test_meta_ve_sidechain_kayitlari_atlanir(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s6",
        [
            {"type": "user", "isMeta": True, "message": {"role": "user", "content": "meta"}},
            {"type": "user", "message": {"role": "user", "content": "gerçek"}},
        ],
    )

    turlar = ClaudeSource(tmp_path).read("s6")

    assert [t.text for t in turlar] == ["gerçek"]


def test_message_null_olan_kayit_oturumu_dusurmez(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s7",
        [
            {"type": "user", "message": None},
            {"type": "user", "message": {"role": "user", "content": "hâlâ okunur"}},
        ],
    )

    (ref,) = ClaudeSource(tmp_path).list()

    assert ref.session_id == "s7"
    assert ref.title == "hâlâ okunur"

    turlar = ClaudeSource(tmp_path).read("s7")
    assert [t.text for t in turlar] == ["hâlâ okunur"]


def test_message_duz_metin_olan_kayit_atlanir(tmp_path):
    _oturum_yaz(
        tmp_path,
        "-p",
        "s8",
        [
            {"type": "user", "message": "sadece bir dizge"},
            {"type": "user", "message": {"role": "user", "content": "asıl mesaj"}},
        ],
    )

    (ref,) = ClaudeSource(tmp_path).list()

    assert ref.session_id == "s8"
    assert ref.title == "asıl mesaj"

    turlar = ClaudeSource(tmp_path).read("s8")
    assert [t.text for t in turlar] == ["asıl mesaj"]


def test_limit_verildiginde_yalnizca_gereken_kadar_dosya_ayristirilir(tmp_path, monkeypatch):
    """`limit` verildiğinde `_read_ref` (yani asıl JSONL ayrıştırması) yalnızca
    döndürülecek oturum sayısı kadar çağrılmalı — 10 oturum olsa da limit=3 ile
    çağrıldığında 3'ten fazla dosya AÇILMAMALI.

    Bu, ölçülen gerçek sorunu (106 oturum, 264 MB'ın hepsinin ayrıştırılması)
    davranışsal olarak kanıtlar: sayaç, sıralamanın içerik okunmadan `stat()`
    üzerinden yapıldığını ve ayrıştırmanın yalnızca seçilen adaylara
    uygulandığını gösterir.
    """
    for i in range(10):
        _oturum_yaz(
            tmp_path,
            "-p",
            f"s{i}",
            [{"type": "user", "message": {"role": "user", "content": f"m{i}"}}],
            mtime=1000 + i,
        )

    source = ClaudeSource(tmp_path)
    call_count = 0
    original_read_ref = source._read_ref

    def _sayilan_read_ref(path):
        nonlocal call_count
        call_count += 1
        return original_read_ref(path)

    monkeypatch.setattr(source, "_read_ref", _sayilan_read_ref)

    refs = source.list(limit=3)

    assert call_count == 3
    # En yeni 3 oturum (s9, s8, s7) döner — mtime 1000+i ile artan sırada.
    assert [r.session_id for r in refs] == ["s9", "s8", "s7"]


def test_limit_disindaki_bozuk_dosya_kesfi_dusurmez(tmp_path):
    """Limit dışında kalacak (en eski mtime'lı) bir dosya bozuksa bile —
    ayrıştırma ona hiç ULAŞMAYACAĞI için — küçük bir `limit` ile çağrı
    hatasız, doğru sonuçla döner.

    Bozukluk burada kırık bir sembolik bağ ile simüle edilir: hedefi olmayan
    bağ `stat()` aşamasında OSError fırlatır, bu da adayların içerik hiç
    okunmadan elenebildiğini kanıtlar.
    """
    for i in range(3):
        _oturum_yaz(
            tmp_path,
            "-p",
            f"saglam{i}",
            [{"type": "user", "message": {"role": "user", "content": f"m{i}"}}],
            mtime=2000 + i,
        )
    # En eski konumda kırık bir sembolik bağ — limit dışında kalmalı.
    hedef = tmp_path / ".claude" / "projects" / "-p"
    kirik_bag = hedef / "bozuk.jsonl"
    kirik_bag.symlink_to(hedef / "yok-boyle-bir-dosya.jsonl")
    os.utime(kirik_bag, (1000, 1000), follow_symlinks=False)

    refs = ClaudeSource(tmp_path).list(limit=2)

    assert [r.session_id for r in refs] == ["saglam2", "saglam1"]


def test_limit_verilmezse_davranis_eskisiyle_aynidir(tmp_path):
    """`limit=None` (varsayılan) davranışı, bu değişiklikten ÖNCEKİ ile aynı
    kalmalı: tüm oturumlar, yeniden eskiye sıralı döner."""
    for i in range(5):
        _oturum_yaz(
            tmp_path,
            "-p",
            f"s{i}",
            [{"type": "user", "message": {"role": "user", "content": f"m{i}"}}],
            mtime=1000 + i,
        )

    refs = ClaudeSource(tmp_path).list()

    assert [r.session_id for r in refs] == ["s4", "s3", "s2", "s1", "s0"]


def test_limit_ile_proje_onceliklendirmesi_bozulmaz(tmp_path):
    """`limit` verildiğinde de proje aidiyeti önceliği korunmalı: kendi
    projenin oturumu, diğer projenin DAHA YENİ oturumundan önce gelmeli —
    tıpkı `limit` yokken olduğu gibi."""
    now = time.time()
    eski_mtime = now - 1000
    yeni_mtime = now

    _oturum_yaz(
        tmp_path,
        "-baska-proje",
        "diger",
        [{"type": "user", "message": {"role": "user", "content": "diğer proje mesajı"}}],
        mtime=yeni_mtime,
    )
    _oturum_yaz(
        tmp_path,
        "-p",
        "bu-proje",
        [{"type": "user", "message": {"role": "user", "content": "bu proje mesajı"}}],
        mtime=eski_mtime,
    )

    refs = ClaudeSource(tmp_path).list(root=Path("/p"), limit=1)

    assert [r.session_id for r in refs] == ["bu-proje"]


def test_root_verildiginde_diger_proje_kaybolmaz_ama_geriye_atilir(tmp_path):
    """Root dizini belirtilirse, kendi proje oturumları diğer projelerin
    oturumlarından önce gelir — aidiyet öncelik kuralını doğrula.

    Test, bu davranışın saf kronolojik sıralamadan farklı olduğunu kanıtlar:
    diğer projenin oturumu kendi projenin oturumundan DAHA YENİ olmasına
    rağmen, kendi proje YINE önce gelmeli (aidiyet üstün).
    """
    now = time.time()
    eski_mtime = now - 1000  # Kendi proje daha eski
    yeni_mtime = now  # Diğer proje daha yeni

    # Diğer projeyi, YENİ mtime ile yaz
    _oturum_yaz(
        tmp_path,
        "-baska-proje",
        "diger",
        [{"type": "user", "message": {"role": "user", "content": "diğer proje mesajı"}}],
        mtime=yeni_mtime,
    )
    # Kendi projeyi, ESKİ mtime ile yaz
    _oturum_yaz(
        tmp_path,
        "-p",
        "bu-proje",
        [{"type": "user", "message": {"role": "user", "content": "bu proje mesajı"}}],
        mtime=eski_mtime,
    )

    refs = ClaudeSource(tmp_path).list(root=Path("/p"))

    # Beklenti: "bu-proje" ESKİ OLMASINA RAĞMEN ÖNCE GELIR (aidiyet sayesinde)
    assert [r.session_id for r in refs] == ["bu-proje", "diger"]


def test_model_controlled_session_id_is_not_a_glob(tmp_path) -> None:
    _oturum_yaz(
        tmp_path,
        "-p",
        "safe-id",
        [{"type": "user", "message": {"role": "user", "content": "özel içerik"}}],
    )
    source = ClaudeSource(tmp_path)

    for unsafe_id in ("*", "[a]", "../safe-id", "-p/safe-id"):
        assert source.read(unsafe_id) == ()


def test_title_falls_back_to_date_and_size(tmp_path) -> None:
    path = _oturum_yaz(tmp_path, "-p", "s1", [], mtime=1_700_000_000.0)

    (ref,) = ClaudeSource(tmp_path).list()

    assert "2023-11-14" in ref.title
    assert f"{path.stat().st_size} bayt" in ref.title
    assert ref.title != "s1"
