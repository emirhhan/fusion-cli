import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Conversation, type Mesaj } from "./Conversation";

afterEach(cleanup);
const step = (n: number, detail = true) => ({ metin: `İşlem ${n}`, arac: "run_shell", durum: "ok", ...(detail ? { komut: `komut${n}`, cikti: `Çıktı ${n}` } : {}) });
const messages = (count: number): Mesaj[] => [
  { id: "u", rol: "kullanici", metin: "İşi yap" },
  ...Array.from({ length: count }, (_, n): Mesaj => ({ id: `event-${n}`, rol: "olay", metin: "", adimlar: [step(n + 1)] })),
  { id: "answer", rol: "asistan", metin: "Yanıt hazır" },
];
it.each([1, 2])("%i işlem normal bitmiş turda ayrı açılır satır olarak görünür", count => {
  const { container } = render(<Conversation running={false} mesajlar={messages(count)} />);
  expect(container.querySelectorAll(".activity__trail-item")).toHaveLength(count);
  for (let n = 1; n <= count; n++) {
    const row = screen.getByText(`İşlem ${n}`).closest("details")!;
    expect(row.closest(".conversation__work-details")).toBeNull();
    fireEvent.click(within(row).getByText(`İşlem ${n}`));
    expect(row.open).toBe(true);
  }
});
it("olay blokları toplamında iki önizleme; seçilen dahil tümü iç panelde", () => {
  const { container } = render(<Conversation running={false} mesajlar={messages(5)} />);
  expect(container.querySelectorAll(".activity__trail-item")).toHaveLength(2);
  expect(screen.queryByText("İşlem 3")).toBeNull();
  fireEvent.click(screen.getByText("İşlem 2"));
  const panel = screen.getByRole("region", { name: "İşlem ayrıntıları" });
  expect(within(panel).getAllByText(/^İşlem \d$/)).toHaveLength(5);
  expect(container.querySelectorAll(".activity__trail-item")).toHaveLength(5);
  expect(within(panel).getByText("İşlem 2").closest("details")?.open).toBe(true);
  expect(screen.getByText("Yanıt hazır").closest(".work-activity-panel")).toBeNull();
  fireEvent.click(within(panel).getByRole("button", { name: "İşlem panelini kapat" }));
  expect(screen.queryByRole("region", { name: "İşlem ayrıntıları" })).toBeNull();
  expect(document.activeElement?.textContent).toContain("İşlem 2");
});
it("ayrıntısız ve süren işlemler de dürüst açılır satırdır", () => {
  render(<Conversation running mesajlar={[{ id: "e", rol: "olay", metin: "", adimlar: [step(1, false), { metin: "İşlem sürüyor", arac: "read_file", basladi: true }] }]} />);
  fireEvent.click(screen.getByText("İşlem 1"));
  expect(screen.getByText("Bu işlem için ek ayrıntı yok.")).toBeTruthy();
  fireEvent.click(screen.getByText("İşlem sürüyor"));
  expect(screen.getByText("İşlem sürüyor; çıktı henüz gelmedi.")).toBeTruthy();
});
it("ikinci açıkken üçüncü işlem gelmesi ve yeni akış ayrıntıyı korur", () => {
  const { rerender } = render(<Conversation running mesajlar={messages(2).slice(0, -1)} />);
  fireEvent.click(screen.getByText("İşlem 2"));
  rerender(<Conversation running mesajlar={messages(3).slice(0, -1)} />);
  let panel = screen.getByRole("region", { name: "İşlem ayrıntıları" });
  expect(within(panel).getByText("İşlem 2").closest("details")?.open).toBe(true);
  rerender(<Conversation running mesajlar={messages(4).slice(0, -1)} />);
  panel = screen.getByRole("region", { name: "İşlem ayrıntıları" });
  expect(within(panel).getByText("İşlem 2").closest("details")?.open).toBe(true);
  expect(within(panel).getByText("İşlem 4")).toBeTruthy();
});
it("Escape paneli kapatır ve üstteki iptal işleyicisine ulaşmaz", () => {
  const cancel = vi.fn();
  render(<div onKeyDown={event => { if (event.key === "Escape") cancel(); }}><Conversation running mesajlar={messages(3)} /></div>);
  fireEvent.click(screen.getByText("İşlem 1"));
  fireEvent.keyDown(screen.getByRole("region", { name: "İşlem ayrıntıları" }), { key: "Escape" });
  expect(cancel).not.toHaveBeenCalled();
  expect(screen.queryByRole("region", { name: "İşlem ayrıntıları" })).toBeNull();
});
it("ara anlatım, görevler ve özgün yanıt indisi panelden bağımsızdır", () => {
  const follow = vi.fn();
  const list: Mesaj[] = [...messages(4).slice(0, -1),
    { id: "narration", rol: "asistan", metin: "Açıklama görünür", ara: true },
    { id: "tasks", rol: "gorevler", metin: "", gorevler: [{ metin: "Görev görünür", durum: "yapiliyor" }] },
    { id: "result", rol: "asistan", metin: "Nihai yanıt" }];
  render(<Conversation running={false} mesajlar={list} onContinueInNewChat={follow} />);
  fireEvent.click(screen.getByText("İşlem 1"));
  expect(screen.getByText("Açıklama görünür").closest(".work-activity-panel")).toBeNull();
  expect(screen.getByText("Görev görünür").closest(".work-activity-panel")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Yeni sohbette devam et" }));
  expect(follow).toHaveBeenCalledWith(7);
});

it("iki önizlemenin arkasındaki canlı işlem tamamlanmış gibi görünmez", () => {
  const items = messages(3).slice(0, -1);
  items[3] = { ...items[3], adimlar: [{ metin: "İşlem 3", arac: "run_shell", basladi: true }] };
  render(<Conversation running mesajlar={items} />);
  expect(screen.getByText("3 işlem · 1 sürüyor · tümünü görmek için bir satırı aç")).toBeTruthy();
  fireEvent.click(screen.getByText("İşlem 1"));
  expect(screen.getByRole("region", { name: "İşlem ayrıntıları" }).textContent).toContain("3 işlem · 1 sürüyor");
});

it("birçok başarısız olay iki işlem önizlemesi ve tek sonuç satırı bırakır", () => {
  const items: Mesaj[] = Array.from({ length: 20 }, (_, i) => ({ id: `failed-${i}`, rol: "olay", metin: "",
    adimlar: [{ ...step(i + 1), durum: "failed" }, { metin: "Tur bitti", sonuc: "failed" }] }));
  const { container } = render(<Conversation running={false} mesajlar={items} />);
  expect(container.querySelectorAll(".activity__trail-item")).toHaveLength(2);
  expect(container.querySelectorAll(".conversation__message--event")).toHaveLength(1);
  expect(container.querySelectorAll(".activity__result")).toHaveLength(1);
  expect(container.querySelector(".activity__result")?.textContent).toBe("Tamamlanamadı");
  expect(screen.getByText("20 işlem · 20 başarısız · tümünü görmek için bir satırı aç")).toBeTruthy();
});
