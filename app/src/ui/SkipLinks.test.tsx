import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SKIP_TARGET_COMPOSER, SKIP_TARGET_MAIN, SkipLinks, focusSkipTarget } from "./SkipLinks";

afterEach(cleanup);

describe("SkipLinks (P-065)", () => {
  it("içeriğe atla hedefin içindeki ilk odaklanabilir denetime odaklanır", () => {
    render(
      <>
        <SkipLinks />
        <main id={SKIP_TARGET_MAIN} tabIndex={-1}><button type="button">İlk düğme</button></main>
        <footer id={SKIP_TARGET_COMPOSER}><textarea aria-label="Mesaj" /></footer>
      </>,
    );
    fireEvent.click(screen.getByRole("link", { name: "İçeriğe atla" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "İlk düğme" }));
    fireEvent.click(screen.getByRole("link", { name: "Mesaj kutusuna atla" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Mesaj"));
  });

  it("hedefte denetim yoksa hedefin kendisine odaklanır; hedef yoksa false döner", () => {
    render(<main id={SKIP_TARGET_MAIN} tabIndex={-1}>yalnız metin</main>);
    expect(focusSkipTarget(SKIP_TARGET_MAIN)).toBe(true);
    expect(document.activeElement?.id).toBe(SKIP_TARGET_MAIN);
    expect(focusSkipTarget("yok-boyle-bir-hedef")).toBe(false);
  });

  it("mesaj kutusu yokken ikinci bağlantı çizilmez", () => {
    render(<SkipLinks composer={false} />);
    expect(screen.queryByRole("link", { name: "Mesaj kutusuna atla" })).toBeNull();
    expect(screen.getByRole("link", { name: "İçeriğe atla" })).toBeTruthy();
  });
});
