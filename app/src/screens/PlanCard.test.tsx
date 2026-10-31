import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import capabilities from "../../src-tauri/capabilities/default.json";
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

// İnceleme bulgusu (yüksek): açılış başarısızsa kart sessiz kalmasın.
it("dosya açılamazsa kartta hata metni gösterir", async () => {
  const onOpen = vi.fn(async () => false);
  render(<PlanCard baslik="Plan" onOpen={onOpen} onReveal={vi.fn(async () => true)} yol="/tmp/plans/s-2.md" />);

  fireEvent.click(screen.getByRole("button", { name: "Editörde aç" }));

  expect((await screen.findByRole("alert")).textContent).toContain("açılamadı");
  expect(onOpen).toHaveBeenCalledTimes(1);
});

// İnceleme bulgusu (yüksek): `opener:default` open_path içermez; Tauri izni olmadan
// "Editörde aç" hiç çalışmıyordu. Yetki dosyası plan dizinini kapsamalı.
it("Tauri yetkileri open_path iznini plan dizini kapsamıyla verir", () => {
  const permissions = (capabilities as { permissions: unknown[] }).permissions;
  const openPath = permissions.find(
    (entry) => typeof entry === "object" && entry !== null && (entry as { identifier?: string }).identifier === "opener:allow-open-path",
  ) as { allow?: Array<{ path?: string }> } | undefined;

  expect(openPath).toBeDefined();
  const paths = (openPath?.allow ?? []).map((item) => item.path ?? "");
  expect(paths.some((path) => path.includes("fusion-cli"))).toBe(true);
});
