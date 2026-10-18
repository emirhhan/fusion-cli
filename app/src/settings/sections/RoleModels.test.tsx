import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
  it("öğretmen modelini seçince kalıcı atama isteği gönderir", async () => {
    const { client, request } = fakeClient();
    render(<RoleModels client={client} />);
    const select = await screen.findByLabelText("Öğretmene sor modeli");
    fireEvent.change(select, { target: { value: "codex_cli/default" } });
    await waitFor(() => expect(request).toHaveBeenCalledWith("model.rol_ata", { rol: "teacher", deger: "codex_cli/default" }));
  });

  it("Codex araç çağıramadığı için varsayılan model listesinde yoktur", async () => {
    const { client } = fakeClient();
    render(<RoleModels client={client} />);
    const select = await screen.findByLabelText("Varsayılan model");
    expect(select.querySelector('option[value="codex_cli/default"]')).toBeNull();
  });

  it("son adayı kaldırmaya izin vermez", async () => {
    const { client, request } = fakeClient();
    render(<RoleModels client={client} />);
    const boxes = await screen.findAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    expect(request).not.toHaveBeenCalledWith("model.rol_ata", expect.objectContaining({ rol: "candidates" }));
  });
});
