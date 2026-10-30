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

// Ölçüldü (30 Ekim): imza hatası ağ hatasından ayırt edilemiyor, relaunch hatası "tamamlanamadı" diyordu (U5-43).
it("imza hatası kurulumun güvenlik nedeniyle yapılmadığını söyler", async () => {
  mocks.check.mockResolvedValue({ version: "1.0.0", close: vi.fn().mockResolvedValue(undefined), downloadAndInstall: vi.fn().mockRejectedValue(new Error("signature verification failed")) });
  render(<UpdatePanel />);
  fireEvent.click(screen.getByText("Güncellemeleri kontrol et"));
  fireEvent.click(await screen.findByText("İndir, kur ve yeniden başlat"));
  await screen.findByText(/imza doğrulanamadığı için kurulum yapılmadı/);
});

it("kurulum başarılı ama yeniden başlatma düşerse kurulduğu söylenir", async () => {
  mocks.check.mockResolvedValue({ version: "1.0.0", close: vi.fn().mockResolvedValue(undefined), downloadAndInstall: vi.fn().mockResolvedValue(undefined) });
  mocks.relaunch.mockRejectedValue(new Error("izin yok"));
  render(<UpdatePanel />);
  fireEvent.click(screen.getByText("Güncellemeleri kontrol et"));
  fireEvent.click(await screen.findByText("İndir, kur ve yeniden başlat"));
  await screen.findByText(/kuruldu ama Fusion yeniden başlatılamadı/);
  expect(screen.queryByText(/Güncelleme tamamlanamadı/)).toBeNull();
});

it("çalışan görev varken kurulumu kapatır ve nedenini söyler (Q1-23)", async () => {
  const downloadAndInstall = vi.fn().mockResolvedValue(undefined);
  mocks.check.mockResolvedValue({ version: "1.0.0", close: vi.fn().mockResolvedValue(undefined), downloadAndInstall });
  render(<UpdatePanel turnRunning />);
  fireEvent.click(screen.getByText("Güncellemeleri kontrol et"));
  const install = await screen.findByText("İndir, kur ve yeniden başlat");
  expect(install.hasAttribute("disabled")).toBe(true);
  expect(screen.getByRole("alert").textContent).toMatch(/Çalışan bir görev var/);
  fireEvent.click(install);
  expect(downloadAndInstall).not.toHaveBeenCalled();
  expect(mocks.relaunch).not.toHaveBeenCalled();
});
