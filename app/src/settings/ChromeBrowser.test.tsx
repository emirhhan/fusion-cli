import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { ChromeBrowser, installChecks } from "./ChromeBrowser";

afterEach(cleanup);

it("Chrome bağlantısı başlatılınca port ve anahtarı gösterir, kapatılınca gizler", async () => {
  let running = false;
  const client = {
    request: vi.fn(async (name: string) => {
      if (name === "chrome.baslat") running = true;
      if (name === "chrome.durdur") running = false;
      return {
        ok: true,
        calisiyor: running,
        bagli: false,
        port: running ? 45123 : null,
        anahtar: name === "chrome.baslat" ? "eşleştirme-anahtarı" : null,
      };
    }),
  } as unknown as ProtocolClient;

  render(<ChromeBrowser client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "Bağlantıyı başlat" }));

  expect(await screen.findByDisplayValue("45123")).toBeTruthy();
  expect(screen.getByDisplayValue("eşleştirme-anahtarı")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Bağlantıyı kapat" }));
  await waitFor(() => expect(screen.queryByDisplayValue("eşleştirme-anahtarı")).toBeNull());
  expect(client.request).toHaveBeenCalledWith("chrome.durdur", {});
});

it("Eklentiyi kur düğmesi kurulumu başlatır, adımları gösterir ve doğrulamayı yansıtır", async () => {
  const client = {
    request: vi.fn(async (name: string) => {
      if (name === "chrome.kur") {
        return {
          ok: true, calisiyor: true, bagli: false, port: 1, anahtar: "a",
          eklenti_yuklu: false, eklenti_etkin: false, yol: "/x", adimlar: ["Geliştirici modunu aç."],
        };
      }
      return { ok: true, calisiyor: false, bagli: false, port: null, anahtar: null, eklenti_yuklu: false };
    }),
  } as unknown as ProtocolClient;

  render(<ChromeBrowser client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "Eklentiyi kur" }));

  expect(await screen.findByText("Geliştirici modunu aç.")).toBeTruthy();
  expect(client.request).toHaveBeenCalledWith("chrome.kur", {});
});

it("Kurulum tamamlanınca düğme kalkar", async () => {
  const client = {
    request: vi.fn(async () => ({
      ok: true, calisiyor: true, bagli: true, port: 1, anahtar: null, eklenti_yuklu: true, eklenti_etkin: true,
    })),
  } as unknown as ProtocolClient;
  render(<ChromeBrowser client={client} />);
  await screen.findByRole("button", { name: "Bağlantıyı kapat" });
  expect(screen.queryByRole("button", { name: "Eklentiyi kur" })).toBeNull();
});

it("installChecks yüklü-etkin ve eşleşme durumlarını ayırır", () => {
  expect(installChecks(null)).toEqual({ loaded: "off", paired: "off" });
  expect(installChecks({ ok: true, calisiyor: true, bagli: false, port: 1, anahtar: null, eklenti_yuklu: true, eklenti_etkin: false }))
    .toEqual({ loaded: "wait", paired: "wait" });
});
