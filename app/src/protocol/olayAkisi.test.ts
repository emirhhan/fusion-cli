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

  it("plan olaylarını tek açılabilir çalışma bloğunda toplar", () => {
    let mesajlar = olayEkle([], { olay: "ExecutionPlanCreated", plan_id: "p", total_steps: 2 });
    mesajlar = olayEkle(mesajlar, {
      olay: "ExecutionStepStarted", index: 1, total_steps: 2, goal: "incele",
    });

    expect(mesajlar).toHaveLength(1);
    expect(mesajlar[0].adimlar).toHaveLength(2);
    expect(mesajlar[0].metin).toBe("adım 1/2 başladı");
  });
});

describe("değişiklik kartı", () => {
  it("başarılı yazmanın diff'ini kalıcı bir mesaj olarak ekler", () => {
    const sonuc = olayEkle([], {
      olay: "ToolExecuted",
      name: "write_file",
      outcome: "ok",
      args: { path: "scripts/Player.gd" },
      diff: "--- a\n+++ b\n+var speed = 320",
    });

    const degisiklik = sonuc.find((mesaj) => mesaj.rol === "degisiklik");
    expect(degisiklik?.metin).toBe("scripts/Player.gd");
    expect(degisiklik?.diff).toContain("var speed = 320");
  });

  /* Engellenen bir yazmanın diff'ini göstermek, yapılmamış bir değişikliği
     yapılmış gibi sunardı — kullanıcının ölçülmüş şikayetinin tam merkezi. */
  it("engellenen yazmada diff kartı çıkarmaz", () => {
    const sonuc = olayEkle([], {
      olay: "ToolExecuted",
      name: "write_file",
      outcome: "blocked",
      args: { path: "project.godot" },
      diff: "--- a\n+++ b\n+config_version=5",
    });

    expect(sonuc.some((mesaj) => mesaj.rol === "degisiklik")).toBe(false);
  });
});

describe("akan cevap", () => {
  const PARCA = (text: string, extra: Record<string, unknown> = {}) => ({
    olay: "TokenReceived",
    channel: "main",
    text,
    ...extra,
  });

  it("gelen parçaları tek bir asistan balonunda biriktirir", () => {
    let mesajlar = olayEkle([], PARCA("Kask seçerken "));
    mesajlar = olayEkle(mesajlar, PARCA("önce sertifikaya bak."));

    const akan = mesajlar.filter((mesaj) => mesaj.rol === "asistan");
    expect(akan).toHaveLength(1);
    expect(akan[0].metin).toBe("Kask seçerken önce sertifikaya bak.");
    expect(akan[0].akan).toBe(true);
  });

  it("yeni model çağrısı başlayınca biriken metin sıfırlanır", () => {
    let mesajlar = olayEkle([], PARCA("ilk cevabın taslağı"));
    mesajlar = olayEkle(mesajlar, DUSUNUYOR);
    mesajlar = olayEkle(mesajlar, PARCA("ikinci cevap"));

    const akan = mesajlar.filter((mesaj) => mesaj.rol === "asistan");
    expect(akan).toHaveLength(1);
    expect(akan[0].metin).toBe("ikinci cevap");
  });

  it("arka plan çağrısının metni akışa girmez", () => {
    const mesajlar = olayEkle([], PARCA("ders çıkarımı", { channel: "background" }));

    expect(mesajlar.filter((mesaj) => mesaj.rol === "asistan")).toHaveLength(0);
  });

  it("tur bitince akan balon kalkar: nihai cevabı uygulama ekler", () => {
    let mesajlar = olayEkle([], PARCA("yazılıyor..."));
    mesajlar = olayEkle(mesajlar, { olay: "TurnFinished" });

    expect(mesajlar.filter((mesaj) => mesaj.rol === "asistan")).toHaveLength(0);
  });
});

describe("görev listesi", () => {
  const TODO = (output: string) => ({
    olay: "ToolExecuted",
    name: "todo_write",
    outcome: "ok",
    args: {},
    output,
  });

  it("araç çıktısını canlı göreve çevirir", () => {
    const mesajlar = olayEkle([], TODO("▶ testleri çalıştır\n☐ hatayı düzelt\n☒ dosyayı oku"));
    const liste = mesajlar.find((mesaj) => mesaj.rol === "gorevler");

    expect(liste?.gorevler).toEqual([
      { durum: "yapiliyor", metin: "testleri çalıştır" },
      { durum: "bekliyor", metin: "hatayı düzelt" },
      { durum: "bitti", metin: "dosyayı oku" },
    ]);
  });

  it("liste güncellenince eskisi çoğalmaz, yerine geçer", () => {
    let mesajlar = olayEkle([], TODO("▶ birinci\n☐ ikinci"));
    mesajlar = olayEkle(mesajlar, TODO("☒ birinci\n▶ ikinci"));

    const listeler = mesajlar.filter((mesaj) => mesaj.rol === "gorevler");
    expect(listeler).toHaveLength(1);
    expect(listeler[0].gorevler?.[0]).toEqual({ durum: "bitti", metin: "birinci" });
  });

  it("boş liste görev kartı açmaz", () => {
    const mesajlar = olayEkle([], TODO("(görev listesi boş)"));

    expect(mesajlar.filter((mesaj) => mesaj.rol === "gorevler")).toHaveLength(0);
  });
});
