"""Masaüstü çalışma alanı protokolünün kök ve içerik sözleşmeleri."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


async def _request(root: Path, name: str, data: dict[str, object]) -> dict[str, object]:
    lines: list[str] = []
    session = AppSession(lines.append, root=root, home=root.parent / f".{root.name}-home")
    await session.handle(Request(id="workspace", name=name, data=data))
    await session.close()
    return json.loads(lines[-1])["veri"]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True)


async def test_proje_listesi_klasorleri_once_ve_sayfali_dondurur(tmp_path: Path):
    """Sıralama ya da cursor kaldırılırsa büyük ağaçta satırlar atlanır/tekrarlanır."""
    (tmp_path / "z.txt").write_text("z", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")
    (tmp_path / "src").mkdir()

    first = await _request(tmp_path, "proje.listele", {"yol": "", "limit": 2, "cursor": 0})
    second = await _request(
        tmp_path,
        "proje.listele",
        {"yol": "", "limit": 2, "cursor": first["next_cursor"]},
    )

    assert [(item["ad"], item["tur"]) for item in first["girdiler"]] == [
        ("src", "klasor"),
        (".env", "dosya"),
    ]
    assert first["next_cursor"] == 2
    assert first["has_more"] is True
    assert [item["ad"] for item in second["girdiler"]] == ["z.txt"]
    assert second["next_cursor"] is None
    assert second["has_more"] is False


async def test_proje_oku_utf8_icerik_ve_sha256_dondurur(tmp_path: Path):
    """İçerik veya özet yanlış dosyadan gelirse editör stale yazımı algılayamaz."""
    content = "merhaba\nşğü\n"
    (tmp_path / "not.txt").write_text(content, encoding="utf-8")

    result = await _request(tmp_path, "proje.oku", {"yol": "not.txt"})

    assert result == {
        "ok": True,
        "yol": "not.txt",
        "tur": "metin",
        "mime": "text/plain",
        "boyut": len(content.encode()),
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "icerik": content,
        "kesildi": False,
    }


async def test_binary_dosya_metne_cevrilmeden_metadata_dondurur(tmp_path: Path):
    """Binary baytlar JSON metnine sokulursa içerik bozulur ve süreç şişer."""
    raw = b"\x00\xff\x10PNG"
    (tmp_path / "image.bin").write_bytes(raw)

    result = await _request(tmp_path, "proje.oku", {"yol": "image.bin"})

    assert result["ok"] is True
    assert result["tur"] == "binary"
    assert result["icerik"] is None
    assert result["boyut"] == len(raw)
    assert result["sha256"] == hashlib.sha256(raw).hexdigest()


async def test_metin_okuma_bayt_tavaninda_kesilir(tmp_path: Path):
    """Tavan uygulanmazsa tek büyük dosya stdio protokolünü ve arayüzü kilitler."""
    (tmp_path / "large.txt").write_text("abcdefghij", encoding="utf-8")

    result = await _request(tmp_path, "proje.oku", {"yol": "large.txt", "max_bytes": 4})

    assert result["icerik"] == "abcd"
    assert result["kesildi"] is True
    assert result["boyut"] == 10


async def test_kok_disina_cikan_goreli_ve_mutlak_yollar_reddedilir(tmp_path: Path):
    """Kök kontrolü kaldırılırsa denetçi proje dışındaki özel dosyaları açabilir."""
    relative = await _request(tmp_path, "proje.oku", {"yol": "../secret.txt"})
    absolute = await _request(tmp_path, "proje.oku", {"yol": "/etc/passwd"})

    assert relative == {"ok": False, "metin": "Proje klasörünün dışına çıkılamaz."}
    assert absolute == {"ok": False, "metin": "Proje klasörünün dışına çıkılamaz."}


async def test_kok_disina_cikan_sembolik_bag_reddedilir(tmp_path: Path):
    """Sözcüksel yol kontrolü tek başına kalırsa symlink kök sınırını aşar."""
    outside = tmp_path.parent / "outside-fusion-secret.txt"
    outside.write_text("gizli", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)

    result = await _request(tmp_path, "proje.oku", {"yol": "link.txt"})

    assert result == {"ok": False, "metin": "Proje klasörünün dışına çıkılamaz."}


async def test_proje_durumu_tum_agaci_taramadan_temel_yetenekleri_bildirir(tmp_path: Path):
    """Durum sözleşmesi eksilirse UI proje seçildiğini güvenilir biçimde anlayamaz."""
    (tmp_path / ".git").mkdir()

    result = await _request(tmp_path, "proje.durum", {})

    assert result == {
        "ok": True,
        "kok": str(tmp_path),
        "git": True,
        "okunabilir": True,
        "yazilabilir": True,
    }


async def test_proje_yaz_sha_kapisi_diff_ve_geri_alma_saglar(tmp_path: Path):
    """Hash kapısı veya anlık görüntü kalkarsa UI başkasının yazımını sessizce ezer."""
    path = tmp_path / "app.txt"
    path.write_text("eski\n", encoding="utf-8")
    old_sha = hashlib.sha256(b"eski\n").hexdigest()
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path.parent / ".fusion-home")

    await session.handle(
        Request(
            id="write",
            name="proje.yaz",
            data={"yol": "app.txt", "icerik": "yeni\n", "expected_sha256": old_sha},
        )
    )
    written = json.loads(lines[-1])["veri"]

    assert written["ok"] is True
    assert written["yol"] == "app.txt"
    assert written["added"] == 1
    assert written["removed"] == 1
    assert "-eski" in written["diff"]
    assert "+yeni" in written["diff"]
    assert path.read_text(encoding="utf-8") == "yeni\n"

    await session.handle(Request(id="changes", name="proje.degisiklikler", data={}))
    changes = json.loads(lines[-1])["veri"]
    assert [item["yol"] for item in changes["degisiklikler"]] == ["app.txt"]

    await session.handle(Request(id="undo", name="proje.geri_al", data={"yol": "app.txt"}))
    undone = json.loads(lines[-1])["veri"]
    await session.close()

    assert undone["ok"] is True
    assert path.read_text(encoding="utf-8") == "eski\n"


async def test_proje_yaz_stale_hashte_dosyaya_dokunmaz(tmp_path: Path):
    """Beklenen özet karşılaştırılmazsa dışarıdaki yeni değişiklik kaybolur."""
    path = tmp_path / "app.txt"
    path.write_text("başkası değiştirdi", encoding="utf-8")

    result = await _request(
        tmp_path,
        "proje.yaz",
        {"yol": "app.txt", "icerik": "benim sürümüm", "expected_sha256": "eski-ozet"},
    )

    assert result == {
        "ok": False,
        "kod": "STALE_FILE",
        "metin": "Dosya başka bir işlem tarafından değiştirildi. Yeniden yükleyip tekrar dene.",
    }
    assert path.read_text(encoding="utf-8") == "başkası değiştirdi"


async def test_proje_yaz_sembolik_bagla_kok_disina_cikamaz(tmp_path: Path):
    """Yazma yolu okuma sınırını atlatırsa proje dışındaki dosya değişebilir."""
    outside = tmp_path.parent / "outside-write-target.txt"
    outside.write_text("koru", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(outside)

    result = await _request(
        tmp_path,
        "proje.yaz",
        {
            "yol": "link.txt",
            "icerik": "boz",
            "expected_sha256": hashlib.sha256(b"koru").hexdigest(),
        },
    )

    assert result == {"ok": False, "metin": "Proje klasörünün dışına çıkılamaz."}
    assert outside.read_text(encoding="utf-8") == "koru"


async def test_degisiklikler_agentin_git_ve_yeni_dosya_degisimlerini_gosterir(tmp_path: Path):
    """Yalnız UI günlüğü okunursa agentın gerçek dosya değişiklikleri görünmez kalır."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "fusion@test.local")
    _git(tmp_path, "config", "user.name", "Fusion Test")
    (tmp_path / "tracked.txt").write_text("önce\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-qm", "baseline")
    (tmp_path / "tracked.txt").write_text("sonra\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("yeni dosya\n", encoding="utf-8")

    result = await _request(tmp_path, "proje.degisiklikler", {})

    by_path = {item["yol"]: item for item in result["degisiklikler"]}
    assert set(by_path) == {"new.txt", "tracked.txt"}
    assert "-önce" in by_path["tracked.txt"]["diff"]
    assert "+sonra" in by_path["tracked.txt"]["diff"]
    assert "+yeni dosya" in by_path["new.txt"]["diff"]

    tracked_undo = await _request(tmp_path, "proje.geri_al", {"yol": "tracked.txt"})
    new_undo = await _request(tmp_path, "proje.geri_al", {"yol": "new.txt"})

    assert tracked_undo["ok"] is True
    assert new_undo["ok"] is True
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "önce\n"
    assert not (tmp_path / "new.txt").exists()
