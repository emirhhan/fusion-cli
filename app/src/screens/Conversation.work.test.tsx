import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Conversation, type Mesaj } from "./Conversation";
afterEach(cleanup);
const messages: Mesaj[] = [
  { id: "u", rol: "kullanici", metin: "Projeyi yap" },
  { id: "n1", rol: "asistan", metin: "Dosyaları okuyorum", ara: true },
  { id: "e", rol: "olay", metin: "okundu", adimlar: [{ metin: "main.py okundu", arac: "read_file", durum: "ok" }] },
  { id: "n2", rol: "asistan", metin: "Testleri çalıştırıyorum", ara: true },
];
it("Codex gibi açıklamaları açık ve araç satırlarıyla aynı sırada gösterir", () => {
  const { container } = render(<Conversation running={false} mesajlar={[...messages, { id: "a", rol: "asistan", metin: "Sonuç hazır" }]} />);
  expect(container.querySelector(".conversation__work-details")).toBeNull();
  expect(screen.getAllByRole("article", { name: "Fusion yanıtı" })).toHaveLength(3);
  expect(screen.getByText("Dosyaları okuyorum").closest("details")).toBeNull();
  expect(screen.getByText("Testleri çalıştırıyorum").closest("details")).toBeNull();
  const rows = container.querySelectorAll(".conversation__message");
  expect(rows[1].textContent).toContain("Dosyaları okuyorum");
  expect(rows[2].querySelector("summary svg")).toBeTruthy();
  expect(rows[3].textContent).toContain("Testleri çalıştırıyorum");
});
it("yalnız araç ayrıntısını açar, açıklama paragraflarını saklamaz", () => {
  const {container} = render(<Conversation running={false} mesajlar={messages} />);
  const summary=container.querySelector(".activity__summary > summary")!;
  fireEvent.click(summary);
  expect(screen.getByText("Dosyaları okuyorum")).toBeTruthy();
  expect(screen.getByText("Testleri çalıştırıyorum")).toBeTruthy();
});
it("görev listesi sınırında yalnız gerçek son araç canlı kalır", () => {
  const { container } = render(<Conversation running mesajlar={[
    ...messages.slice(0, 3),
    { id: "tasks", rol: "gorevler", metin: "Görevler", gorevler: [] },
    { id: "new-event", rol: "olay", metin: "test", adimlar: [{ metin: "Test çalışıyor", arac: "run_shell", basladi: true }] },
  ]} />);
  expect(container.querySelectorAll('.activity[data-state="running"]')).toHaveLength(1);
});
it("hata ana akışta raporlanabilir kalır", () => {
  render(<Conversation running={false} onHataBildir={() => {}} mesajlar={[
    ...messages, { id: "error", rol: "asistan", metin: "Hata: Bağlantı kurulamadı", ara: true, hata: true },
  ]} />);
  expect(screen.getByText("Hata: Bağlantı kurulamadı").closest("details")).toBeNull();
  expect(screen.getByRole("button", { name: "Hatayı bildir" })).toBeTruthy();
});
it("alt ajan bitişini referanstaki gibi küçük ikonlu işlem satırında gösterir",()=>{
 const {container}=render(<Conversation running={false} mesajlar={[{id:'team',rol:'ekip',metin:'Ekip',ajanlar:[{id:'review',persona:'yardimci',unvan:'Review resume',avatar:'yardimci',renk:'mor',gorev:'İncele',durum:'bitti',adimlar:[],baslangic:1}]}]} />);
 expect(screen.getByText('Review resume çalışmayı bitirdi').closest('summary')?.querySelector('svg')).toBeTruthy();
 expect(container.querySelector('.team-cards')).toBeNull();
});
