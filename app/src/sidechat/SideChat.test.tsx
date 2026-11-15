import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { runAppAction, type AppActionDeps } from "../shortcuts/appActions";
import { DEFAULT_BINDINGS } from "../shortcuts/keys";
import { SideChat } from "./SideChat";

afterEach(cleanup);

it("yan soru yan_sohbet.sor ile gider, önceki yan geçmiş bağlam olarak taşınır (#444)", async () => {
  const request = vi.fn(async (_name: string, data: Record<string, unknown>) => ({ ok: true, metin: `yanıt ${(data.gecmis as unknown[]).length}` }));
  const client = { request } as unknown as ProtocolClient;
  render(<SideChat client={client} onClose={vi.fn()} />);
  const box = screen.getByLabelText("Yan soru");
  fireEvent.change(box, { target: { value: "Bu hata ne demek?" } });
  fireEvent.keyDown(box, { key: "Enter" });
  expect(await screen.findByText("yanıt 0")).toBeTruthy();
  fireEvent.change(box, { target: { value: "Peki çözüm?" } });
  fireEvent.click(screen.getByRole("button", { name: "Sor" }));
  expect(await screen.findByText("yanıt 2")).toBeTruthy();
  expect(request).toHaveBeenLastCalledWith("yan_sohbet.sor", {
    soru: "Peki çözüm?",
    gecmis: [{ rol: "kullanici", metin: "Bu hata ne demek?" }, { rol: "asistan", metin: "yanıt 0" }],
  });
});

it("hata gösterilir; Esc kapatır", async () => {
  const onClose = vi.fn();
  const client = { request: vi.fn(async () => ({ ok: false, metin: "Model yok" })) } as unknown as ProtocolClient;
  render(<SideChat client={client} onClose={onClose} />);
  fireEvent.change(screen.getByLabelText("Yan soru"), { target: { value: "x" } });
  fireEvent.click(screen.getByRole("button", { name: "Sor" }));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("Model yok"));
  fireEvent.keyDown(screen.getByLabelText("Yan soru"), { key: "Escape" });
  expect(onClose).toHaveBeenCalled();
});

it("⌘; varsayılanı yan_sohbet eylemidir; oturum yoksa çalışmaz", () => {
  expect(DEFAULT_BINDINGS["mod+;"]).toBe("yan_sohbet");
  const toggle = vi.fn();
  expect(runAppAction("yan_sohbet", { toggleSideChat: toggle } as unknown as AppActionDeps)).toBe(true);
  expect(toggle).toHaveBeenCalled();
  expect(runAppAction("yan_sohbet", {} as AppActionDeps)).toBe(false);
});
