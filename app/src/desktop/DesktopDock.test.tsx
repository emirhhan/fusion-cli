import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { DesktopDock, DOCK_POLL_MS } from "./DesktopDock";

afterEach(() => { cleanup(); vi.useRealTimers(); });
const target = { kind: "window", id: 12, pid: 34 };
function fakeClient(activity: Record<string, unknown> = { active: false }) {
  return { request: vi.fn(async (name: string) => {
    if (name === "masaustu.hedefler") return { ok: true, windows: [{ ...target, app: "Notlar", title: "Taslak", icon: "https://example.com/icon.png" }], tabs: [{ kind: "tab", id: 8, title: "Belgeler", url: "https://example.com" }] };
    if (name === "masaustu.etkinlik") return { ok: true, ...activity };
    if (name === "masaustu.onizleme") return { ok: true, pngBase64: "YWJj", width: 100, height: 80 };
    return { ok: true };
  }) } as unknown as ProtocolClient;
}

it("pencere ve sekmeyi tam hedef kimliğiyle odaklar; uzak simge yüklemez", async () => {
  const client = fakeClient();
  render(<DesktopDock client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "Notlar: Taslak penceresini öne getir" }));
  expect(client.request).toHaveBeenCalledWith("masaustu.odakla", { target });
  fireEvent.click(screen.getByRole("button", { name: "Belgeler sekmesini öne getir" }));
  expect(client.request).toHaveBeenCalledWith("masaustu.odakla", { target: { kind: "tab", id: 8 } });
  expect(screen.queryByRole("img")).toBeNull();
});

it("telefon ekranı izlese de ajan etkinliği olmadan önizleme istemez", async () => {
  const client = fakeClient({ active: false, etkin: [{ cihazId: "telefon" }] });
  render(<DesktopDock client={client} />);
  await screen.findByRole("button", { name: /Notlar:/ });
  expect(screen.queryByRole("region", { name: "Ajanın çalıştığı pencere" })).toBeNull();
  expect(client.request).not.toHaveBeenCalledWith("masaustu.onizleme", expect.anything());
});

it("yalnız ajan hedefini gösterir; kapatınca aynı etkinlikte tekrar açılmaz", async () => {
  vi.useFakeTimers();
  const client = fakeClient({ active: true, activityId: "islem-1", target, label: "Notları düzenliyor" });
  render(<DesktopDock client={client} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(client.request).toHaveBeenCalledWith("masaustu.onizleme", { target });
  expect(screen.getByAltText("Ajan hedefi: Notları düzenliyor").getAttribute("src")).toBe("data:image/png;base64,YWJj");
  fireEvent.click(screen.getByRole("button", { name: "Ajan önizlemesini kapat" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(DOCK_POLL_MS * 2); });
  expect(screen.queryByRole("region", { name: "Ajanın çalıştığı pencere" })).toBeNull();
  expect(vi.mocked(client.request).mock.calls.filter(([name]) => name === "masaustu.onizleme")).toHaveLength(1);
});

it("kare başarısızlığını eski görüntüyü canlı göstermeden bildirir ve zamanlayıcıyı temizler", async () => {
  vi.useFakeTimers();
  const client = fakeClient({ active: true, activityId: "islem-1", target, label: "Düzenliyor" });
  const request = vi.mocked(client.request);
  const original = request.getMockImplementation()!;
  let frames = 0;
  request.mockImplementation(async (...args) => args[0] === "masaustu.onizleme" && ++frames > 1
    ? { ok: false, metin: "Pencere kapandı." } : original(...args));
  const view = render(<DesktopDock client={client} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  await act(async () => { await vi.advanceTimersByTimeAsync(DOCK_POLL_MS); });
  expect(screen.getByRole("alert").textContent).toContain("Pencere kapandı.");
  expect(screen.queryByRole("img")).toBeNull();
  view.unmount();
  const calls = request.mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(DOCK_POLL_MS * 3); });
  expect(request).toHaveBeenCalledTimes(calls);
});

it("önceki hedef sorgusu bitmeden yenisini başlatmaz", async () => {
  vi.useFakeTimers();
  const client = fakeClient();
  vi.mocked(client.request).mockImplementation(() => new Promise(() => {}));
  render(<DesktopDock client={client} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(DOCK_POLL_MS * 4); });
  expect(vi.mocked(client.request).mock.calls.filter(([name]) => name === "masaustu.hedefler")).toHaveLength(1);
});

it("yeni etkinliği yeniden gösterir; önceki hedefin karesini taşımaz", async () => {
  vi.useFakeTimers();
  const state = { active: true, activityId: "islem-1", target, label: "İlk işlem" };
  const client = fakeClient(state);
  render(<DesktopDock client={client} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  fireEvent.click(screen.getByRole("button", { name: "Ajan önizlemesini kapat" }));
  Object.assign(state, { activityId: "islem-2", target: { kind: "window", id: 56, pid: 78 }, label: "Yeni işlem" });
  await act(async () => { await vi.advanceTimersByTimeAsync(DOCK_POLL_MS); });
  expect(screen.getByAltText("Ajan hedefi: Yeni işlem")).toBeTruthy();
  expect(client.request).toHaveBeenCalledWith("masaustu.onizleme", { target: { kind: "window", id: 56, pid: 78 } });
});

it.each([
  { active: true, activityId: "a", target: { kind: "tab", id: 8 } },
  { active: true, activityId: "a", target: { kind: "window", id: 12 } },
  { active: true, target },
])("doğrulanmamış pencere etkinliğinden ekran yakalamaz: %j", async (state) => {
  const client = fakeClient(state);
  render(<DesktopDock client={client} />);
  await screen.findByRole("button", { name: /Notlar:/ });
  expect(client.request).not.toHaveBeenCalledWith("masaustu.onizleme", expect.anything());
});

it("açık hedef listesini daraltıp yeniden açabilir", async () => {
  render(<DesktopDock client={fakeClient()} />);
  await screen.findByRole("button", { name: /Notlar:/ });
  const collapse = screen.getByRole("button", { name: "Masaüstü dock'unu daralt" });
  fireEvent.click(collapse);
  expect(screen.queryByRole("button", { name: /Notlar:/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Masaüstü dock'unu aç" }));
  expect(screen.getByRole("button", { name: /Notlar:/ })).toBeTruthy();
});
