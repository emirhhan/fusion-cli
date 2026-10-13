import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { Settings } from "./Settings";

afterEach(cleanup);

function draw(overrides: Partial<Parameters<typeof Settings>[0]> = {}) {
  const request = vi.fn(async (name: string) => {
    if (name === "kontrol.gateway_durdur") return { ok: false, metin: "API ucu işlem reddi." };
    if (name === "kontrol.durum") return {
      ok: true, kok: "/tmp/p3-test", gateway: { durum: "calisiyor", adres: "http://127.0.0.1" },
      izin: { mod: "auto" }, model: {}, saglayicilar: [],
    };
    return { ok: true };
  });
  render(<Settings client={{ request } as unknown as ProtocolClient} onClose={vi.fn()}
    onThemeChange={vi.fn()} themePreference="system" {...overrides} />);
  return request;
}

describe("Ayar mutasyonu ve içerik araması", () => {
  it("arama sonucu seçilince gerçek tema satırını odaklar", async () => {
    draw();
    fireEvent.click(screen.getByRole("button", { name: "İzinler" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Ayarları ara" }), { target: { value: "tema" } });
    fireEvent.click(screen.getByRole("button", { name: "Tema" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "Tema" })));
  });
  it("mode komutu beklerken ikinci mode isteğini engeller ve snapshot korur", async () => {
    const onRunCommand = vi.fn(() => new Promise<void>(() => undefined));
    draw({ onRunCommand });
    fireEvent.click(screen.getByRole("button", { name: "İzinler" }));
    await screen.findByText("/tmp/p3-test");
    const manual = screen.getByRole("button", { name: /Manuel/ });
    fireEvent.click(manual);
    fireEvent.click(manual);
    expect(onRunCommand).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /Otomatik/ }).getAttribute("aria-pressed")).toBe("true");
  });
  it("reddedilen mode değişiminin nedenini korur", async () => {
    draw({ onRunCommand: vi.fn(async () => { throw new Error("İzin değişimi reddedildi."); }) });
    fireEvent.click(screen.getByRole("button", { name: "İzinler" }));
    await screen.findByText("/tmp/p3-test");
    fireEvent.click(screen.getByRole("button", { name: /Manuel/ }));
    expect(await screen.findByText(/İzin değişimi reddedildi/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Otomatik/ }).getAttribute("aria-pressed")).toBe("true");
  });
  it("fulfilled başarısız gateway sonucunun nedenini korur ve ilgili işlemi yeniden dener", async () => {
    const request = draw();
    fireEvent.click(screen.getByRole("button", { name: "Gelişmiş" }));
    fireEvent.click(await screen.findByRole("button", { name: "Durdur" }));
    expect(await screen.findByText(/API ucu işlem reddi/)).toBeTruthy();
    expect(screen.getByText("http://127.0.0.1")).toBeTruthy();
    fireEvent.click(within(screen.getByText(/API ucu işlem reddi/).closest("p")!).getByRole("button", { name: "Yeniden dene" }));
    await waitFor(() => expect(request.mock.calls.filter(([name]) => name === "kontrol.gateway_durdur")).toHaveLength(2));
  });
  it("tema içeriği araması ilgili ayarı erişilebilir sonuç olarak sunar", () => {
    draw();
    fireEvent.change(screen.getByRole("searchbox", { name: "Ayarları ara" }), { target: { value: "tema" } });
    expect(screen.getByRole("button", { name: /Tema/ })).toBeTruthy();
    expect(screen.getByText(/1.*sonuç/).getAttribute("role")).toBe("status");
  });
  it("eşleşme bulunmayınca erişilebilir sonuç bilgisi verir", () => {
    draw();
    fireEvent.change(screen.getByRole("searchbox", { name: "Ayarları ara" }), { target: { value: "bulunmayacak-ayar" } });
    expect(screen.getByText(/sonuç bulunamadı/i).getAttribute("role")).toBe("status");
  });
});

it("yeni client yüklenirken ve reddedildiğinde eski gateway mutasyonu yapmaz", async () => {
  const oldRequest = vi.fn(async () => ({ ok: true, gateway: { durum: "calisiyor" }, model: {}, izin: {}, saglayicilar: [] }));
  let reject!: (reason: Error) => void;
  const nextRequest = vi.fn((name: string) => name === "kontrol.durum" ? new Promise((_, fail) => { reject = fail; }) : Promise.resolve({ ok: true }));
  const props = { onClose: vi.fn(), onThemeChange: vi.fn(), themePreference: "system" as const };
  const view = render(<Settings {...props} client={{ request: oldRequest } as unknown as ProtocolClient} />);
  fireEvent.click(screen.getByRole("button", { name: "Gelişmiş" }));
  await screen.findByRole("button", { name: "Durdur" });
  view.rerender(<Settings {...props} client={{ request: nextRequest } as unknown as ProtocolClient} />);
  fireEvent.click(screen.getByRole("button", { name: /Başlat/ }));
  expect(nextRequest.mock.calls.filter(([name]) => name === "kontrol.gateway_durdur" || name === "kontrol.gateway_baslat")).toHaveLength(0);
  await act(async () => reject(new Error("Yeni sahip erişilemiyor")));
  fireEvent.click(screen.getByRole("button", { name: /Başlat/ }));
  expect(nextRequest.mock.calls.filter(([name]) => name === "kontrol.gateway_durdur" || name === "kontrol.gateway_baslat")).toHaveLength(0);
});
it("senkron mode sonucu sonrası refresh bitmeden ikinci komut çalışmaz", async () => {
  let count = 0;
  const request = vi.fn(() => ++count === 1 ? Promise.resolve({ ok: true, kok: "/tmp/p3-test", izin: { mod: "auto" } }) : new Promise(() => undefined));
  const onRunCommand = vi.fn(() => ({ ok: true as const }));
  draw({ client: { request } as unknown as ProtocolClient, onRunCommand });
  fireEvent.click(screen.getByRole("button", { name: "İzinler" }));
  await screen.findByText("/tmp/p3-test");
  const manual = screen.getByRole("button", { name: /Manuel/ });
  fireEvent.click(manual);
  await act(async () => undefined);
  fireEvent.click(manual);
  expect(onRunCommand).toHaveBeenCalledTimes(1);
});
it("başka realm promise beklerken mode guard açık kalır", async () => {
  const frame = document.createElement("iframe"); document.body.append(frame);
  const ForeignPromise = (frame.contentWindow as unknown as { Promise: PromiseConstructor }).Promise;
  const onRunCommand = vi.fn(() => new ForeignPromise<void>(() => undefined));
  try {
    draw({ onRunCommand });
    fireEvent.click(screen.getByRole("button", { name: "İzinler" }));
    await screen.findByText("/tmp/p3-test");
    const manual = screen.getByRole("button", { name: /Manuel/ });
    fireEvent.click(manual); fireEvent.click(manual);
    expect(onRunCommand).toHaveBeenCalledTimes(1);
  } finally { frame.remove(); }
});
