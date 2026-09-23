/** Takip önerisi rozetleri: turun kapanışının ardına düşen sonraki adımlar. */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Conversation, type Mesaj } from "./Conversation";
import { olayEkle } from "../protocol/olayAkisi";

afterEach(cleanup);

const ONERILER: Mesaj[] = [
  {
    rol: "oneriler",
    metin: "",
    oneriler: [
      { etiket: "Değişiklikleri gözden geçir", gorev: "Değişiklikleri gözden geçir." },
      { etiket: "Doğrulamayı çalıştır", gorev: "`pytest -q` çalıştır." },
    ],
  },
];

describe("takip önerileri — görünüm", () => {
  it("rozetleri listeler", () => {
    render(<Conversation mesajlar={ONERILER} onOneriSec={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Değişiklikleri gözden geçir" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Doğrulamayı çalıştır" })).toBeTruthy();
  });

  it("tıklayınca TAM görevi gönderir, etiketi değil", () => {
    // Etiket rozete sığsın diye kısaltılmıştır; gönderilecek olan tam görevdir.
    const onOneriSec = vi.fn();
    render(<Conversation mesajlar={ONERILER} onOneriSec={onOneriSec} />);
    fireEvent.click(screen.getByRole("button", { name: "Doğrulamayı çalıştır" }));
    expect(onOneriSec).toHaveBeenCalledWith("`pytest -q` çalıştır.");
  });

  it("geri çağırım yoksa rozet çizilmez", () => {
    // Tıklanmayan bir düğme göstermek, hiç göstermemekten kötüdür.
    render(<Conversation mesajlar={ONERILER} />);
    expect(screen.queryByRole("button", { name: "Doğrulamayı çalıştır" })).toBeNull();
  });
});

describe("takip önerileri — olay akışı", () => {
  it("FollowupsSuggested akışa öneri mesajı ekler", () => {
    const sonuc = olayEkle([], {
      olay: "FollowupsSuggested",
      items: [["Kaldığın yerden devam et", "Kaldığın yerden devam et."]],
    });
    expect(sonuc).toHaveLength(1);
    expect(sonuc[0].rol).toBe("oneriler");
    expect(sonuc[0].oneriler).toEqual([
      { etiket: "Kaldığın yerden devam et", gorev: "Kaldığın yerden devam et." },
    ]);
  });

  it("boş liste mesaj AÇMAZ", () => {
    // Kanıt yoksa öneri de yok; boş bir rozet satırı gürültüdür.
    expect(olayEkle([], { olay: "FollowupsSuggested", items: [] })).toEqual([]);
  });

  it("bozuk girdi atılır, akış bozulmaz", () => {
    const sonuc = olayEkle([], {
      olay: "FollowupsSuggested",
      items: [["iyi", "görev"], "bozuk", [1, 2]],
    });
    expect(sonuc[0].oneriler).toEqual([{ etiket: "iyi", gorev: "görev" }]);
  });

  it("öneriler çalışma bloğuna KATILMAZ", () => {
    // Öneri bir adım değil, turun kapanışının ardına düşen ayrı bir satırdır.
    const akis = olayEkle([], { olay: "ToolExecuted", arac: "read_file", sonuc: false });
    const sonrasi = olayEkle(akis, {
      olay: "FollowupsSuggested",
      items: [["devam", "devam et"]],
    });
    expect(sonrasi[sonrasi.length - 1].rol).toBe("oneriler");
    expect(sonrasi.length).toBeGreaterThan(akis.length);
  });
});
