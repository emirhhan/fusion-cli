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

  it("meşgulken ekranda yalnız logo vardır: görünür yazı, çubuk, yüzde ve kart yoktur", () => {
    const { container } = render(
      <RuntimeSetup state="kuruluyor" progress={64} message="Çalışma zamanı kuruluyor" version="0.7.0" onRepair={vi.fn()} />,
    );
    expect(container.querySelector(".runtime-setup__mark img")).not.toBeNull();
    const notice = container.querySelector(".runtime-setup__notice") as HTMLElement;
    expect(notice.dataset.visible).toBe("false"); // yalnız ekran okuyucuya
    expect(container.textContent).not.toContain("%64");
    expect(container.querySelector("progress")).toBeNull();
    // Durum yine de ekran okuyucuya iletilir.
    expect(screen.getByRole("status").textContent).toBe("Çalışma zamanı kuruluyor");
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("64");
    expect(container.textContent).not.toContain("Sürüm");
  });

  it("onarım ve hata durumunda açıklama ve tek eylem görünür", () => {
    const { container, rerender } = render(
      <RuntimeSetup state="onarilabilir" progress={0} message="Dosyalar eksik" onRepair={vi.fn()} />,
    );
    expect((container.querySelector(".runtime-setup__notice") as HTMLElement).dataset.visible).toBe("true");
    expect(screen.getByRole("heading", { name: "Çalışma zamanı onarılmalı" })).toBeTruthy();
    rerender(<RuntimeSetup state="hata" progress={0} message="Olmadı" version="0.7.0" onRepair={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Fusion başlatılamadı" })).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.queryByRole("button", { name: "Çalışma zamanını onar" })).toBeNull();
    expect(container.querySelector("main")?.getAttribute("data-busy")).toBe("false");
  });
});
