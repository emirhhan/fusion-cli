/** Ekip kartları: alt ajan olayları kendi kartına düşer, paralel ajanlar yan yana durur. */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

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
