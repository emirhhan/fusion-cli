"""Yapısal dosya biçimlerinin yazılmadan ÖNCE denetlenmesi.

Gerçek hata: model MCP aracıyla tıkanınca `.tscn` dosyasını elle düzenlemeye
geçti ve Godot sahne formatını bilmediği için bozdu. Fusion dosyayı sessizce
yazdı ve turu `completed` diye kapattı; kullanıcı bozuk bir proje aldı. Godot'un
söyledikleri ölçüldü:

- `[gd_scene]` başlığı yoksa: `Parse Error: Unrecognized file type 'node'`
- `project.godot`'ta anahtarlar `[application]` bölümünden önce gelirse:
  `no main scene defined in the project`
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.structured_files import validate_structured


def test_bilinmeyen_bicim_denetlenmez():
    assert validate_structured(Path("notlar.txt"), "herhangi bir metin") is None
    assert validate_structured(Path("kod.py"), "def f(:") is None


def test_bozuk_json_reddedilir():
    assert validate_structured(Path("a.json"), '{"a": 1}') is None
    sorun = validate_structured(Path("a.json"), '{"a": 1,}')
    assert sorun is not None and "JSON" in sorun


def test_bozuk_toml_reddedilir():
    assert validate_structured(Path("a.toml"), 'ad = "x"') is None
    assert validate_structured(Path("a.toml"), "ad = ") is not None


def test_tscn_gd_scene_basligi_zorunlu():
    """Ölçüldü: başlıksız sahne Godot'ta `Unrecognized file type 'node'` veriyor."""
    gecerli = '[gd_scene format=3]\n\n[node name="root" type="Node2D"]\n'
    assert validate_structured(Path("main.tscn"), gecerli) is None

    sorun = validate_structured(Path("main.tscn"), '[node name="root" type="Node2D"]\n')
    assert sorun is not None
    assert "gd_scene" in sorun


def test_tscn_ext_resource_dugumlerden_once_gelmeli():
    """Ölçüldü: `ext_resource` düğümlerden SONRA yazılınca sahne yüklenmiyor."""
    bozuk = (
        "[gd_scene format=3]\n\n"
        '[node name="root" type="Node2D"]\n'
        '[ext_resource type="Script" path="res://a.gd" id="1"]\n'
    )
    sorun = validate_structured(Path("main.tscn"), bozuk)
    assert sorun is not None
    assert "ext_resource" in sorun

    duzgun = (
        "[gd_scene format=3]\n\n"
        '[ext_resource type="Script" path="res://a.gd" id="1"]\n\n'
        '[node name="root" type="Node2D"]\n'
    )
    assert validate_structured(Path("main.tscn"), duzgun) is None


def test_project_godot_anahtarlari_bolum_icinde_olmali():
    """Ölçüldü: bölümsüz anahtarlar `no main scene defined` ile sonuçlanıyor."""
    bozuk = 'config/name="Oyun"\nrun/main_scene="res://main.tscn"\n'
    sorun = validate_structured(Path("project.godot"), bozuk)
    assert sorun is not None
    assert "[application]" in sorun

    duzgun = '[application]\n\nconfig/name="Oyun"\nrun/main_scene="res://main.tscn"\n'
    assert validate_structured(Path("project.godot"), duzgun) is None


def test_yorum_ve_bos_satir_bolum_sayilmaz():
    """Başlıktan önceki yorum ve boşluk normaldir; hata sayılmamalı."""
    duzgun = '; Godot yapılandırması\n\n[application]\nconfig/name="Oyun"\n'
    assert validate_structured(Path("project.godot"), duzgun) is None


# --- araçlara bağlanması ---------------------------------------------------- #


def test_write_file_bozuk_sahneyi_yazmaz(tmp_path):
    """Bozuk yapı DİSKE ULAŞMAMALI.

    Yazıp sonra uyarmak, kullanıcıyı bozuk dosyayla baş başa bırakırdı; ölçülen
    vakada tur "tamamlandı" derken proje açılmıyordu. Reddetmek önceki iyi
    durumu korur ve modele düzeltme şansı verir.
    """
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.files import write_file

    context = ToolContext(root=tmp_path)
    hedef = tmp_path / "main.tscn"

    sonuc = write_file({"path": "main.tscn", "content": '[node name="a" type="Node2D"]\n'}, context)

    assert sonuc.ok is False
    assert "gd_scene" in sonuc.output
    assert not hedef.exists(), "bozuk içerik diske yazılmamalı"


def test_write_file_gecerli_sahneyi_yazar(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.files import write_file

    context = ToolContext(root=tmp_path)
    icerik = '[gd_scene format=3]\n\n[node name="a" type="Node2D"]\n'

    sonuc = write_file({"path": "main.tscn", "content": icerik}, context)

    assert sonuc.ok is True
    assert (tmp_path / "main.tscn").read_text() == icerik


def test_replace_range_sahne_basligini_silemez(tmp_path):
    """Ölçülen vakada dosyayı asıl bozan `replace_range` oldu."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.files import read_file, replace_range

    context = ToolContext(root=tmp_path)
    hedef = tmp_path / "main.tscn"
    saglam = '[gd_scene format=3]\n\n[node name="a" type="Node2D"]\n'
    hedef.write_text(saglam)
    read_file({"path": "main.tscn"}, context)

    sonuc = replace_range(
        {"path": "main.tscn", "start_line": 1, "end_line": 1, "new": '[node name="b"]'},
        context,
    )

    assert sonuc.ok is False
    assert "gd_scene" in sonuc.output
    assert hedef.read_text() == saglam, "bozuk düzenleme diske ulaşmamalı"


# --- biçimi sahiplenen araçlar ---------------------------------------------- #


def test_sahne_dosyasi_arac_varken_elle_yazilamaz():
    """`.tscn` formatını Godot araçları ÜRETİR; model elle yazmamalı.

    Ölçüldü: model GDScript'i kusursuz yazıyor ama sahne formatını her seferinde
    bozuyor (başlığı siliyor, `ext_resource` bloklarını sona koyuyor). Araçlar
    Godot'un kendisini çalıştırdığı için dosyayı tanım gereği doğru üretiyor.
    """
    icerik = '[gd_scene format=3]\n\n[node name="a" type="Node2D"]\n'
    araclar = frozenset({"godot__add_node", "godot__save_scene"})

    sorun = validate_structured(Path("main.tscn"), icerik, available_tools=araclar)

    assert sorun is not None, "araç varken elle yazma engellenmeli"
    assert "godot__add_node" in sorun
    assert "godot__save_scene" in sorun


def test_arac_yoksa_elle_yazmaya_izin_verilir():
    """MCP bağlı değilse tek yol elle yazmaktır; engellemek işi imkânsız kılardı."""
    icerik = '[gd_scene format=3]\n\n[node name="a" type="Node2D"]\n'

    assert validate_structured(Path("main.tscn"), icerik, available_tools=frozenset()) is None
    assert validate_structured(Path("main.tscn"), icerik) is None


def test_arac_varken_de_bozuk_yapi_bozuk_kalir():
    """Yönlendirme, yapı denetiminin YERİNE geçmez."""
    araclar = frozenset({"godot__add_node", "godot__save_scene"})

    sorun = validate_structured(Path("main.tscn"), '[node name="a"]\n', available_tools=araclar)

    assert sorun is not None


#: Godot araçlarının sunulduğu, gerçek koşudaki araç kümesi.
_GODOT_ARACLARI = frozenset({"godot__add_node", "godot__save_scene"})

#: Script'i düğüme bağlayan, biçimi geçerli sahne — Godot MCP'de bunu yapan
#: hiçbir araç YOKTUR (14 aracın hiçbiri script eklemiyor).
_SCRIPTLI_SAHNE = (
    "[gd_scene format=3]\n\n"
    '[ext_resource type="Script" path="res://player.gd" id="1_s"]\n\n'
    '[node name="Player" type="CharacterBody2D"]\n'
    'script = ExtResource("1_s")\n'
)


def test_hedefli_duzenleme_sahipli_bicimde_de_serbesttir():
    """Ölçüldü (Godot koşusu): oyun scriptleri hiçbir düğüme bağlanamadı.

    Godot MCP'nin 14 aracından hiçbiri script bağlayamıyor; Fusion da `.tscn`
    düzenlemeyi o araçlara yönlendirip elle düzenlemeyi kapatıyordu. İki kapı
    birlikte işi İMKÂNSIZ hâle getirdi: model her yolu denedi, hepsi kapalıydı.

    Kural genelleşir: bir kapı, işi YAPAMAYAN bir yeteneğe yönlendiremez.
    Yönlendirme dosyayı BAŞTAN YAZMAYA aittir; hedefli düzenleme açık kalır ve
    yapı denetiminden geçer.
    """
    sorun = validate_structured(
        Path("main.tscn"), _SCRIPTLI_SAHNE, available_tools=_GODOT_ARACLARI, authoring=False
    )

    assert sorun is None


def test_dosyayi_bastan_yazma_hala_araclara_yonlendirilir():
    sorun = validate_structured(
        Path("main.tscn"), _SCRIPTLI_SAHNE, available_tools=_GODOT_ARACLARI, authoring=True
    )

    assert sorun is not None
    assert "godot__add_node" in sorun


def test_hedefli_duzenleme_bicimi_bozarsa_yine_reddedilir():
    """Kapının ölçülmüş koruması aynen durur: başlıksız sahne kabul edilmez."""
    sorun = validate_structured(
        Path("main.tscn"),
        '[node name="a" type="Node2D"]\n',
        available_tools=_GODOT_ARACLARI,
        authoring=False,
    )

    assert sorun is not None
    assert "gd_scene" in sorun


def test_replace_range_ile_script_baglanabilir(tmp_path):
    """Uçtan uca: araçlar sunuluyorken bile hedefli düzenleme diske ulaşmalı."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import files

    sahne = tmp_path / "main.tscn"
    sahne.write_text(
        "[gd_scene format=3]\n\n" '[node name="Player" type="CharacterBody2D"]\n',
        encoding="utf-8",
    )
    context = ToolContext(root=tmp_path, available_tools=set(_GODOT_ARACLARI))
    files.read_file({"path": "main.tscn"}, context)

    sonuc = files.replace_range(
        {"path": "main.tscn", "start_line": 1, "end_line": 3, "new": _SCRIPTLI_SAHNE.strip()},
        context,
    )

    assert sonuc.ok is True, sonuc.output
    assert "script = ExtResource" in sahne.read_text(encoding="utf-8")


def test_edit_file_de_yapiyi_bozamaz(tmp_path):
    """`edit_file` yapı denetiminden HİÇ geçmiyordu; aynı hasar oradan sızabilirdi."""
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import files

    sahne = tmp_path / "main.tscn"
    sahne.write_text(
        "[gd_scene format=3]\n\n" '[node name="Player" type="Node2D"]\n', encoding="utf-8"
    )
    context = ToolContext(root=tmp_path, available_tools=set(_GODOT_ARACLARI))

    sonuc = files.edit_file(
        {"path": "main.tscn", "old": "[gd_scene format=3]\n", "new": ""}, context
    )

    assert sonuc.ok is False
    assert "gd_scene" in sonuc.output
    assert sahne.read_text(encoding="utf-8").startswith("[gd_scene")


def test_edit_file_gecerli_hedefli_degisikligi_yazar(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import files

    sahne = tmp_path / "main.tscn"
    sahne.write_text(
        "[gd_scene format=3]\n\n" '[node name="Player" type="Node2D"]\n', encoding="utf-8"
    )
    context = ToolContext(root=tmp_path, available_tools=set(_GODOT_ARACLARI))

    sonuc = files.edit_file(
        {
            "path": "main.tscn",
            "old": '[node name="Player" type="Node2D"]',
            "new": '[node name="Player" type="CharacterBody2D"]',
        },
        context,
    )

    assert sonuc.ok is True, sonuc.output
    assert "CharacterBody2D" in sahne.read_text(encoding="utf-8")
