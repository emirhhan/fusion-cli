import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { BrowserMoreMenu, DevServersMenu } from "./BrowserMenus";
import { OPEN_IN_BROWSER_EVENT, OPEN_LINKS_KEY, routeLinkToBrowser } from "./openLinks";

afterEach(() => { cleanup(); localStorage.clear(); });

function client(rows: Record<string, unknown>[] = []) {
  const request = vi.fn(async (name: string) => {
    if (name === "onizleme.yapilandirmalar") return { ok: true, otomatik_dogrulama: true, yapilandirmalar: rows };
    if (name === "onizleme.baslat") return { ok: true, url: "http://localhost:5173" };
    return { ok: true };
  });
  return { request } as unknown as ProtocolClient & { request: typeof request };
}

it("⋮ menüsü dört Claude seçeneğini sunar ve uygular (#439)", async () => {
  const c = client();
  const onKeep = vi.fn();
  const onClear = vi.fn();
  render(<BrowserMoreMenu client={c} keepCookies={false} onClearData={onClear} onKeepCookies={onKeep} />);
  fireEvent.click(screen.getByRole("button", { name: "Tarayıcı seçenekleri" }));
  fireEvent.click(screen.getByRole("checkbox", { name: /Keep cookies/ }));
  expect(onKeep).toHaveBeenCalledWith(true);
  const verify = screen.getByRole("checkbox", { name: /Auto-verify changes/ }) as HTMLInputElement;
  await waitFor(() => expect(verify.checked).toBe(true));
  fireEvent.click(verify);
  await waitFor(() => expect(c.request).toHaveBeenCalledWith("onizleme.otomatik_dogrulama", { deger: false }));
  fireEvent.click(screen.getByRole("checkbox", { name: /Open links in built-in browser/ }));
  expect(localStorage.getItem(OPEN_LINKS_KEY)).toBe("true");
  fireEvent.click(screen.getByRole("menuitem", { name: /Clear browsing data/ }));
  expect(onClear).toHaveBeenCalled();
});

it("Open links açıkken http bağlantısı Tarayıcı bölmesine yönlenir", () => {
  const seen = vi.fn();
  window.addEventListener(OPEN_IN_BROWSER_EVENT, seen);
  expect(routeLinkToBrowser("https://example.com")).toBe(false);
  localStorage.setItem(OPEN_LINKS_KEY, "true");
  expect(routeLinkToBrowser("mailto:a@b.c")).toBe(false);
  expect(routeLinkToBrowser("https://example.com")).toBe(true);
  expect(seen).toHaveBeenCalledTimes(1);
  window.removeEventListener(OPEN_IN_BROWSER_EVENT, seen);
});

it("Dev servers menüsü başlatır, durdurur ve hepsini durdurur", async () => {
  const rows = [
    { ad: "web", komut: "npm run dev", url: "http://localhost:5173", calisiyor: false },
    { ad: "api", komut: "npm run api", url: "http://localhost:8000", calisiyor: true },
  ];
  const c = client(rows);
  const onStarted = vi.fn();
  render(<DevServersMenu client={c} onStarted={onStarted} />);
  fireEvent.click(screen.getByRole("button", { name: "Dev servers" }));
  fireEvent.click(await screen.findByRole("button", { name: "Başlat" }));
  await waitFor(() => expect(onStarted).toHaveBeenCalledWith("http://localhost:5173"));
  fireEvent.click(screen.getByRole("button", { name: "Durdur" }));
  await waitFor(() => expect(c.request).toHaveBeenCalledWith("onizleme.durdur", { ad: "api" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Hepsini durdur" }));
  await waitFor(() => expect(c.request.mock.calls.filter(([name]) => name === "onizleme.durdur").length).toBe(2));
});
