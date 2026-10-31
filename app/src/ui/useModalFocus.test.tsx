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

describe("useModalFocus — işlenmiş Escape", () => {
  // Ölçüldü (31 Ekim): modalın üstündeki bir katman (palet, açılır liste) Escape'i kendi kapanışı için
  // işleyip `preventDefault` etse de window dinleyicisi modalı da kapatıyordu; yazılan metin gidiyordu.
  it("içerideki öğe Escape'i işlediyse modal kapanmaz", () => {
    const kapat = vi.fn();
    render(<Katman ad="ic" onClose={kapat} />);
    const dugme = screen.getByRole("button", { name: "ic-düğme" });
    dugme.addEventListener("keydown", (event) => event.preventDefault(), { once: true });
    fireEvent.keyDown(dugme, { key: "Escape" });
    expect(kapat).not.toHaveBeenCalled();
    fireEvent.keyDown(dugme, { key: "Escape" });
    expect(kapat).toHaveBeenCalledTimes(1);
  });
});

describe("useModalFocus — arka plan", () => {
  // Ölçüldü (30 Ekim, U6-37): modal #root içinde (portal değil) çizilince kök modalı içerdiği için
  // inert yapılmıyor, arka plan sekmeyle erişilebilir kalıyordu.
  it("modal uygulama kökünün içinde çizilse de kardeş arka plan inert olur ve kapanınca geri döner", () => {
    const kok = document.createElement("div");
    document.body.append(kok);
    const uygulama = (acik: boolean) => (
      <div>
        <main data-testid="arka"><button type="button">arka</button></main>
        {acik && <Katman ad="ic" onClose={() => undefined} />}
      </div>
    );
    const view = render(uygulama(true), { container: kok });
    const arka = screen.getByTestId("arka") as HTMLElement;
    expect(arka.inert).toBe(true);
    expect((screen.getByRole("dialog", { name: "ic" }) as HTMLElement).inert).toBeFalsy();
    view.rerender(uygulama(false));
    expect(arka.inert).toBeFalsy();
    view.unmount();
    kok.remove();
  });
});
