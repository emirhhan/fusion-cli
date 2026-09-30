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

  /* Bkz. bug: "Düşünüyor 25sn" sayacı sekme değişince sıfırlanıyordu çünkü
     başlangıç zamanı yalnız bir bileşen ref'indeydi. Artık blok açılırken
     `baslangicZamani` OTURUM durumuna (mesaj listesine) damgalanır ve
     bileşen yeniden bağlansa bile aynı kalır. */
  it("blok açılınca baslangicZamani damgalanır ve sonraki adımlarda değişmez", () => {
    let mesajlar: Mesaj[] = [];
    mesajlar = olayEkle(mesajlar, DUSUNUYOR);

    const ilkDamga = mesajlar[0].baslangicZamani;
    expect(typeof ilkDamga).toBe("number");

    mesajlar = olayEkle(mesajlar, DUSUNUYOR);
    expect(mesajlar[0].baslangicZamani).toBe(ilkDamga);
  });

  it("blok başlığı son yapılan işi gösterir", () => {
    let mesajlar = olayEkle([], DUSUNUYOR);
    mesajlar = olayEkle(mesajlar, { olay: "ToolExecuted", name: "write_file", args: { path: "a.py" } });

    expect(mesajlar[0].metin).toBe("a.py yazılıyor");
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

describe("Claude gibi akış", () => {
  it("görev listesi kartı adım bloğunu bölmez", () => {
    let mesajlar = olayEkle([], { olay: "ToolStarted", name: "read_file", args: { path: "a.py" }, metin: "a.py okunuyor" });
    mesajlar = olayEkle(mesajlar, { olay: "ToolExecuted", name: "read_file", args: { path: "a.py" }, outcome: "ok", output: "x" });
    mesajlar = olayEkle(mesajlar, { olay: "ToolExecuted", name: "todo_write", outcome: "ok", output: "▶ Oku\n☐ Yaz" });
    mesajlar = olayEkle(mesajlar, { olay: "ToolStarted", name: "read_file", args: { path: "b.py" }, metin: "b.py okunuyor" });
    mesajlar = olayEkle(mesajlar, { olay: "ToolExecuted", name: "read_file", args: { path: "b.py" }, outcome: "ok", output: "y" });

    const bloklar = mesajlar.filter((mesaj) => mesaj.rol === "olay");
    expect(bloklar).toHaveLength(1);
    expect(bloklar[0].adimlar?.length).toBe(2);
    expect(mesajlar[mesajlar.length - 1].rol).toBe("gorevler");
  });

  it("giriş ve adım geçişi anlatımı adımların arasında metin olarak durur", () => {
    let mesajlar = olayEkle([], { olay: "NarrationPublished", text: "İsteği şöyle anladım: önce yapıyı okuyacağım." });
    mesajlar = olayEkle(mesajlar, { olay: "ToolStarted", name: "read_file", args: { path: "a.py" }, metin: "a.py okunuyor" });
    mesajlar = olayEkle(mesajlar, { olay: "NarrationPublished", text: "Şimdi “Testi yaz” adımına geçiyorum." });
    mesajlar = olayEkle(mesajlar, { olay: "ToolStarted", name: "write_file", args: { path: "t.py" }, metin: "t.py yazılıyor" });

    expect(mesajlar.map((mesaj) => mesaj.rol)).toEqual(["asistan", "olay", "asistan", "olay"]);
    expect(mesajlar[0].ara).toBe(true);
    expect(mesajlar[2].metin).toContain("Testi yaz");
  });
});

describe("değişiklik kartı", () => {
  /* Davranış değişikliği: diff eskiden akışa ayrı, kalıcı bir kart olarak
     düşüyordu. Claude'daki gibi kod akışta görünmez; diff adım satırının içinde
     durur ve satır açılınca görünür (bkz. `ActivityLine`). */
  it("başarılı yazmanın diff'ini adımın içinde taşır, akışa kart eklemez", () => {
    const sonuc = olayEkle([], {
      olay: "ToolExecuted",
      name: "write_file",
      outcome: "ok",
      args: { path: "scripts/Player.gd" },
      diff: "--- a\n+++ b\n+var speed = 320",
    });

    expect(sonuc.some((mesaj) => mesaj.rol === "degisiklik")).toBe(false);
    const adim = sonuc[0].adimlar?.[0];
    expect(adim?.yol).toBe("scripts/Player.gd");
    expect(adim?.diff).toContain("var speed = 320");
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

  it("araçtan önce akan metin ara anlatım olarak adımların arasında kalır", () => {
    let mesajlar = olayEkle([], PARCA("Şimdi testleri çalıştırıyorum."));
    mesajlar = olayEkle(mesajlar, { olay: "ToolStarted", name: "run_shell", args: { command: "pytest" }, metin: "pytest çalıştırılıyor" });
    mesajlar = olayEkle(mesajlar, DUSUNUYOR);
    mesajlar = olayEkle(mesajlar, { olay: "TurnFinished" });

    const anlatim = mesajlar.filter((mesaj) => mesaj.rol === "asistan");
    expect(anlatim).toHaveLength(1);
    expect(anlatim[0].metin).toBe("Şimdi testleri çalıştırıyorum.");
    expect(anlatim[0].ara).toBe(true);
    expect(anlatim[0].akan).toBeUndefined();
    expect(mesajlar.findIndex((mesaj) => mesaj.rol === "asistan"))
      .toBeLessThan(mesajlar.findIndex((mesaj) => mesaj.rol === "olay"));
  });

  it("araç istemeyen nihai cevap ara anlatıma dönüşmez", () => {
    let mesajlar = olayEkle([], PARCA("Nihai cevap."));
    mesajlar = olayEkle(mesajlar, { olay: "TurnFinished" });

    expect(mesajlar.some((mesaj) => mesaj.rol === "asistan")).toBe(false);
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

describe("Claude gibi kalıcı adımlar ve tur sayacı", () => {
  it("biten araç başladığı satırın yerine yazılır; sayaç tur boyunca aynı başlangıçtan sayar", () => {
    let mesajlar: Mesaj[] = [{ rol: "kullanici", metin: "oku" }];
    mesajlar = olayEkle(mesajlar, { olay: "ToolStarted", name: "read_file", args: { path: "a.py" }, metin: "a.py okunuyor" });
    const baslangic = mesajlar[1].baslangicZamani;
    mesajlar = olayEkle(mesajlar, { olay: "ToolExecuted", name: "read_file", args: { path: "a.py" }, outcome: "ok", output: "" });
    expect(mesajlar[1].adimlar).toHaveLength(1);
    expect(mesajlar[1].adimlar?.[0]).toMatchObject({ metin: "a.py okunuyor", durum: "ok", basladi: false });
    // Araya cevap parçası girip yeni blok açılsa da sayaç sıfırlanmaz.
    mesajlar = [...mesajlar, { rol: "asistan", metin: "Şimdi yazıyorum." }];
    mesajlar = olayEkle(mesajlar, { olay: "ToolStarted", name: "write_file", args: {}, metin: "b.py yazılıyor" });
    expect(mesajlar[mesajlar.length - 1].baslangicZamani).toBe(baslangic);
  });
});
