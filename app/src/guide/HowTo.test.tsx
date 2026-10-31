import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { HowTo } from "./HowTo";
import { GUIDE_TOPICS } from "./topics";

beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

it("bütün görevleri kısa, kapalı başlıklar olarak listeler; ekran görüntüsü yoktur", () => {
  const { container } = render(<HowTo />);
  const items = container.querySelectorAll("details.guide-howto__item");
  expect(items).toHaveLength(GUIDE_TOPICS.length);
  expect([...items].every((item) => !(item as HTMLDetailsElement).open)).toBe(true);
  expect(screen.queryAllByRole("img")).toHaveLength(0);
  expect(screen.getByText("Telefondan uzaktan kontrol")).toBeTruthy();
});

it("başlığa tıklayınca nerede olduğu ve adımlar açılır", () => {
  render(<HowTo />);
  const summary = screen.getByText("MCP sunucusu eklemek").closest("summary")!;
  fireEvent.click(summary);
  const item = summary.parentElement as HTMLDetailsElement;
  expect(item.open).toBe(true);
  expect(item.textContent).toContain("Profil menüsü → MCP bağlantıları.");
});

it("arama konuları süzer, eşleşenleri açık gösterir ve eşleşme yoksa bunu söyler", () => {
  const { container } = render(<HowTo />);
  fireEvent.change(screen.getByLabelText("Konularda ara"), { target: { value: "tailscale" } });
  const items = container.querySelectorAll("details.guide-howto__item");
  expect(items).toHaveLength(1);
  expect((items[0] as HTMLDetailsElement).open).toBe(true);
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
