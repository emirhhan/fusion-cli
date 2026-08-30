import { describe, expect, it } from "vitest";
import { olayEkle } from "./olayAkisi";
import type { Mesaj } from "../screens/Conversation";

const DUSUNUYOR = { olay: "ModelCallStarted", role: "agent", model: "openrouter/x" };

describe("olayEkle", () => {
  it("ardışık adımları TEK blokta toplar", () => {
    let mesajlar: Mesaj[] = [];
    mesajlar = olayEkle(mesajlar, DUSUNUYOR);
    mesajlar = olayEkle(mesajlar, DUSUNUYOR);

    expect(mesajlar).toHaveLength(1);
    expect(mesajlar[0].adimlar).toHaveLength(2);
  });

  it("blok başlığı son yapılan işi gösterir", () => {
    let mesajlar = olayEkle([], DUSUNUYOR);
    mesajlar = olayEkle(mesajlar, { olay: "ToolExecuted", name: "write_file", args: { path: "a.py" } });

    expect(mesajlar[0].metin).toBe("araç çalıştı: write_file");
  });

  it("tur sonucu ayrı satırda durur", () => {
    let mesajlar = olayEkle([], DUSUNUYOR);
    mesajlar = olayEkle(mesajlar, { olay: "TurnOutcome", status: "completed" });

    expect(mesajlar).toHaveLength(2);
    expect(mesajlar[1].metin).toBe("görev tamamlandı");
  });

  it("sonuçtan sonra gelen adım yeni bir blok açar", () => {
    let mesajlar = olayEkle([], DUSUNUYOR);
    mesajlar = olayEkle(mesajlar, { olay: "TurnOutcome", status: "completed" });
    mesajlar = olayEkle(mesajlar, DUSUNUYOR);

    expect(mesajlar).toHaveLength(3);
  });

  it("araya giren kullanıcı mesajı bloğu kapatır", () => {
    let mesajlar = olayEkle([], DUSUNUYOR);
    mesajlar = [...mesajlar, { rol: "kullanici", metin: "dur" }];
    mesajlar = olayEkle(mesajlar, DUSUNUYOR);

    expect(mesajlar).toHaveLength(3);
  });

  it("tanınmayan olay akışı değiştirmez", () => {
    const mesajlar: Mesaj[] = [];
    expect(olayEkle(mesajlar, { olay: "Bilinmeyen" })).toBe(mesajlar);
  });
});
