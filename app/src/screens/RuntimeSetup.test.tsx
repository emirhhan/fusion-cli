import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RuntimeSetup } from "./RuntimeSetup";

afterEach(cleanup);

describe("RuntimeSetup", () => {
  it("kurulum ilerlemesini erişilebilir biçimde gösterir", () => {
    render(
      <RuntimeSetup
        state="kuruluyor"
        progress={42}
        message="Fusion hazırlanıyor"
        onRepair={vi.fn()}
      />,
    );

    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("42");
    expect(screen.getByText("Fusion hazırlanıyor")).toBeTruthy();
  });

  it("onarılabilir hatada tek onarım eylemi sunar", () => {
    const repair = vi.fn();
    render(
      <RuntimeSetup
        state="onarilabilir"
        progress={0}
        message="Dosyalar eksik"
        onRepair={repair}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Çalışma zamanını onar" }));
    expect(repair).toHaveBeenCalledOnce();
  });

  it("hazır olmayan normal durumda onarım düğmesi göstermez", () => {
    render(
      <RuntimeSetup
        state="denetleniyor"
        progress={0}
        message="Çalışma zamanı denetleniyor"
        onRepair={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button")).toBeNull();
  });
});
