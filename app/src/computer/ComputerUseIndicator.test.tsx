import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ComputerUseIndicator } from "./ComputerUseIndicator";

afterEach(cleanup);

function client() {
  let listener: ((event: Record<string, unknown>) => void) | null = null;
  return {
    emit: (event: Record<string, unknown>) => act(() => listener?.(event)),
    onEvent: (f: (event: Record<string, unknown>) => void) => { listener = f; return () => { listener = null; }; },
  };
}

describe("ComputerUseIndicator", () => {
  it("olayla açılır, Esc ipucunu gösterir, Durdur turu keser", () => {
    const api = client();
    const onStop = vi.fn();
    render(<ComputerUseIndicator client={api} onStop={onStop} running />);
    expect(screen.queryByRole("status")).toBeNull();

    api.emit({ olay: "BilgisayarKullaniliyor", aktif: true, esc: true });
    expect(screen.getByRole("status").textContent).toContain("Fusion bilgisayarı kullanıyor · durdurmak için Esc");
    fireEvent.click(screen.getByRole("button", { name: "Durdur" }));
    expect(onStop).toHaveBeenCalledOnce();

    api.emit({ olay: "BilgisayarKullaniliyor", aktif: false });
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("tur bitince olay gelmese de kapanır", () => {
    const api = client();
    const { rerender } = render(<ComputerUseIndicator client={api} onStop={vi.fn()} running />);
    api.emit({ olay: "BilgisayarKullaniliyor", aktif: true, esc: false });
    expect(screen.getByRole("status").textContent).not.toContain("Esc");

    rerender(<ComputerUseIndicator client={api} onStop={vi.fn()} running={false} />);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("Esc ile durdurulunca nedeni söyler, yeni tur başlayınca kaybolur", () => {
    const api = client();
    const { rerender } = render(<ComputerUseIndicator client={api} onStop={vi.fn()} running />);
    api.emit({ olay: "BilgisayarKullaniliyor", aktif: true, esc: true });
    api.emit({ olay: "BilgisayarKullaniliyor", aktif: false, esc: false, esc_ile_durdu: true });
    rerender(<ComputerUseIndicator client={api} onStop={vi.fn()} running={false} />);
    expect(screen.getByRole("status").textContent).toContain("Esc ile durduruldu");
    expect(screen.queryByRole("button", { name: "Durdur" })).toBeNull();

    rerender(<ComputerUseIndicator client={api} onStop={vi.fn()} running />);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
