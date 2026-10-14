import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ModelPicker, type ModelOption } from "./ModelPicker";

afterEach(cleanup);

const options: ModelOption[] = [
  { deger: "/model ilk", etiket: "İlk model" },
  { deger: "/model son", etiket: "Son model" },
];

test("arama açılışta odağı alır ve listbox dışında kalır", () => {
  render(<ModelPicker active="ilk" options={options} onSelect={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
  const search = screen.getByRole("combobox", { name: "Model ara" });
  expect(document.activeElement).toBe(search);
  expect(screen.getByRole("listbox").contains(search)).toBe(false);
});

test("klavye son seçeneğe gider ve Enter ile seçer", () => {
  const onSelect = vi.fn();
  render(<ModelPicker active="ilk" options={options} onSelect={onSelect} />);
  fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
  const search = screen.getByRole("combobox", { name: "Model ara" });
  fireEvent.keyDown(search, { key: "ArrowDown" });
  fireEvent.keyDown(search, { key: "End" });
  fireEvent.keyDown(document.activeElement ?? search, { key: "Enter" });
  expect(onSelect).toHaveBeenCalledExactlyOnceWith("/model son");
  expect(screen.queryByRole("listbox")).toBeNull();
});

test("Escape aramadan tetikleyiciye odağı geri verir", () => {
  render(<ModelPicker active="ilk" options={options} onSelect={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: /Model:/ });
  fireEvent.click(trigger);
  const search = screen.getByRole("combobox", { name: "Model ara" });
  search.focus();
  fireEvent.keyDown(search, { key: "Escape" });
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

test("yükleme, hata ve boş katalog ayrı; hata yeniden denenebilir", () => {
  const retry = vi.fn();
  const { rerender } = render(<ModelPicker active="ilk" options={options} busy onSelect={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
  expect(screen.getByText("Modeller okunuyor…")).toBeTruthy();
  expect(screen.queryByText(/Seçilebilir model yok/)).toBeNull();
  expect(screen.getByRole("combobox", { name: "Model ara" }).getAttribute("aria-activedescendant")).toBeNull();
  rerender(<ModelPicker active="ilk" options={[]} error="Kaynak okunamadı" onRetry={retry} onSelect={vi.fn()} />);
  expect(screen.getByRole("alert").textContent).toContain("Kaynak okunamadı");
  expect(screen.queryByText(/Seçilebilir model yok/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
  expect(retry).toHaveBeenCalledOnce();
});

test("boş katalog sağlayıcı bağlantı yoluna gider", () => {
  const connect = vi.fn();
  render(<ModelPicker active="ilk" options={[]} onConnect={connect} onSelect={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
  fireEvent.click(screen.getByRole("button", { name: "Sağlayıcıya bağlan" }));
  expect(connect).toHaveBeenCalledOnce();
});

test("pending seçim tekrar çalıştırılamaz", () => {
  const onSelect = vi.fn();
  render(<ModelPicker active="ilk" options={options} pending onSelect={onSelect} />);
  fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
  const option = screen.getAllByRole("option")[0] as HTMLButtonElement;
  expect(option.disabled).toBe(true);
  fireEvent.click(option);
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
  expect(onSelect).not.toHaveBeenCalled();
});

test("hata düğmesinde Enter eski modeli seçmez ve doğal etkinleştirmeyi korur", () => {
  const onSelect = vi.fn(), onRetry = vi.fn();
  render(<ModelPicker active="ilk" options={options} error="Kaynak okunamadı" onRetry={onRetry} onSelect={onSelect} />);
  fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
  const retry = screen.getByRole("button", { name: "Yeniden dene" });
  retry.focus();
  expect(fireEvent.keyDown(retry, { key: "Enter" })).toBe(true);
  expect(onSelect).not.toHaveBeenCalled();
  fireEvent.click(retry);
  expect(onRetry).toHaveBeenCalledOnce();
});

test("klavye hedefi seçili modelden ayrı görünür ve combobox etkin seçeneği bildirir", () => {
  const scroll = vi.fn();
  render(<ModelPicker active="/model ilk" options={options} onSelect={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Model:/ }));
  const search = screen.getByLabelText("Model ara");
  const last = screen.getAllByRole("option")[1];
  last.scrollIntoView = scroll;
  fireEvent.keyDown(search, { key: "End" });
  expect(search.getAttribute("role")).toBe("combobox");
  expect(search.getAttribute("aria-expanded")).toBe("true");
  expect(search.getAttribute("aria-activedescendant")).toBe(last.id);
  expect(last.className).toContain("model-picker__option--active");
  expect(last.getAttribute("aria-selected")).toBe("false");
  expect(scroll).toHaveBeenCalledWith({ block: "nearest" });
});
