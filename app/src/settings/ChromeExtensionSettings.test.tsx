import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { ChromeExtensionSettings } from "./ChromeExtensionSettings";

afterEach(cleanup);

type Shortcut = { ad: string; metin: string };

function fakeClient(initial: Shortcut[] = [], monitor = true) {
  let shortcuts = [...initial];
  let acik = monitor;
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "chrome.izleme") {
      if (typeof data.acik === "boolean") acik = data.acik;
      return { ok: true, acik };
    }
    if (name === "chrome.kisayollar") return { ok: true, kisayollar: shortcuts };
    if (name === "chrome.kisayol_kaydet") {
      shortcuts = [...shortcuts.filter((s) => s.ad !== data.ad), { ad: String(data.ad), metin: String(data.metin) }];
      return { ok: true, kisayollar: shortcuts };
    }
    if (name === "chrome.kisayol_sil") {
      shortcuts = shortcuts.filter((s) => s.ad !== data.ad);
      return { ok: true, kisayollar: shortcuts };
    }
    return { ok: false, metin: "bilinmeyen" };
  });
  return { request } as unknown as ProtocolClient & { request: ReturnType<typeof vi.fn> };
}

it("bağlıyken izleme anahtarını ve kısayolları eklentiden okur, anahtarı değiştirir", async () => {
  const client = fakeClient([{ ad: "ozet", metin: "Bu sayfayı özetle." }], true);
  render(<ChromeExtensionSettings client={client} />);

  const toggle = (await screen.findByLabelText("Konsol ve ağ isteklerini izle")) as HTMLInputElement;
  expect(toggle.checked).toBe(true);
  expect(await screen.findByText("/ozet")).toBeTruthy();

  fireEvent.click(toggle);
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("chrome.izleme", { acik: false }));
  await waitFor(() => expect(toggle.checked).toBe(false));
});

it("kısayol kaydeder ve kaldırır; ad boşsa köprüye gitmez", async () => {
  const client = fakeClient();
  render(<ChromeExtensionSettings client={client} />);
  expect(await screen.findByText("Henüz kısayol yok.")).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "Kısayolu kaydet" }));
  expect(client.request).not.toHaveBeenCalledWith("chrome.kisayol_kaydet", expect.anything());
  expect(screen.getByRole("alert").textContent).toContain("ad");

  fireEvent.change(screen.getByLabelText("Kısayol adı"), { target: { value: "/cevir" } });
  fireEvent.change(screen.getByLabelText("Görev"), { target: { value: "Sayfayı çevir." } });
  fireEvent.click(screen.getByRole("button", { name: "Kısayolu kaydet" }));

  expect(await screen.findByText("/cevir")).toBeTruthy();
  expect(client.request).toHaveBeenCalledWith("chrome.kisayol_kaydet", { ad: "cevir", metin: "Sayfayı çevir." });
  expect((screen.getByLabelText("Kısayol adı") as HTMLInputElement).value).toBe("");

  fireEvent.click(screen.getByRole("button", { name: "/cevir kısayolunu kaldır" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("chrome.kisayol_sil", { ad: "cevir" }));
  expect(await screen.findByText("Henüz kısayol yok.")).toBeTruthy();
});

it("eklenti ayarları okunamazsa hatayı gösterir, kartı düşürmez", async () => {
  const client = { request: vi.fn(async () => ({ ok: false, metin: "Chrome eklentisi bağlı değil." })) } as unknown as ProtocolClient;
  render(<ChromeExtensionSettings client={client} />);

  expect((await screen.findByRole("alert")).textContent).toContain("bağlı değil");
  expect(screen.getByLabelText("Konsol ve ağ isteklerini izle")).toBeTruthy();
});
