/** Ekip kartları: alt ajan olayları kendi kartına düşer, paralel ajanlar yan yana durur. */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { olayEkle } from "../protocol/olayAkisi";
import type { Mesaj } from "../screens/Conversation";
import { TeamCards } from "./TeamCards";

afterEach(cleanup);

function akit(olaylar: Record<string, unknown>[], baslangic: Mesaj[] = []): Mesaj[] {
  return olaylar.reduce<Mesaj[]>((mesajlar, olay) => olayEkle(mesajlar, olay), baslangic);
}

const BASLA_TASARIMCI = {
  olay: "SubAgentStarted",
  task: "ana sayfayı tasarla",
  sub_id: "tasarimci-1",
  persona: "tasarimci",
  title: "Arayüz Tasarımcısı",
  avatar: "tasarimci",
  color: "pembe",
  group_size: 2,
};
const BASLA_ARASTIRMACI = {
  ...BASLA_TASARIMCI,
  task: "rakip siteleri incele",
  sub_id: "arastirmaci-1",
  persona: "arastirmaci",
  title: "Araştırmacı",
  avatar: "arastirmaci",
  color: "turuncu",
};

describe("ekip olayları", () => {
  it("aynı anda başlayan ajanlar tek ekip mesajında toplanır", () => {
    const mesajlar = akit([BASLA_TASARIMCI, BASLA_ARASTIRMACI]);

    expect(mesajlar).toHaveLength(1);
    expect(mesajlar[0].rol).toBe("ekip");
    expect(mesajlar[0].ajanlar?.map((kart) => kart.unvan)).toEqual([
      "Arayüz Tasarımcısı",
      "Araştırmacı",
    ]);
  });

  it("alt ajanın adımı ana bloğa değil kendi kartına düşer", () => {
    const mesajlar = akit([
      BASLA_TASARIMCI,
      BASLA_ARASTIRMACI,
      { olay: "ToolStarted", name: "web_search", args: { query: "rakip" }, agent_id: "arastirmaci-1" },
      { olay: "ToolStarted", name: "write_file", args: { path: "index.html" }, agent_id: "tasarimci-1" },
    ]);

    expect(mesajlar.some((mesaj) => mesaj.rol === "olay")).toBe(false);
    const [tasarimci, arastirmaci] = mesajlar[0].ajanlar ?? [];
    expect(tasarimci.adimlar.map((adim) => adim.arac)).toEqual(["write_file"]);
    expect(arastirmaci.adimlar.map((adim) => adim.arac)).toEqual(["web_search"]);
  });

  it("bitiş olayı kartı sonucu ve süresiyle kapatır", () => {
    const mesajlar = akit([
      BASLA_TASARIMCI,
      {
        olay: "SubAgentFinished",
        sub_id: "tasarimci-1",
        ok: true,
        summary: "index.html hazır",
        elapsed_s: 42,
        tool_calls: 5,
      },
    ]);

    const kart = mesajlar[0].ajanlar?.[0];
    expect(kart?.durum).toBe("bitti");
    expect(kart?.ozet).toBe("index.html hazır");
    expect(kart?.sureSn).toBe(42);
  });

  it("tek ajan her seferinde kendi kartını açar", () => {
    const tek = { ...BASLA_TASARIMCI, group_size: 1 };
    const mesajlar = akit([tek, { ...tek, sub_id: "tasarimci-2" }]);

    expect(mesajlar.filter((mesaj) => mesaj.rol === "ekip")).toHaveLength(2);
  });

  it("ana ajanın olayları eskisi gibi ana bloğa gider", () => {
    const mesajlar = akit([{ olay: "ToolStarted", name: "read_file", args: { path: "a.ts" } }]);

    expect(mesajlar[0].rol).toBe("olay");
  });

  it("kartı olmayan alt ajan olayı ana bloğa sızmaz", () => {
    const mesajlar = akit([
      { olay: "ToolStarted", name: "read_file", args: { path: "a.ts" }, agent_id: "kayip" },
    ]);

    expect(mesajlar).toEqual([]);
  });
});

describe("ekip kartları", () => {
  it("paralel grubu başlık ve kişilik bilgisiyle çizer", () => {
    const mesajlar = akit([BASLA_TASARIMCI, BASLA_ARASTIRMACI]);

    render(<TeamCards ajanlar={mesajlar[0].ajanlar ?? []} canli />);

    expect(screen.getByRole("heading", { name: "2 ajan aynı anda çalışıyor" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Arayüz Tasarımcısı" })).toBeTruthy();
    expect(screen.getByText("rakip siteleri incele")).toBeTruthy();
    expect(screen.getAllByText(/çalışıyor/).length).toBeGreaterThan(0);
  });

  it("tur bittiği hâlde bitiş olayı gelmeyen ajan yarım görünür", () => {
    const mesajlar = akit([BASLA_TASARIMCI]);

    render(<TeamCards ajanlar={mesajlar[0].ajanlar ?? []} canli={false} />);

    expect(screen.getByText("yarım kaldı")).toBeTruthy();
  });

  it("bilinmeyen renk uydurulmaz, gri kullanılır", () => {
    const mesajlar = akit([{ ...BASLA_TASARIMCI, color: "fosfor" }]);

    const { container } = render(<TeamCards ajanlar={mesajlar[0].ajanlar ?? []} canli />);

    expect(container.querySelector(".agent-card")?.getAttribute("data-renk")).toBe("gri");
  });
});

it("tekrarlanan başlangıç bitmiş ajan kartını yeniden açmaz", () => {
  const start = { olay: "SubAgentStarted", sub_id: "same", task: "iş", started_at: 123 };
  const first = olayEkle([], start)!;
  const done = olayEkle(first, { olay: "SubAgentFinished", sub_id: "same", ok: true })!;
  const replay = olayEkle(done, start)!;
  const cards = replay.flatMap((message) => message.ajanlar ?? []);
  expect(cards).toHaveLength(1);
  expect(cards[0].durum).toBe("bitti");
  expect(cards[0].baslangic).toBe(123000);
});

it("tek ajan iptalini bir kez gönderir ve terminal olaya kadar bekler", async () => {
  const cards = akit([BASLA_TASARIMCI])[0].ajanlar!;
  const onCancel = vi.fn(async () => undefined);
  const view = render(<TeamCards ajanlar={cards} canli onCancel={onCancel} />);
  const button = screen.getByRole("button", { name: "Ajanı durdur" });
  fireEvent.click(button);
  fireEvent.click(button);
  await waitFor(() => expect(onCancel).toHaveBeenCalledOnce());
  expect(onCancel).toHaveBeenCalledWith("tasarimci-1");
  expect(screen.getByRole("button", { name: "Durduruluyor…" }).hasAttribute("disabled")).toBe(true);
  const finished = akit([BASLA_TASARIMCI, { olay: "SubAgentFinished", sub_id: "tasarimci-1", status: "cancelled", ok: false }])[0].ajanlar!;
  await act(async () => view.rerender(<TeamCards ajanlar={finished} canli onCancel={onCancel} />));
  expect(screen.getByText("iptal edildi")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Durduruluyor…" })).toBeNull();
});

it("başlangıçtan önce gelen terminal sonuç sonraki başlangıçta korunur", () => {
  const messages = akit([
    { olay: "SubAgentFinished", sub_id: "late", ok: false, status: "cancelled", summary: "İptal edildi" },
    { olay: "SubAgentStarted", sub_id: "late", task: "araştır", title: "Araştırmacı", started_at: 123 },
  ]);
  const cards = messages.flatMap((message) => message.ajanlar ?? []);
  expect(cards).toHaveLength(1);
  expect(cards[0].durum).toBe("iptal");
  expect(cards[0].gorev).toBe("araştır");
  expect(cards[0].baslangic).toBe(123000);
});
