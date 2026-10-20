import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DepoUyarisi } from "./DepoUyarisi";

describe("DepoUyarisi", () => {
  it("tek projede hiçbir şey göstermez", () => {
    const { container } = render(<DepoUyarisi kok="/ev/proje" onAc={vi.fn()} projeler={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("proje deposunda uyarır ve seçilen projeyi tam yoluyla açar", () => {
    const onAc = vi.fn();
    const projeler = ["01-Projeler/fusion-cli", "sneaksup-wp", "a", "b", "c", "d"];
    render(<DepoUyarisi kok="/ev/Desktop/" onAc={onAc} projeler={projeler} />);

    expect(screen.getByRole("note", { name: "Proje deposu uyarısı" }).textContent).toContain("6 proje");
    expect(screen.getByText("+2 proje")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "fusion-cli" }));
    expect(onAc).toHaveBeenCalledWith("/ev/Desktop/01-Projeler/fusion-cli");
  });
});
