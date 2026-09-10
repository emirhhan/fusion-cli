import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { UpdatePanel } from "./UpdatePanel";

const mocks = vi.hoisted(() => ({ check: vi.fn(), relaunch: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => true }));
vi.mock("@tauri-apps/plugin-updater", () => ({ check: mocks.check }));
vi.mock("@tauri-apps/plugin-process", () => ({ relaunch: mocks.relaunch }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("sunucu hatasında güncel demez ve yeniden denemeye izin verir", async () => {
  mocks.check.mockRejectedValue(new Error("offline"));
  render(<UpdatePanel />);
  fireEvent.click(screen.getByText("Güncellemeleri kontrol et"));
  await screen.findByText(/sunucusuna ulaşılamadı/);
  expect(screen.getByText("Güncellemeleri kontrol et").hasAttribute("disabled")).toBe(false);
});

it("imza veya kurulum hatasında yeniden başlatmaz", async () => {
  mocks.check.mockResolvedValue({ version: "1.0.0", close: vi.fn().mockResolvedValue(undefined), downloadAndInstall: vi.fn().mockRejectedValue(new Error("signature")) });
  render(<UpdatePanel />);
  fireEvent.click(screen.getByText("Güncellemeleri kontrol et"));
  fireEvent.click(await screen.findByText("İndir, kur ve yeniden başlat"));
  await screen.findByText(/Güncelleme tamamlanamadı/);
  expect(mocks.relaunch).not.toHaveBeenCalled();
});

it("başarılı kurulumdan sonra yeniden başlatır", async () => {
  mocks.check.mockResolvedValue({ version: "1.0.0", close: vi.fn().mockResolvedValue(undefined), downloadAndInstall: vi.fn().mockResolvedValue(undefined) });
  render(<UpdatePanel />);
  fireEvent.click(screen.getByText("Güncellemeleri kontrol et"));
  fireEvent.click(await screen.findByText("İndir, kur ve yeniden başlat"));
  await waitFor(() => expect(mocks.relaunch).toHaveBeenCalledOnce());
});
