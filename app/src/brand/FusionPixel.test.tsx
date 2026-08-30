import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FusionPixel } from "./FusionPixel";
import { SourceIcon } from "./SourceIcon";

describe("Fusion marka görselleri", () => {
  it("pixel karakteri dekoratif olarak erişilebilirlik ağacından çıkarır", () => {
    const { container } = render(<FusionPixel />);
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("bilinen kaynakları gerçek eşlemesine, bilinmeyeni Fusion yedeğine yollar", () => {
    const { container, rerender } = render(<SourceIcon source="claude" />);
    expect(container.querySelector('[data-source="claude"]')).toBeTruthy();
    rerender(<SourceIcon source="codex" />);
    expect(container.querySelector('[data-source="codex"]')).toBeTruthy();
    rerender(<SourceIcon source="bilinmeyen" />);
    expect(container.querySelector('[data-source="fusion"]')).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});
