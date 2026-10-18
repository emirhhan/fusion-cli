import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Conversation, type Mesaj } from "./Conversation";

afterEach(cleanup);
const messages: Mesaj[] = [
  { id: "u", rol: "kullanici", metin: "Projeyi yap" },
  { id: "n1", rol: "asistan", metin: "Dosyaları okuyorum", ara: true },
  { id: "e", rol: "olay", metin: "okundu", adimlar: [{ metin: "main.py okundu", arac: "read_file", durum: "ok" }] },
  { id: "n2", rol: "asistan", metin: "Testleri çalıştırıyorum", ara: true },
];

it("ara anlatımları tek kapalı ayrıntıda toplar, ana cevabı dışarıda tutar", () => {
  const { container } = render(<Conversation running={false} mesajlar={[...messages, { id: "a", rol: "asistan", metin: "Sonuç hazır" }]} />);
  const details = container.querySelector<HTMLDetailsElement>(".conversation__work-details");
  expect(details).toBeTruthy();
  expect(details?.open).toBe(false);
  expect(details?.textContent).toContain("Dosyaları okuyorum");
  expect(details?.textContent).toContain("main.py okundu");
  expect(details?.textContent).toContain("Testleri çalıştırıyorum");
  expect(details?.textContent).not.toContain("Sonuç hazır");
  expect(screen.getAllByRole("article", { name: "Fusion yanıtı" })).toHaveLength(1);
});

it("çalışırken son açıklamayı görünür tutar, önceki turu yeniden açmaz", () => {
  const { container } = render(<Conversation running mesajlar={messages} />);
  const latest = container.querySelector(".conversation__work-current");
  expect(latest?.textContent).toBe("Testleri çalıştırıyorum");
  expect(latest?.closest("details")).toBeNull();
  expect(container.querySelector(".conversation__work-details")?.textContent).toContain("Dosyaları okuyorum");
});

it("yeni kullanıcı mesajının iki tarafındaki çalışma ve hata durumlarını karıştırmaz", () => {
  const { container } = render(<Conversation running mesajlar={[
    ...messages,
    { id: "failure", rol: "olay", metin: "Başarısız", adimlar: [{ metin: "Başarısız", sonuc: "failed" }] },
    { id: "u2", rol: "kullanici", metin: "Devam et" },
    { id: "n3", rol: "asistan", metin: "Hatayı inceliyorum", ara: true },
  ]} />);
  expect(container.querySelectorAll(".conversation__work-details")).toHaveLength(1);
  expect(container.querySelector(".conversation__work-current")?.textContent).toBe("Hatayı inceliyorum");
  expect(container.querySelector(".activity__result")?.closest("details")).toBeNull();
  expect(container.querySelector(".activity__result")?.textContent).toBe("Tamamlanamadı");
});

it("görev listesi sınırında yalnız gerçek son araç canlı kalır", () => {
  const { container } = render(<Conversation running mesajlar={[
    ...messages.slice(0, 3),
    { id: "tasks", rol: "gorevler", metin: "Görevler", gorevler: [] },
    { id: "new-event", rol: "olay", metin: "test", adimlar: [{ metin: "Test çalışıyor", arac: "run_shell", basladi: true }] },
  ]} />);
  expect(container.querySelectorAll('.activity[data-state="running"]')).toHaveLength(1);
});

it("biten araçları canlı göstergede ikinci kez çizmez", () => {
  const { container } = render(<Conversation running mesajlar={messages} />);
  expect(screen.getAllByText("main.py okundu")).toHaveLength(1);
  expect(container.querySelector(".activity__summary")).toBeNull();
});

it("ara işaretli hata bile ana akışta raporlanabilir kalır", () => {
  const { container } = render(<Conversation running={false} onHataBildir={() => {}} mesajlar={[
    ...messages,
    { id: "error", rol: "asistan", metin: "Hata: Bağlantı kurulamadı", ara: true, hata: true },
  ]} />);
  expect(screen.getByText("Hata: Bağlantı kurulamadı").closest("details")).toBeNull();
  expect(screen.getByRole("button", { name: "Hatayı bildir" })).toBeTruthy();
  expect(container.querySelectorAll(".conversation__work-details")).toHaveLength(1);
});
