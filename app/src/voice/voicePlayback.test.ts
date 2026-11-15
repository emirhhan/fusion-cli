import { describe, expect, it, vi } from "vitest";
import { createVoicePlayback } from "./voicePlayback";
const deferred = <T,>() => { let resolve!: (value:T)=>void; return { promise:new Promise<T>(done=>{resolve=done;}), resolve:(value:T)=>resolve(value) }; };
describe("hazırlanan ses kuyruğu", () => {
 it("ikinci cümleyi ilki çalarken hazırlar ve bitmeden oynatmaz", async () => {
  const firstEnd=deferred<Record<string,unknown>>(); const publish=vi.fn(async()=>{}); let prepared=0;
  const request=vi.fn(async(name:string,data:Record<string,unknown>)=> {
   if(name==="ses.hazirla") return {ok:true,hazir_id:`p${++prepared}`};
   if(name==="ses.haziri_cal") return {ok:true,tur_id:data.hazir_id};
   if(name==="ses.bekle" && data.tur_id==="p1") return firstEnd.promise;
   return {ok:true,tamamlandi:true};
  });
  const turn=createVoicePlayback({request},`İlk cümle ${"uzun ".repeat(32)}. İkinci cümle.`,publish);
  await vi.waitFor(()=>expect(prepared).toBe(2));
  expect(request.mock.calls.filter(([name])=>name==="ses.haziri_cal")).toHaveLength(1);
  firstEnd.resolve({ok:true,tamamlandi:true}); await turn.finished;
  expect(request.mock.calls.filter(([name])=>name==="ses.haziri_cal")).toHaveLength(2);
 });
 it("hazırlama beklerken iptal, geç sesi çalmaz ve dosyayı temizler", async()=>{
  const ready=deferred<Record<string,unknown>>(); const publish=vi.fn(async()=>{});
  const request=vi.fn(async(name:string)=>name==="ses.hazirla" ? ready.promise : {ok:true});
  const turn=createVoicePlayback({request},"Merhaba.",publish);
  const cancel=turn.cancel(); ready.resolve({ok:true,hazir_id:"late"});
  await cancel; await turn.finished;
  expect(request.mock.calls.some(([name])=>name==="ses.haziri_cal")).toBe(false);
  expect(request).toHaveBeenCalledWith("ses.haziri_sil",{hazir_id:"late"});
  expect(publish).toHaveBeenCalledWith({durum:"interrupted"});
 });
});

it("çalma başlatılırken iptal edilen tur geç gelen oynatıcıyı kapatır", async () => {
 const started = deferred<Record<string, unknown>>();
 const publish = vi.fn(async () => {});
 const request = vi.fn(async (name: string) => {
  if(name === "ses.hazirla") return {ok:true, hazir_id:"owned"};
  if(name === "ses.haziri_cal") return started.promise;
  return {ok:true, tamamlandi:true};
 });
 const turn = createVoicePlayback({request}, "Merhaba.", publish);
 await vi.waitFor(() => expect(request).toHaveBeenCalledWith("ses.haziri_cal", {hazir_id:"owned", nesil:expect.any(Number)}));
 const cancelling = turn.cancel();
 started.resolve({ok:true, tur_id:"late-player"});
 await cancelling;
 expect(request).toHaveBeenCalledWith("ses.durdur", {tur_id:"late-player"});
 expect(request.mock.calls.filter(([name]) => name === "ses.durdur")).toHaveLength(1);
 expect(publish).not.toHaveBeenCalledWith(expect.objectContaining({durum:"talking"}));
});

describe("voicePlayback — dalga 4 (U2-25, U2-26)", () => {
 it("bir hazır sesin silinememesi kalanları sızdırmaz ve iptali 'error' yapmaz (U2-25)", async () => {
  const publish = vi.fn(async () => {});
  const request = vi.fn(async (name: string) => {
   if (name === "ses.hazirla") return { ok: true, hazir_id: `h${request.mock.calls.filter(([n]) => n === "ses.hazirla").length}` };
   if (name === "ses.haziri_sil") return { ok: false };
   return { ok: true };
  });
  const turn = createVoicePlayback({ request }, "Merhaba.", publish);
  const cancel = turn.cancel();
  await expect(cancel).resolves.toBeUndefined();
  await expect(turn.finished).resolves.toBeUndefined();
  expect(publish).toHaveBeenCalledWith({ durum: "interrupted" });
  expect(publish).not.toHaveBeenCalledWith(expect.objectContaining({ durum: "error" }));
 });

 it("çekirdek hazırlama isteğine yanıt vermezse süre aşımıyla hata yayınlar (U2-26)", async () => {
  vi.useFakeTimers();
  try {
   const publish = vi.fn(async () => {});
   const request = vi.fn((name: string) => name === "ses.hazirla" ? new Promise<Record<string, unknown>>(() => undefined) : Promise.resolve({ ok: true }));
   const turn = createVoicePlayback({ request }, "Merhaba.", publish);
   const outcome = turn.finished.then(() => "bitti", (error: Error) => error.message);
   await vi.advanceTimersByTimeAsync(61_000);
   await expect(outcome).resolves.toBe("Ses hizmeti yanıt vermedi.");
   expect(publish).toHaveBeenCalledWith({ durum: "error", metin: "Ses hizmeti yanıt vermedi." });
  } finally { vi.useRealTimers(); }
 });
});
