"""Next rota kapısı: dinamik segment ve paket tabanlı rota yanlış pozitif vermez (A2-34, A2-35)."""

from __future__ import annotations

from fusion_cli.engines.agent.next_route_verify import NextRouteVerifier


def _istemci(kok):
    dosya = kok / "components/panelApi.ts"
    dosya.parent.mkdir(parents=True)
    dosya.write_text(
        "export const getPanel = (id: string) => fetch(`/api/panel/${id}`);\n", encoding="utf-8"
    )
    return dosya


async def test_tek_dinamik_segmentli_rota_404_bulgusu_vermez(tmp_path):
    istemci = _istemci(tmp_path)
    rota = tmp_path / "app/api/panel/[id]/route.ts"
    rota.parent.mkdir(parents=True)
    rota.write_text("export async function GET() { return Response.json({}); }\n")

    assert (await NextRouteVerifier(tmp_path, (istemci,)).verify()).ok


async def test_route_group_icindeki_dinamik_rota_da_sayilir(tmp_path):
    istemci = _istemci(tmp_path)
    rota = tmp_path / "app/api/panel/(v1)/[id]/route.ts"
    rota.parent.mkdir(parents=True)
    rota.write_text("export async function GET() { return Response.json({}); }\n")

    assert (await NextRouteVerifier(tmp_path, (istemci,)).verify()).ok


async def test_rotasi_olmayan_dinamik_cagri_hala_yakalanir(tmp_path):
    istemci = _istemci(tmp_path)

    sonuc = await NextRouteVerifier(tmp_path, (istemci,)).verify()

    assert not sonuc.ok and "/api/panel/*" in sonuc.findings[0]


async def test_npm_paketiyle_is_yapan_rota_taslak_sayilmaz(tmp_path):
    rota = tmp_path / "app/api/mail/route.ts"
    rota.parent.mkdir(parents=True)
    rota.write_text(
        'import { NextResponse } from "next/server";\n'
        'import nodemailer from "nodemailer";\n'
        "export async function POST(request: Request) {\n"
        "  await nodemailer.createTransport({}).sendMail({});\n"
        "  return NextResponse.json({ success: true });\n"
        "}\n",
        encoding="utf-8",
    )

    assert (await NextRouteVerifier(tmp_path, (rota,)).verify()).ok
