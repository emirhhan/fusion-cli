import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PlanCard } from "./PlanCard";

afterEach(cleanup);

// P-025: plan dosyası kartı yolu gösterir ve dosyayı editörde açar.
it("plan yolunu gösterir ve düğmeler dosyayı açar / konumunu gösterir", () => {
  const onOpen = vi.fn(async () => true);
  const onReveal = vi.fn(async () => true);
  render(<PlanCard baslik="Giriş ekranı" onOpen={onOpen} onReveal={onReveal} yol="/tmp/plans/s-1.md" />);

  expect(screen.getByText("Giriş ekranı")).toBeTruthy();
  expect(screen.getByText("/tmp/plans/s-1.md")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Editörde aç" }));
  fireEvent.click(screen.getByRole("button", { name: "Konumunu göster" }));
  expect(onOpen).toHaveBeenCalledWith("/tmp/plans/s-1.md");
  expect(onReveal).toHaveBeenCalledWith("/tmp/plans/s-1.md");
});
