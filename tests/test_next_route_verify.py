"""Next istemcilerinin 404'e düşen API çağrılarını bağımsız yakala."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.next_route_verify import NextRouteVerifier
from fusion_cli.engines.agent.verification import build_verifier

from .fakes import make_config


def _client(root: Path) -> Path:
    file = root / "components/stok/stokApi.ts"
    file.parent.mkdir(parents=True)
    file.write_text(
        'const API_BASE = "/api/stok";\n'
        "export async function stokGet(path: string) {\n"
        "  return fetch(`${API_BASE}/${path}`);\n"
        "}\n",
        encoding="utf-8",
    )
    (root / "next.config.mjs").write_text("export default {};\n", encoding="utf-8")
    return file


@pytest.mark.asyncio
async def test_eksik_next_catchall_route_derleme_gecse_de_yakalanir(tmp_path):
    client = _client(tmp_path)

    result = await NextRouteVerifier(tmp_path, (client,)).verify()

    assert result.ok is False
    assert "/api/stok/*" in result.findings[0]
    assert "404" in result.findings[0]


@pytest.mark.asyncio
async def test_eksik_route_turun_gercek_kalite_kapisini_dusurur(tmp_path):
    client = _client(tmp_path)
    context = ToolContext(root=tmp_path)
    context.changes.record_created(client)
    verifier = build_verifier(make_config(), root=tmp_path, tool_context=context)

    assert verifier is not None
    result = await verifier.verify()

    assert result.ok is False
    assert any("/api/stok/*" in finding for finding in result.findings)


@pytest.mark.asyncio
async def test_mevcut_route_veya_rewrite_gecer(tmp_path):
    client = _client(tmp_path)
    route = tmp_path / "app/api/stok/[...path]/route.ts"
    route.parent.mkdir(parents=True)
    route.write_text("export async function GET() {}\n", encoding="utf-8")

    assert (await NextRouteVerifier(tmp_path, (client,)).verify()).ok

    route.unlink()
    alternate = route.parent.parent / "[...slug]/route.ts"
    alternate.parent.mkdir()
    alternate.write_text("export async function GET() {}\n", encoding="utf-8")
    assert (await NextRouteVerifier(tmp_path, (client,)).verify()).ok
    alternate.unlink()
    nested = tmp_path / "src/app/api/stok/[...slug]/route.ts"
    nested.parent.mkdir(parents=True)
    nested.write_text("export async function GET() {}\n", encoding="utf-8")
    assert (await NextRouteVerifier(tmp_path, (client,)).verify()).ok
    nested.unlink()
    (tmp_path / "next.config.mjs").write_text(
        "export default { async rewrites() { return ["
        "{ source: '/api/stok/:path*', destination: 'http://localhost:3001/:path*' }"
        "]; }};\n",
        encoding="utf-8",
    )

    assert (await NextRouteVerifier(tmp_path, (client,)).verify()).ok


@pytest.mark.asyncio
async def test_ilgisiz_ve_degisilmeyen_dosyalar_kapiyi_dusurmez(tmp_path):
    client = _client(tmp_path)
    other = tmp_path / "components/other.ts"
    other.write_text("export const x = 1;\n", encoding="utf-8")

    assert (await NextRouteVerifier(tmp_path, (other,)).verify()).ok
    assert (await NextRouteVerifier(tmp_path, (tmp_path / "../elsewhere.ts",)).verify()).ok
    assert client.is_file()
