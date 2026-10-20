/** Sağ denetçide canlı alt ajan yaşam döngüsü ve olayların yeniden oynatılması. */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { olayEkle } from "../protocol/olayAkisi";
import type { Mesaj } from "../screens/Conversation";
import { AgentPanel, agentCardsForMessages } from "./AgentPanel";
import type { AjanKarti } from "./ekipOlaylari";

afterEach(cleanup);
const start = { olay: "SubAgentStarted", sub_id: "yardimci-fixture", task: "bilgi.txt dosyasını oku", title: "Yardımcı", started_at: 123 };
const tool = { olay: "ToolStarted", agent_id: "yardimci-fixture", name: "read_file", args: { path: "bilgi.txt" } };
const executed = { olay: "ToolExecuted", agent_id: "yardimci-fixture", name: "read_file", args: { path: "bilgi.txt" }, output: "doğrulanan içerik", outcome: "ok" };
const finish = { olay: "SubAgentFinished", sub_id: "yardimci-fixture", status: "completed", ok: true, summary: "İnceleme tamamlandı", tool_calls: 1 };

it("başlama, canlı araç ve terminal sonuç aynı sağ panel kartını günceller", () => {
  let messages: Mesaj[] = olayEkle([], start);
  const view = render(<AgentPanel ajanlar={agentCardsForMessages(messages)} canli />);
  expect(screen.getByText("Çalışıyor")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Yardımcı/ }));
  expect(screen.getByText("Başlıyor")).toBeTruthy();
  messages = olayEkle(messages, tool);
  view.rerender(<AgentPanel ajanlar={agentCardsForMessages(messages)} canli />);
  expect(screen.getByText("1 adım")).toBeTruthy();
  expect(screen.getAllByText(/bilgi.txt/).length).toBeGreaterThan(1);
  messages = olayEkle(olayEkle(messages, executed), finish);
  view.rerender(<AgentPanel ajanlar={agentCardsForMessages(messages)} canli />);
  expect(screen.getByText("Tamamlandı")).toBeTruthy();
  expect(screen.getByText("İnceleme tamamlandı")).toBeTruthy();
  expect(screen.getByText("doğrulanan içerik")).toBeTruthy();
  expect(screen.getByRole("button", { name: /Yardımcı/ }).getAttribute("aria-pressed")).toBe("true");
});

it("saklanmış tel olayları yeniden oynatılınca tamamlanan ajan ve araç izi korunur", () => {
  const wire = JSON.parse(JSON.stringify([start, tool, executed, finish])) as Record<string, unknown>[];
  const restored = wire.reduce<Mesaj[]>((messages, event) => olayEkle(messages, event), []);
  const cards = agentCardsForMessages(restored);
  render(<AgentPanel ajanlar={cards} canli={false} />);
  fireEvent.click(screen.getByRole("button", { name: /Yardımcı/ }));
  expect(cards[0].baslangic).toBe(123000);
  expect(cards[0].cagriSayisi).toBe(1);
  expect(screen.getByText("Tamamlandı")).toBeTruthy();
  expect(screen.getByText("doğrulanan içerik")).toBeTruthy();
});

const agent: AjanKarti = { id: "a", persona: "yardimci", unvan: "Araştırmacı", avatar: "yardimci", renk: "mavi", gorev: "Kaynakları incele", durum: "calisiyor", adimlar: [], baslangic: Date.now() };
it("seçilen ajanın canlı olaylarını günceller ve kaybolan seçimden döner", () => {
  const view = render(<AgentPanel ajanlar={[agent]} canli />);
  fireEvent.click(screen.getByRole("button", { name: /Araştırmacı/ }));
  expect(screen.getByRole("article").textContent).toContain("Başlıyor");
  view.rerender(<AgentPanel ajanlar={[{ ...agent, adimlar: [{ metin: "Dosyalar okunuyor", basladi: true }] }]} canli />);
  expect(screen.getByRole("article").textContent).toContain("Dosyalar okunuyor");
  view.rerender(<AgentPanel ajanlar={[]} canli={false} />);
  expect(screen.queryByRole("article")).toBeNull();
  expect(screen.getByText(/Henüz alt ajan/)).toBeTruthy();
});
it("biten turda ajanı çalışıyor göstermez", () => {
 render(<AgentPanel ajanlar={[agent]} canli={false} />);
 fireEvent.click(screen.getByRole("button", { name: /Araştırmacı/ }));
 expect(screen.getByRole("article").textContent).toContain("yarım kaldı");
});
it("aynı turdaki yönlendirme veya kuyruk mesajı çalışan ajanı kapatmaz", async () => {
 const { agentCardsForMessages } = await import("./AgentPanel");
 const cards = agentCardsForMessages([{ rol: "ekip", metin: "", ajanlar: [agent] }, { rol: "kullanici", metin: "Yeni iş" }]);
 expect(cards[0].durum).toBe("calisiyor");
});
