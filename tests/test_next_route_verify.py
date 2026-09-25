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
async def test_sablon_dizisinde_dogrudan_yazilan_api_yolu_da_yakalanir(tmp_path):
    client = tmp_path / "components/stok/stokApi.ts"
    client.parent.mkdir(parents=True)
    client.write_text(
        "export async function stokGet(path: string) {\n"
        "  return fetch(`/api/candidates/${path}`);\n"
        "}\n",
        encoding="utf-8",
    )

    result = await NextRouteVerifier(tmp_path, (client,)).verify()

    assert result.ok is False
    assert "/api/candidates/*" in result.findings[0]


@pytest.mark.asyncio
async def test_yeni_yazma_rotasinin_kosulsuz_basarisi_gercek_islem_sayilmaz(tmp_path):
    route = tmp_path / "app/api/candidates/[action]/route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        'import { NextResponse } from "next/server";\n'
        "export async function POST(request: Request, "
        "{ params }: { params: Promise<{ action: string }> }) {\n"
        "  const { action } = await params;\n"
        "  return NextResponse.json({ success: true, action });\n"
        "}\n",
        encoding="utf-8",
    )

    result = await NextRouteVerifier(tmp_path, (route,)).verify()

    assert result.ok is False
    assert "koşulsuz" in result.findings[0]

    route.write_text(
        'import { NextResponse } from "next/server";\n'
        'import { importCandidates } from "@/services/stok/import";\n'
        "export async function POST(request: Request) {\n"
        "  await importCandidates(await request.json());\n"
        "  return NextResponse.json({ success: true });\n"
        "}\n",
        encoding="utf-8",
    )
    assert (await NextRouteVerifier(tmp_path, (route,)).verify()).ok


@pytest.mark.asyncio
async def test_yetkili_helper_sadece_get_icinse_post_proxy_bulgusu_yok(tmp_path):
    helper = tmp_path / "lib/stok/client.ts"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        'export const stokFetch = () => fetch("http://127.0.0.1:4455", '
        '{ headers: { "X-MG-Panel": "1" } });\n',
        encoding="utf-8",
    )
    route = tmp_path / "app/api/stok/route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        'import { stokFetch } from "@/lib/stok/client";\n'
        "export async function GET() { return stokFetch(); }\n"
        'export async function POST() { return new Response("ok"); }\n',
        encoding="utf-8",
    )

    assert (await NextRouteVerifier(tmp_path, (route,)).verify()).ok


@pytest.mark.asyncio
async def test_yetkili_yerel_servis_basligini_ekleyen_post_proxy_korunmalidir(tmp_path):
    helper = tmp_path / "lib/stok/client.ts"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        'const STOK_URL = "http://127.0.0.1:4455";\n'
        "export const stokFetch = (path: string) => fetch(`${STOK_URL}/${path}`, "
        '{ headers: { "X-MG-Panel": "1" } });\n',
        encoding="utf-8",
    )
    route = tmp_path / "app/api/stok/[...path]/route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        'import { stokFetch } from "@/lib/stok/client";\n'
        "export async function POST(req: Request) {\n"
        '  const response = await stokFetch("candidates/import");\n'
        "  return new Response(await response.text());\n"
        "}\n",
        encoding="utf-8",
    )

    result = await NextRouteVerifier(tmp_path, (route,)).verify()

    assert result.ok is False
    assert "yetki" in result.findings[0].lower()

    route.write_text(
        'import { stokFetch } from "@/lib/stok/client";\n'
        'import { auth } from "@/lib/auth";\n'
        "export async function POST(req: Request) {\n"
        "  if (!await auth()) return new Response('Unauthorized', { status: 401 });\n"
        '  const response = await stokFetch("candidates/import");\n'
        "  return new Response(await response.text());\n"
        "}\n",
        encoding="utf-8",
    )
    assert (await NextRouteVerifier(tmp_path, (route,)).verify()).ok


@pytest.mark.asyncio
async def test_tarayıcıya_kopyalanabilen_yetkili_baslik_dogrulama_sayilmaz(tmp_path):
    client = tmp_path / "components/stok/stokApi.ts"
    client.parent.mkdir(parents=True)
    client.write_text(
        'export function stokPost() { return fetch("/api/stok/run", '
        '{ method: "POST", headers: { "X-MG-Panel": "1" } }); }\n',
        encoding="utf-8",
    )

    result = await NextRouteVerifier(tmp_path, (client,)).verify()

    assert result.ok is False
    assert any("kopyalayabilir" in finding for finding in result.findings)


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
async def test_kapi_kurulduktan_sonra_degisen_route_dogrulamada_gorulur(tmp_path):
    (tmp_path / "next.config.mjs").write_text("export default {};\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)
    verifier = build_verifier(make_config(), root=tmp_path, tool_context=context)
    assert verifier is not None

    helper = tmp_path / "lib/stok/client.ts"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        'export const stokFetch = () => fetch("http://127.0.0.1:4455", '
        '{ headers: { "X-MG-Panel": "1" } });\n',
        encoding="utf-8",
    )
    route = tmp_path / "app/api/stok/[...path]/route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        'import { stokFetch } from "@/lib/stok/client";\n'
        "export async function POST() { return stokFetch(); }\n",
        encoding="utf-8",
    )
    context.changes.record_created(route)

    result = await verifier.verify()

    assert result.ok is False
    assert any("yetki" in finding for finding in result.findings)


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
