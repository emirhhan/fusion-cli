"""#431 kalanları: computer modifiers, koordinatla hover, start_coordinate ile sürükleme,
read_page max_chars, tabs_context_mcp createIfEmpty, gif_creator stop/export/clear."""

from __future__ import annotations

import json

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import chrome
from fusion_cli.tools.claude_chrome_translate import translate

P = "claude-in-chrome__"


class _Kopru:
    def __init__(self, tabs: list[list[dict]] | None = None, frames: int = 2) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._tabs = list(tabs or [])
        self._frames = frames

    async def invoke(self, name, data):
        self.calls.append((name, data))
        if name.startswith("describe"):
            return {"ok": True, "veri": {"name": "Bağlantı", "type": ""}}
        if name == "tabs":
            sekmeler = self._tabs.pop(0) if self._tabs else []
            return {"ok": True, "veri": {"tabs": sekmeler}}
        if name == "tree":
            return {"ok": True, "veri": {"tree": "x" * 500, "doc": 1}}
        if name == "record":
            if data.get("op") == "stop":
                return {"ok": True, "veri": {"frames": self._frames, "url": "https://a.test"}}
            if data.get("op") == "release":
                return {"ok": True, "veri": {"released": True, "frames": self._frames}}
            return {"ok": True, "veri": {"frames": [], "next": None}}
        return {"ok": True, "veri": {"changed": True}}


def _ctx(tmp_path, kopru) -> ToolContext:
    return ToolContext(root=tmp_path, chrome=kopru)  # type: ignore[arg-type]


def test_degistirici_tuslu_tiklama_ic_cagriya_cevrilir():
    assert translate(
        P + "computer",
        {"action": "left_click", "coordinate": [10, 20], "modifiers": "cmd+Shift"},
    ) == ("chrome_action", {"action": "click_at", "value": "10,20", "modifiers": "meta+shift"})
    assert translate(
        P + "computer", {"action": "left_click", "ref": "e4", "modifiers": "ctrl"}
    ) == ("chrome_action", {"action": "click_at", "ref": "e4", "modifiers": "ctrl"})
    assert translate(
        P + "computer", {"action": "double_click", "ref": "e4", "modifiers": "windows+alt"}
    ) == ("chrome_action", {"action": "double_click", "ref": "e4", "modifiers": "meta+alt"})
    assert isinstance(
        translate(P + "computer", {"action": "left_click", "ref": "e4", "modifiers": "hyper"}),
        str,
    )


def test_koordinatla_hover_ve_baslangic_noktasindan_surukleme():
    assert translate(P + "computer", {"action": "hover", "coordinate": [5, 6]}) == (
        "chrome_action",
        {"action": "hover", "value": "5,6"},
    )
    assert translate(
        P + "computer",
        {"action": "left_click_drag", "start_coordinate": [10, 20], "coordinate": [30, 40]},
    ) == ("chrome_action", {"action": "drag", "value": "30,40", "start": "10,20"})
    assert translate(
        P + "computer", {"action": "left_click_drag", "ref": "e2", "coordinate": [30, 40]}
    ) == ("chrome_action", {"action": "drag", "value": "30,40", "ref": "e2"})
    assert isinstance(translate(P + "computer", {"action": "left_click_drag"}), str)


def test_okuma_siniri_sekme_olusturma_ve_gif_eylemleri_cevrilir():
    assert translate(P + "read_page", {"max_chars": 100}) == (
        "chrome_page",
        {"tree": "all", "max_chars": 100},
    )
    assert translate(P + "tabs_context_mcp", {"createIfEmpty": True}) == (
        "chrome_action",
        {"action": "tabs", "value": "create_if_empty"},
    )
    assert translate(P + "tabs_context_mcp", {}) == ("chrome_action", {"action": "tabs"})
    gif = {
        a: translate(P + "gif_creator", {"action": a})
        for a in ("stop_recording", "export", "clear")
    }
    assert gif["stop_recording"] == ("chrome_action", {"action": "record", "value": "halt"})
    assert gif["export"] == ("chrome_action", {"action": "record", "value": "stop"})
    assert gif["clear"] == ("chrome_action", {"action": "record", "value": "clear"})
    assert translate(P + "gif_creator", {"action": "export", "filename": "akis.gif"}) == (
        "chrome_action",
        {"action": "record", "value": "stop", "filename": "akis.gif"},
    )


async def test_degistirici_tuslar_eklentiye_gider(tmp_path):
    kopru = _Kopru()
    ctx = _ctx(tmp_path, kopru)
    nokta = await chrome.chrome_action(
        {"action": "click_at", "value": "10,20", "modifiers": "meta+shift"}, ctx
    )
    ogeli = await chrome.chrome_action(
        {"action": "click_at", "ref": "e4", "modifiers": "ctrl"}, ctx
    )
    assert nokta.ok and ogeli.ok
    assert ("click_at", {"x": 10.0, "y": 20.0, "mods": ["meta", "shift"]}) in kopru.calls
    assert ("describe", {"ref": "e4"}) in kopru.calls
    assert ("click", {"ref": "e4", "mods": ["ctrl"]}) in kopru.calls
    hatali = await chrome.chrome_action({"action": "click_at", "ref": "e4", "modifiers": "x"}, ctx)
    assert not hatali.ok


async def test_koordinatla_hover_ve_noktadan_surukleme_eklentiye_gider(tmp_path):
    kopru = _Kopru()
    ctx = _ctx(tmp_path, kopru)
    assert (await chrome.chrome_action({"action": "hover", "value": "5,6"}, ctx)).ok
    surukle = await chrome.chrome_action(
        {"action": "drag", "value": "30,40", "start": "10,20"}, ctx
    )
    assert surukle.ok
    assert ("hover", {"x": 5.0, "y": 6.0}) in kopru.calls
    assert ("drag", {"from_x": 10.0, "from_y": 20.0, "x": 30.0, "y": 40.0}) in kopru.calls


async def test_okuma_siniri_metni_keser_ve_not_dusulur(tmp_path):
    sonuc = await chrome.chrome_page({"tree": "all", "max_chars": 120}, _ctx(tmp_path, _Kopru()))
    assert sonuc.ok
    assert len(sonuc.output) < 400
    assert "max_chars" in sonuc.output


async def test_sekme_yoksa_bos_sekme_acilir(tmp_path):
    kopru = _Kopru(tabs=[[], [{"id": 9, "url": "about:blank"}]])
    sonuc = await chrome.chrome_action(
        {"action": "tabs", "value": "create_if_empty"}, _ctx(tmp_path, kopru)
    )
    assert sonuc.ok
    assert [name for name, _ in kopru.calls] == ["tabs", "tab_open", "tabs"]
    assert kopru.calls[1] == ("tab_open", {"blank": True})
    assert json.loads(sonuc.output)["tabs"][0]["id"] == 9
    dolu = _Kopru(tabs=[[{"id": 3, "url": "https://a.test"}]])
    await chrome.chrome_action({"action": "tabs", "value": "create_if_empty"}, _ctx(tmp_path, dolu))
    assert [name for name, _ in dolu.calls] == ["tabs"]


async def test_kayit_durdurma_kareleri_tutar_temizleme_birakir(tmp_path):
    kopru = _Kopru(frames=3)
    ctx = _ctx(tmp_path, kopru)
    dur = await chrome.chrome_action({"action": "record", "value": "halt"}, ctx)
    assert dur.ok and "3" in dur.output
    assert [d.get("op") for n, d in kopru.calls] == ["stop"]
    temizle = await chrome.chrome_action({"action": "record", "value": "clear"}, ctx)
    assert temizle.ok
    assert [d.get("op") for n, d in kopru.calls] == ["stop", "stop", "release"]


@pytest.mark.parametrize("ad", ["../kacak.gif", "a/b.gif", ""])
def test_gif_dosya_adi_guvenli_olmali(ad):
    from fusion_cli.tools.chrome_record import gif_name

    adi = gif_name(ad)
    assert "/" not in adi and adi.endswith(".gif") and ".." not in adi


def test_gif_dosya_adi_verilirse_kullanilir():
    from fusion_cli.tools.chrome_record import gif_name

    assert gif_name("akis") == "akis.gif"
    assert gif_name("Akış kaydı.gif") == "Akış kaydı.gif"


_JPEG = (
    b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x02\x00\x04\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xd9"
)


class _GoruntuKopru(_Kopru):
    async def invoke(self, name, data):
        if name == "screenshot":
            self.calls.append((name, data))
            import base64

            image = "data:image/jpeg;base64," + base64.b64encode(_JPEG).decode()
            return {"ok": True, "veri": {"image": image, "width": 4}}
        return await super().invoke(name, data)


def test_upload_image_ic_cagriya_cevrilir():
    assert translate(P + "upload_image", {"imageId": "ss_1", "ref": "e3"}) == (
        "chrome_action",
        {"action": "upload_image", "value": "ss_1", "ref": "e3"},
    )
    assert translate(
        P + "upload_image", {"imageId": "ss_1", "coordinate": [5, 6], "filename": "a.png"}
    ) == (
        "chrome_action",
        {"action": "upload_image", "value": "ss_1", "point": "5,6", "filename": "a.png"},
    )
    assert isinstance(translate(P + "upload_image", {"imageId": "ss_1"}), str)
    assert isinstance(
        translate(P + "upload_image", {"imageId": "ss_1", "ref": "e3", "coordinate": [1, 2]}),
        str,
    )


async def test_ekran_goruntusu_kimligi_upload_image_ile_yuklenir(tmp_path):
    kopru = _GoruntuKopru()
    ctx = _ctx(tmp_path, kopru)
    shot = await chrome.chrome_action({"action": "screenshot"}, ctx)
    assert shot.ok
    image_id = shot.output.split("imageId: ")[1].split()[0].rstrip(");.,")
    sonuc = await chrome.chrome_action(
        {"action": "upload_image", "value": image_id, "ref": "e3"}, ctx
    )
    assert sonuc.ok
    name, data = kopru.calls[-1]
    assert name == "upload" and data["ref"] == "e3"
    assert data["files"][0]["mime"] == "image/jpeg"
    assert data["files"][0]["name"].endswith(".jpg")
    birak = await chrome.chrome_action(
        {"action": "upload_image", "value": image_id, "point": "5,6", "filename": "a.jpg"}, ctx
    )
    assert birak.ok
    name, data = kopru.calls[-1]
    assert name == "upload" and data["x"] == 5.0 and data["y"] == 6.0
    assert data["files"][0]["name"] == "a.jpg"
    yok = await chrome.chrome_action({"action": "upload_image", "value": "ss_99", "ref": "e3"}, ctx)
    assert not yok.ok and "ss_99" in yok.output
