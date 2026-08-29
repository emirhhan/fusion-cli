import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Icon } from "./Icon";

afterEach(cleanup);

describe("Icon", () => {
  it("dekoratif kullanıldığında erişilebilirlik ağacından gizlenir", () => {
    render(<Icon name="search" />);
    expect(screen.queryByRole("img")).toBeNull();
    expect(document.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("anlam taşıdığında erişilebilir bir ad sunar", () => {
    render(<Icon name="search" title="Ara" />);
    expect(screen.getByRole("img", { name: "Ara" })).toBeTruthy();
  });

  it("tüm ikonları ortak çizgi sözleşmesiyle çizer", () => {
    render(<Icon name="settings" />);
    const icon = document.querySelector("svg");
    expect(icon?.getAttribute("fill")).toBe("none");
    expect(icon?.getAttribute("stroke")).toBe("currentColor");
    expect(icon?.getAttribute("stroke-width")).toBe("1.75");
  });
});
