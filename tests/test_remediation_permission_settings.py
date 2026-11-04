"""İzin kapsamı görüntülenir; aynı yüzeyden yalnız seçilen izin geri alınır."""

from __future__ import annotations

from fusion_cli.appserver.session import AppSession
from fusion_cli.config import browser_sites


async def test_panel_lists_and_revokes_engine_session_and_persistent_site_permissions(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(browser_sites, "sites_file", lambda: tmp_path / "browser-sites.json")
    session = AppSession(lambda _: None, root=tmp_path, home=tmp_path / "home")
    memory = session._state.approval_memory
    memory._scopes.update({"chrome-site:work.test", "browser-site:docs.test"})
    browser_sites.add_allowed("docs.test")
    listed = await session._chrome_settings({"izinler": True})
    rows = {row["anahtar"]: row for row in listed["izinler"]}
    assert rows["chrome-site:work.test"]["kapsam"] == "Bu oturum boyunca"
    assert rows["browser-site:docs.test"]["kapsam"] == "Kalıcı · yerleşik Browser"
    assert (await session._chrome_settings({"izin_sil": "chrome-site:work.test"}))["ok"]
    assert not memory.scopes_with_prefix("chrome-site:")
    assert "docs.test" in browser_sites.load_allowed()
    assert (await session._chrome_settings({"izin_sil": "browser-site:docs.test"}))["ok"]
    assert not browser_sites.load_allowed()
    assert not memory.scopes_with_prefix("browser-site:")
