import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button } from "./Button";

afterEach(cleanup);

describe("Button", () => {
  it("metinli düğmeyi varyantıyla sunar", () => {
    render(<Button variant="primary">Yeni görev</Button>);
    expect(screen.getByRole("button", { name: "Yeni görev" }).className).toContain(
      "ui-button--primary",
    );
  });

  it("yalnız ikonlu düğmeyi erişilebilir adıyla sunar", () => {
    render(<Button aria-label="Ara" icon="search" iconOnly />);
    expect(screen.getByRole("button", { name: "Ara" })).toBeTruthy();
  });

  it("yüklenirken işlemi kilitler ve durumu metinle açıklar", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Kaydet
      </Button>,
    );
    const button = screen.getByRole("button", { name: /kaydet/i });
    expect(button).toHaveProperty("disabled", true);
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText("Yükleniyor")).toBeTruthy();
  });
});
