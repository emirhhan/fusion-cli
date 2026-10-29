import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useModalFocus } from "./useModalFocus";

function Katman({ ad, onClose }: { ad: string; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useModalFocus(ref, true, onClose);
  return <div aria-label={ad} ref={ref} role="dialog" tabIndex={-1}><button type="button">{ad}-düğme</button></div>;
}

afterEach(cleanup);

describe("useModalFocus — katmanlar", () => {
  // Ölçüldü (29 Ekim): her katman Escape'i window'da ayrı dinlediği için iç içe
  // iki modal tek tuşla birlikte kapanıyordu.
  it("Escape yalnız en üst katmanı kapatır", () => {
    const alt = vi.fn();
    const ust = vi.fn();
    const view = render(<Katman ad="alt" onClose={alt} />);
    const ustDiv = document.createElement("div");
    document.body.append(ustDiv);
    render(<Katman ad="ust" onClose={ust} />, { container: ustDiv });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(ust).toHaveBeenCalledTimes(1);
    expect(alt).not.toHaveBeenCalled();
    view.unmount();
  });

  it("üst katman kapanınca Escape alttakine döner", () => {
    const alt = vi.fn();
    const ust = vi.fn();
    render(<Katman ad="alt" onClose={alt} />);
    const ustDiv = document.createElement("div");
    document.body.append(ustDiv);
    const ustView = render(<Katman ad="ust" onClose={ust} />, { container: ustDiv });
    ustView.unmount();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(alt).toHaveBeenCalledTimes(1);
    expect(ust).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "alt" })).toBeTruthy();
  });
});
