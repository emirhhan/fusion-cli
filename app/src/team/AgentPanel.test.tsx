import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AgentPanel } from "./AgentPanel";
import type { AjanKarti } from "./ekipOlaylari";
afterEach(cleanup);
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
