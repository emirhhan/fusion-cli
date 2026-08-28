"""Claude Code JSONL okuyucusu."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.history.claude_source import ClaudeSource, slug_for


def _oturum_yaz(home: Path, slug: str, session_id: str, kayitlar: list[dict]) -> Path:
    hedef = home / ".claude" / "projects" / slug
    hedef.mkdir(parents=True, exist_ok=True)
    yol = hedef / f"{session_id}.jsonl"
    yol.write_text("\n".join(json.dumps(k) for k in kayitlar), encoding="utf-8")
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
