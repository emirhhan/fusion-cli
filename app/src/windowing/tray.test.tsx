import { renderHook, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TRAY_STORAGE_KEY, readTrayEnabled, resetTrayCache, setTrayEnabled, useTray, type TepsiKoprusu } from "./tray";

afterEach(() => {
  localStorage.clear();
  resetTrayCache();
});

function kopru(): TepsiKoprusu & { ayarla: ReturnType<typeof vi.fn>; durum: ReturnType<typeof vi.fn> } {
  return { ayarla: vi.fn(async () => undefined), durum: vi.fn(async () => undefined) };
}

describe("tepsi köprüsü (P-064)", () => {
  it("varsayılan açık; 'false' saklanınca kapalı", () => {
    expect(readTrayEnabled()).toBe(true);
    localStorage.setItem(TRAY_STORAGE_KEY, "false");
    expect(readTrayEnabled()).toBe(false);
  });

  it("kabukta tercih kurulur ve çalışan sayısı ipucuna yazılır", () => {
    const k = kopru();
    const { rerender } = renderHook(({ n }: { n: number }) => useTray(n, k, () => true), { initialProps: { n: 0 } });
    expect(k.ayarla).toHaveBeenCalledWith(true);
    expect(k.durum).toHaveBeenLastCalledWith(0);
    rerender({ n: 2 });
    expect(k.durum).toHaveBeenLastCalledWith(2);
  });

  it("tercih kapatılınca simge kaldırılır ve durum yazılmaz", () => {
    const k = kopru();
    renderHook(() => useTray(1, k, () => true));
    act(() => setTrayEnabled(false));
    expect(k.ayarla).toHaveBeenLastCalledWith(false);
    const durumSayisi = k.durum.mock.calls.length;
    act(() => setTrayEnabled(false));
    expect(k.durum.mock.calls.length).toBe(durumSayisi);
  });

  it("Tauri kabuğu yoksa (tarayıcı/test) köprüye hiç dokunmaz", () => {
    const k = kopru();
    renderHook(() => useTray(3, k, () => false));
    expect(k.ayarla).not.toHaveBeenCalled();
    expect(k.durum).not.toHaveBeenCalled();
  });
});
