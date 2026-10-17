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

  it("yüzde bilinmiyorsa belirsiz çubuk ve 'Birazdan hazır', biliniyorsa dolgu ölçeği gösterir", () => {
    const { container, rerender } = render(
      <RuntimeSetup state="kuruluyor" progress={0} message="Hazırlanıyor" onRepair={vi.fn()} />,
    );
    expect(screen.getByText("Birazdan hazır")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("data-indeterminate")).toBe("true");
    rerender(<RuntimeSetup state="kuruluyor" progress={64} message="Hazırlanıyor" onRepair={vi.fn()} />);
    expect(screen.getByText("%64")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("data-indeterminate")).toBe("false");
    expect((container.querySelector(".runtime-setup__track span") as HTMLElement).style.transform).toBe("scaleX(0.64)");
  });

  it("camlı kartta marka logosu, aurora zemini ve süren iş için dönen halka vardır; hata durumunda halka durur", () => {
    const { container, rerender } = render(
      <RuntimeSetup state="denetleniyor" progress={0} message="Denetleniyor" onRepair={vi.fn()} />,
    );
    expect(container.querySelector(".runtime-setup__aurora")).not.toBeNull();
    expect(container.querySelector(".runtime-setup__card img")).not.toBeNull();
    expect(container.querySelector("main")?.getAttribute("data-busy")).toBe("true");
    rerender(<RuntimeSetup state="hata" progress={0} message="Olmadı" onRepair={vi.fn()} />);
    expect(container.querySelector("main")?.getAttribute("data-busy")).toBe("false");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});
