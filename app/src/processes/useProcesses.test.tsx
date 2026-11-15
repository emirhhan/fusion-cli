import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { useProcesses } from "./useProcesses";

afterEach(cleanup);

describe("useProcesses", () => {
  it("ProcessOutput olay parçalarını snapshot aynı kalsa da monoton akışta korur", async () => {
    let eventListener: ((event: Record<string, unknown>) => void) | null = null;
    const client = {
      onEvent: vi.fn((listener: (event: Record<string, unknown>) => void) => {
        eventListener = listener;
        return () => { eventListener = null; };
      }),
      request: vi.fn(async () => ({ ok: true, surecler: [] })),
    } as unknown as ProtocolClient;

    function Probe() {
      const state = useProcesses(client);
      const stream = state.outputStreams.dev;
      return <output>{stream ? `${stream.total}:${stream.text}` : "boş"}</output>;
    }

    render(<Probe />);
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("surec.listele", {}));
    act(() => {
      eventListener?.({ olay: "ProcessOutput", surec_id: "dev", metin: "xxx" });
      eventListener?.({ olay: "ProcessOutput", surec_id: "dev", metin: "xxx" });
    });

    expect(screen.getByText("6:xxxxxx")).toBeTruthy();
  });
});

// Ölçüldü (30 Ekim): başlatma hatası bir sonraki başarılı yoklamada siliniyor (U4-27); tek bozuk kayıt
// tüm listeyi reddediyor (U4-28); çıktı olayı başına eşzamanlı tam liste isteği çıkıyordu (U4-26).
describe("useProcesses dayanıklılık (30 Ekim)", () => {
  function istemci(listele: () => Promise<Record<string, unknown>>, baslat?: () => Promise<Record<string, unknown>>) {
    let dinleyici: ((event: Record<string, unknown>) => void) | null = null;
    const client = {
      onEvent: vi.fn((f: (event: Record<string, unknown>) => void) => { dinleyici = f; return () => { dinleyici = null; }; }),
      request: vi.fn(async (ad: string) => (ad === "surec.baslat" && baslat ? baslat() : listele())),
    } as unknown as ProtocolClient;
    return { client, olay: (e: Record<string, unknown>) => dinleyici?.(e) };
  }

  it("başlatma hatası sonraki başarılı yoklamayla silinmez (U4-27)", async () => {
    const { client } = istemci(async () => ({ ok: true, surecler: [] }), async () => ({ ok: false, metin: "komut bulunamadı" }));
    let kontrol!: ReturnType<typeof useProcesses>;
    function Probe() { kontrol = useProcesses(client); return <output>{kontrol.error ?? "yok"}</output>; }
    render(<Probe />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());
    await act(async () => { await kontrol.start("xyz"); });
    expect(screen.getByText("komut bulunamadı")).toBeTruthy();
    await act(async () => { await kontrol.refresh(); });
    expect(screen.getByText("komut bulunamadı")).toBeTruthy();
  });

  it("tek bozuk kayıt listeyi düşürmez; pid boş ve bilinmeyen durum kabul edilir (U4-28)", async () => {
    const saglam = { surec_id: "a", komut: "ls", cwd: "/", pid: 5, durum: "calisiyor", cikis_kodu: null, cikti: "", baslangic: 1 };
    const { client } = istemci(async () => ({ ok: true, surecler: [
      saglam, { surec_id: 3 }, { ...saglam, surec_id: "b", pid: null, durum: "zaman_asimi" },
    ] }));
    function Probe() {
      const s = useProcesses(client);
      return <output>{s.error ?? s.processes.map((p) => `${p.surec_id}:${p.pid}:${p.durum}`).join(",")}</output>;
    }
    render(<Probe />);
    await waitFor(() => expect(screen.getByText("a:5:calisiyor,b:null:hata")).toBeTruthy());
  });

  it("çıktı olayları eşzamanlı liste isteği çıkarmaz (U4-26)", async () => {
    let acik = 0, enFazla = 0;
    const { client, olay } = istemci(async () => {
      acik += 1; enFazla = Math.max(enFazla, acik);
      await new Promise((r) => setTimeout(r, 10));
      acik -= 1;
      return { ok: true, surecler: [] };
    });
    function Probe() { useProcesses(client); return null; }
    render(<Probe />);
    await waitFor(() => expect(client.request).toHaveBeenCalled());
    act(() => { for (let i = 0; i < 20; i += 1) olay({ olay: "ProcessOutput", surec_id: "dev", metin: "x" }); });
    await new Promise((r) => setTimeout(r, 80));
    expect(enFazla).toBe(1);
  });
});
