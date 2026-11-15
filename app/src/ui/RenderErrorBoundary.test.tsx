import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RenderErrorBoundary } from "./RenderErrorBoundary";

afterEach(cleanup);

function Patlayan(): never {
  throw new Error("bozuk tercih");
}

it("render hatasında boş pencere yerine uyarı ve yeniden yükle düğmesi çizer (U6-32)", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  render(<RenderErrorBoundary><Patlayan /></RenderErrorBoundary>);
  expect(screen.getByRole("alert").textContent).toContain("çizilemedi");
  expect(screen.getByRole("button", { name: "Yeniden yükle" })).toBeTruthy();
});

it("hata yoksa çocukları olduğu gibi çizer", () => {
  render(<RenderErrorBoundary><p>merhaba</p></RenderErrorBoundary>);
  expect(screen.getByText("merhaba")).toBeTruthy();
});
