import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../../protocol/client";
import { RoleModels } from "./RoleModels";

const roles = { agent: "gemini_web/main/auto", teacher: "", judge: "gemini_web/main/auto", candidates: ["gemini_web/main/auto"] };
const secenekler = [
  { model: "gemini_web/main/auto", etiket: "Gemini", grup: "Web oturumları", hazir: true, not: "" },
  { model: "codex_cli/default", etiket: "ChatGPT · Codex", grup: "Abonelik", hazir: true, not: "", arac: false },
];

function fakeClient() {
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "model.roller") return { ok: true, roller: roles, secenekler };
    return { ok: true, metin: "Kaydedildi.", roller: { ...roles, [String(data.rol)]: data.deger } };
  });
  return { client: { request } as unknown as ProtocolClient, request };
}

describe("RoleModels", () => {
  afterEach(cleanup);

  it("öğretmen modelini seçince kalıcı atama isteği gönderir", async () => {
    const { client, request } = fakeClient();
    render(<RoleModels client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "Öğretmene sor" }));
    fireEvent.click(await screen.findByRole("button", { name: /ChatGPT · Codex/ }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("model.rol_ata", { rol: "teacher", deger: "codex_cli/default" }));
  });

  it("Codex araç çağıramadığı için varsayılan model listesinde yoktur", async () => {
    const { client } = fakeClient();
    render(<RoleModels client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "Varsayılan model" }));
    await screen.findByRole("button", { name: /Gemini/ });
    expect(screen.queryByRole("button", { name: /ChatGPT · Codex/ })).toBeNull();
  });

  it("son adayı kaldırmaya izin vermez", async () => {
    const { client, request } = fakeClient();
    render(<RoleModels client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "Fusion adayları" }));
    fireEvent.click(await screen.findByRole("button", { name: /Gemini/, pressed: true }));
    expect(request).not.toHaveBeenCalledWith("model.rol_ata", expect.objectContaining({ rol: "candidates" }));
  });
});
