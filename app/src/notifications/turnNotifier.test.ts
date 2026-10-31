import { describe, expect, it } from "vitest";
import { VARSAYILAN_BILDIRIM_TERCIHLERI } from "./preferences";
import { planNotifications, unreadTransitions, type OturumIzi } from "./turnNotifier";

const iz = (running: boolean, questionId: string | null = null, title = "Sohbet"): OturumIzi => ({ running, questionId, title });

/* Claude Code masaüstü kuralı: kullanıcı o sohbete BAKMIYORSA haber verilir (P-047). */
describe("planNotifications", () => {
  it("bakılan sohbetin turu pencere odakta değilken bitince 'tur bitti' bildirir", () => {
    const plan = planNotifications({ a: iz(true) }, { a: iz(false, null, "Tema") }, { activeId: "a", focused: false }, VARSAYILAN_BILDIRIM_TERCIHLERI);
    expect(plan).toHaveLength(1);
    expect(plan[0]).toMatchObject({ tur: "tur-bitti", oturumId: "a", odaktaDaGonder: false });
    expect(plan[0].metin).toContain("Tema");
  });

  it("bakılan sohbet odaktayken bitince bildirmez: cevap zaten ekranda", () => {
    expect(planNotifications({ a: iz(true) }, { a: iz(false) }, { activeId: "a", focused: true }, VARSAYILAN_BILDIRIM_TERCIHLERI)).toEqual([]);
  });

  it("başka sohbet bitince pencere odakta olsa da 'arka plan bitti' bildirir", () => {
    const plan = planNotifications({ b: iz(true) }, { b: iz(false) }, { activeId: "a", focused: true }, VARSAYILAN_BILDIRIM_TERCIHLERI);
    expect(plan).toHaveLength(1);
    expect(plan[0]).toMatchObject({ tur: "arka-plan-bitti", oturumId: "b", odaktaDaGonder: true, okunmamis: true });
  });

  it("onay sorusu gelince yalnız bakılmıyorsa bildirir", () => {
    const bakiliyor = planNotifications({ a: iz(true) }, { a: iz(true, "s1") }, { activeId: "a", focused: true }, VARSAYILAN_BILDIRIM_TERCIHLERI);
    expect(bakiliyor).toEqual([]);
    const arkada = planNotifications({ a: iz(true) }, { a: iz(true, "s1") }, { activeId: "a", focused: false }, VARSAYILAN_BILDIRIM_TERCIHLERI);
    expect(arkada.map((item) => item.tur)).toEqual(["onay-bekliyor"]);
    const baska = planNotifications({ b: iz(true) }, { b: iz(true, "s1") }, { activeId: "a", focused: true }, VARSAYILAN_BILDIRIM_TERCIHLERI);
    expect(baska[0]).toMatchObject({ tur: "onay-bekliyor", odaktaDaGonder: true });
  });

  it("ilk kez görülen (geri yüklenen) sohbet geçiş sayılmaz", () => {
    expect(planNotifications({}, { a: iz(false), b: iz(true, "s") }, { activeId: null, focused: false }, VARSAYILAN_BILDIRIM_TERCIHLERI)).toEqual([]);
  });

  it("tercih kapalıysa o tür bildirim üretilmez", () => {
    const tercih = { ...VARSAYILAN_BILDIRIM_TERCIHLERI, turBitti: false, arkaPlanBitti: false };
    expect(planNotifications({ a: iz(true), b: iz(true) }, { a: iz(false), b: iz(false) }, { activeId: "a", focused: false }, tercih)).toEqual([]);
  });

  it("aynı sohbette tur bitişi ve soru birlikte gelirse ikisi de planlanır", () => {
    const plan = planNotifications({ b: iz(true) }, { b: iz(false, "s1") }, { activeId: "a", focused: true }, VARSAYILAN_BILDIRIM_TERCIHLERI);
    expect(plan.map((item) => item.tur).sort()).toEqual(["arka-plan-bitti", "onay-bekliyor"]);
  });
});

describe("unreadTransitions", () => {
  it("bakılmayan sohbette biten tur ya da gelen soru okunmamış sayılır; bakılan sayılmaz", () => {
    const once = { a: iz(true), b: iz(true), c: iz(true) };
    const simdi = { a: iz(false), b: iz(false), c: iz(true, "soru") };
    expect(unreadTransitions(once, simdi, { activeId: "a", focused: true })).toEqual(["b", "c"]);
    expect(unreadTransitions(once, simdi, { activeId: "a", focused: false })).toEqual(["a", "b", "c"]);
  });
});
