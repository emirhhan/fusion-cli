import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";

afterEach(cleanup);

describe("EmptyState", () => {
  it("boş ekranda Fusion karakterini çizer; harf işareti kullanmaz", () => {
    const { container } = render(<EmptyState />);
    // Eskiden pixel "F" logosu duruyordu; kullanıcı karakterin kendisini istedi.
    expect(container.querySelector(".fusion-avatar")).toBeTruthy();
    expect(container.querySelector(".fusion-pixel")).toBeNull();
  });

  it("durum karakterin ifadesine yansır", () => {
    const { container } = render(<EmptyState durum="thinking" />);
    expect(container.querySelector(".fusion-avatar")?.getAttribute("data-state")).toBe("thinking");
  });

  it("önerileri gösterir", () => {
    render(<EmptyState />);
    expect(screen.getByRole("button", { name: "Yeni bir web projesi oluştur" })).toBeTruthy();
  });
});
