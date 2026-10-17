import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { HowTo } from "./HowTo";
import { markSeen } from "./progress";
import { GUIDE_TOPICS } from "./topics";

beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

it("bütün konuları gerçek ekran görüntüleriyle listeler", () => {
  render(<HowTo />);
  expect(screen.getAllByRole("img")).toHaveLength(GUIDE_TOPICS.length);
  expect(screen.getByRole("heading", { name: "Telefondan uzaktan erişim (Tailscale)", level: 3 })).toBeTruthy();
});

it("görülmeyen konuya Bakılmadı etiketi koyar, görüleni etiketlemez", () => {
  markSeen("chrome");
  render(<HowTo />);
  expect(screen.getAllByText("Bakılmadı")).toHaveLength(GUIDE_TOPICS.length - 1);
});

it("arama konuları süzer ve eşleşme yoksa bunu söyler", () => {
  render(<HowTo />);
  fireEvent.change(screen.getByLabelText("Konularda ara"), { target: { value: "tailscale" } });
  expect(screen.getAllByRole("img")).toHaveLength(1);
  fireEvent.change(screen.getByLabelText("Konularda ara"), { target: { value: "olmayan-şey" } });
  expect(screen.getByText("Bu aramayla eşleşen konu yok.")).toBeTruthy();
});

it("Ayarlar'da aç düğmesi ilgili bölümü bildirir", () => {
  const onOpenSettings = vi.fn();
  render(<HowTo onOpenSettings={onOpenSettings} />);
  fireEvent.change(screen.getByLabelText("Konularda ara"), { target: { value: "tailscale" } });
  fireEvent.click(screen.getByRole("button", { name: "Ayarlar'da aç" }));
  expect(onOpenSettings).toHaveBeenCalledWith("uzak");
});
