"""Tema başlangıç kanıtı ile sonraki değişiklikleri ayrı tut."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.tools.capture_provenance import check_capture_provenance, save_capture_provenance
from fusion_cli.tools.site_capture import CapturedPage, SiteCapture
from fusion_cli.tools.site_responsive import CapturedVariant
from fusion_cli.tools.woo_theme import ThemeFiles


def _fixture(root: Path, *, responsive: bool) -> tuple[SiteCapture, ThemeFiles]:
    folder = root / "wp-content/themes/copy"
    folder.mkdir(parents=True)
    (folder / "header.php").write_text("desktop header")
    (folder / "front-page.php").write_text("desktop hero")
    url = "https://example.test/?order_key=fixture-private-value"
    variant = CapturedVariant(
        390,
        844,
        "private html",
        "",
        "",
        0,
        "",
        "mobile",
        media_query="(max-width: 768px)" if responsive else None,
        blocked=("https://private.test/?token=fixture-private-value",),
    )
    page = CapturedPage(url, "private title", "en", "", "", "", "", variants=(variant,))
    if responsive:
        (folder / "responsive.js").write_text("original runtime")
    files = (
        ("header.php", "front-page.php", "responsive.js")
        if responsive
        else ("header.php", "front-page.php")
    )
    return SiteCapture((page,), "", {}, ()), ThemeFiles(folder, files, (url,) if responsive else ())


@pytest.mark.asyncio
async def test_refused_source_gate_is_recorded_without_claiming_theme_overwrite(
    tmp_path: Path,
) -> None:
    capture, theme = _fixture(tmp_path, responsive=False)
    await save_capture_provenance(tmp_path, capture, theme)
    result = await check_capture_provenance(tmp_path, theme.folder)
    assert result.source_status == "unverified_source_transition"
    assert result.changed_files == ()
    assert result.missing_files == ()
    assert not result.has_responsive_transfer


@pytest.mark.asyncio
async def test_successful_transfer_then_overwrite_is_distinguished(tmp_path: Path) -> None:
    capture, theme = _fixture(tmp_path, responsive=True)
    await save_capture_provenance(tmp_path, capture, theme)
    (theme.folder / "header.php").write_text("agent overwrite")
    (theme.folder / "responsive.js").unlink()
    result = await check_capture_provenance(tmp_path, theme.folder)
    assert result.source_status == "verified_source_transition"
    assert result.has_responsive_transfer
    assert result.changed_files == ("header.php",)
    assert result.missing_files == ("responsive.js",)


@pytest.mark.asyncio
async def test_provenance_schema_excludes_raw_html_queries_titles_and_rejection_text(
    tmp_path: Path,
) -> None:
    capture, theme = _fixture(tmp_path, responsive=True)
    path = await save_capture_provenance(tmp_path, capture, theme)
    text = path.read_text()
    assert "fixture-private-value" not in text
    assert "private" not in text
    assert "order_key" not in text
    record = json.loads(text)
    assert record["primary_path"] == "/"
    assert record["viewports"][0]["width"] == 390
    assert record["verified_queries"] == ["(max-width: 768px)"]
    assert record["rejection_count"] == 1


@pytest.mark.asyncio
async def test_legacy_capture_without_variants_remains_observable(tmp_path: Path) -> None:
    capture, theme = _fixture(tmp_path, responsive=False)
    page = CapturedPage("https://example.test/", "", "", "", "", "", "")
    capture = SiteCapture((page,), "", {}, ())
    await save_capture_provenance(tmp_path, capture, theme)
    result = await check_capture_provenance(tmp_path, theme.folder)
    assert result.source_status == "no_viewport_contract"
    assert result.changed_files == ()


@pytest.mark.asyncio
async def test_postcheck_never_follows_template_symlink(tmp_path: Path) -> None:
    capture, theme = _fixture(tmp_path, responsive=True)
    await save_capture_provenance(tmp_path, capture, theme)
    target = tmp_path / ".env.json"
    target.write_text("fixture only")
    header = theme.folder / "header.php"
    header.unlink()
    header.symlink_to(target)
    result = await check_capture_provenance(tmp_path, theme.folder)
    assert result.missing_files == ("header.php",)


@pytest.mark.asyncio
async def test_clone_pipeline_snapshots_before_install_can_replace_generated_theme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import clone_tools

    capture, theme = _fixture(tmp_path, responsive=True)

    async def measure(*args, **kwargs):
        return SimpleNamespace(pages=[{"url": "https://example.test/"}])

    async def download(*args, **kwargs):
        return None

    async def capture_site(*args, **kwargs):
        return capture

    async def install(*args, **kwargs):
        assert (tmp_path / ".fusion/capture-provenance.json").exists()
        (theme.folder / "header.php").write_text("installation overwrite")

    monkeypatch.setattr(clone_tools, "url_block_reason", lambda url: None)
    monkeypatch.setattr(clone_tools.design, "measure", measure)
    monkeypatch.setattr(clone_tools.design, "download_assets", download)
    monkeypatch.setattr(clone_tools.design, "save_report", lambda *args: None)
    monkeypatch.setattr(clone_tools, "capture_site", capture_site)
    monkeypatch.setattr(clone_tools, "write_theme", lambda *args: theme)
    monkeypatch.setattr(clone_tools, "_install", install)
    result = await clone_tools.run_clone_site(
        {"url": "https://example.test/"}, ToolContext(tmp_path)
    )
    assert result.ok
    assert (await check_capture_provenance(tmp_path, theme.folder)).changed_files == ("header.php",)


@pytest.mark.asyncio
async def test_private_payment_path_is_redacted(tmp_path: Path) -> None:
    from dataclasses import replace

    capture, theme = _fixture(tmp_path, responsive=True)
    private_url = "https://example.test/checkout/order-received/fixture-order/?key=fixture-key"
    capture = replace(capture, pages=(replace(capture.pages[0], url=private_url),))
    theme = replace(theme, responsive_paths=(private_url,))
    path = await save_capture_provenance(tmp_path, capture, theme)
    assert "fixture-order" not in path.read_text()
    assert json.loads(path.read_text())["responsive_paths"] == ["/[redacted]"]


@pytest.mark.asyncio
async def test_verified_source_query_preserves_supported_screen_and_min_forms(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    capture, theme = _fixture(tmp_path, responsive=True)
    variants = capture.pages[0].variants
    for query, expected in [
        ("SCREEN and (max-width : 768px)", "(max-width: 768px)"),
        ("not all and (min-width: 769px)", "not all and (min-width: 769px)"),
    ]:
        capture = replace(
            capture,
            pages=(replace(capture.pages[0], variants=(replace(variants[0], media_query=query),)),),
        )
        path = await save_capture_provenance(tmp_path, capture, theme)
        record = json.loads(path.read_text())
        assert record["verified_queries"] == [expected]
        assert record["source_status"] == "verified_source_transition"


@pytest.mark.asyncio
async def test_tampered_manifest_cannot_expand_hash_scope(tmp_path: Path) -> None:
    capture, theme = _fixture(tmp_path, responsive=True)
    path = await save_capture_provenance(tmp_path, capture, theme)
    record = json.loads(path.read_text())
    record["generated_hashes"]["../../.env.json"] = "a" * 64
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="şeması"):
        await check_capture_provenance(tmp_path, theme.folder)


@pytest.mark.asyncio
async def test_multitransition_provenance_is_source_verified_but_not_theme_transferred(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from fusion_cli.tools.site_responsive import CapturedTransition

    capture, theme = _fixture(tmp_path, responsive=False)
    base = capture.pages[0].variants[0]
    left = replace(base, width=600, height=900, signature="mobile")
    right = replace(base, width=601, height=900, signature="tablet")
    transition = CapturedTransition("(max-width: 600px)", left, right, ("(max-width: 600px)",))
    page = replace(capture.pages[0], transitions=(transition,))
    path = await save_capture_provenance(tmp_path, replace(capture, pages=(page,)), theme)
    record = json.loads(path.read_text())
    assert record["verified_queries"] == ["(max-width: 600px)"]
    assert record["transitions"][0]["left_width"] == 600
    assert record["transitions"][0]["right_width"] == 601
    assert "mobile" not in path.read_text()
    result = await check_capture_provenance(tmp_path, theme.folder)
    assert result.source_status == "verified_source_transition"
    assert not result.has_responsive_transfer
