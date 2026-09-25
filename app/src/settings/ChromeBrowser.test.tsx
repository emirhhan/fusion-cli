import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { ChromeBrowser } from "./ChromeBrowser";

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
