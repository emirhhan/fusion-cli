import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import type { Mesaj } from "../screens/Conversation";
import { ekipOlayi } from "./ekipOlaylari";
import { OrchestrationPanel } from "./OrchestrationPanel";
import { orkestrasyonOlayi } from "./orkestrasyon";
import { TeamBoard } from "./TeamBoard";
import { WorkflowBoard } from "./WorkflowBoard";

afterEach(cleanup);

function ilerleme(status: string, dugumDurumu: string) {
  return {
    olay: "WorkflowProgress", run_id: "k1", name: "inceleme", status, phase: "Keşif",
    agents_started: 1, agents_limit: 50, elapsed_s: 3.2, message: "",
    nodes: [
      { id: "a1", label: "a.py incele", status: dugumDurumu, phase: "Keşif", summary: "" },
      { id: "a2", label: "b.py incele", status: "bekliyor", phase: "Keşif", summary: "" },
    ],
  };
}

describe("iş akışı panosu", () => {
  it("aynı koşunun olayları tek panoyu yerinde günceller, kartlar aynı mesaja girer", () => {
    let akis: Mesaj[] = [{ rol: "kullanici", metin: "akış kur" }];
    akis = orkestrasyonOlayi(akis, ilerleme("calisiyor", "calisiyor"))!;
    akis = ekipOlayi(akis, { olay: "SubAgentStarted", sub_id: "x-1", task: "a.py incele", group_size: 2 })!;
    akis = orkestrasyonOlayi(akis, ilerleme("tamam", "tamam"))!;

    expect(akis).toHaveLength(2);
    expect(akis[1].akis?.durum).toBe("tamam");
    expect(akis[1].ajanlar?.map((kart) => kart.id)).toEqual(["x-1"]);
  });

  it("ilgisiz olaya null döner", () => {
    expect(orkestrasyonOlayi([], { olay: "ToolStarted" })).toBeNull();
  });

  it("evreyi, ilerlemeyi ve durumları metinle gösterir", () => {
    const mesaj = orkestrasyonOlayi([], ilerleme("calisiyor", "calisiyor"))![0];
    render(<WorkflowBoard akis={mesaj.akis!} running />);

    expect(screen.getByText("Evre: Keşif")).toBeTruthy();
    expect(screen.getByText("0/2 adım")).toBeTruthy();
    expect(screen.getByText("çalışıyor")).toBeTruthy();
    expect(screen.getByText("Çalışıyor")).toBeTruthy();
  });

  it("tur bittiyse koşan pano yarım kaldı der", () => {
    const mesaj = orkestrasyonOlayi([], ilerleme("calisiyor", "calisiyor"))![0];
    render(<WorkflowBoard akis={mesaj.akis!} running={false} />);

    expect(screen.getByText("Yarım kaldı")).toBeTruthy();
  });
});

describe("İş akışları paneli", () => {
  it("kayıtlıyı /workflows komutuyla çalıştırır, koşanı akis.iptal ile durdurur", async () => {
    const request = vi.fn(async (name: string) => name === "akis.liste" ? {
      ok: true,
      tanimlar: [{ ad: "rapor", kapsam: "proje", aciklama: "haftalık" }],
      kosular: [{ run_id: "k1", name: "rapor", status: "calisiyor", agents_started: 2, nodes: [{ status: "tamam" }, { status: "calisiyor" }], phase: "", message: "" }],
    } : { ok: true });
    const client = { request, onEvent: () => () => undefined } as unknown as ProtocolClient;
    const onCommand = vi.fn();
    render(<OrchestrationPanel client={client} onCommand={onCommand} />);

    (await screen.findByText("Çalıştır")).click();
    screen.getByText("Durdur").click();

    expect(onCommand).toHaveBeenCalledWith("/workflows rapor");
    await vi.waitFor(() => expect(request).toHaveBeenCalledWith("akis.iptal", { kimlik: "k1" }));
    expect(screen.getByText(/1\/2 adım · 2 ajan/)).toBeTruthy();
  });
});

function panoOlayi(status: string) {
  return {
    olay: "TeamBoardChanged", team: "site", goal: "Açılış sayfası", status, group_size: 16,
    tasks: [
      { id: "g1", title: "Palet", status: "tamam", owner: "tasarim", depends_on: [], result: "ok" },
      { id: "g2", title: "JS", status: "calisiyor", owner: "kod", depends_on: ["g1"], result: "" },
      { id: "g3", title: "Test", status: "basarisiz", owner: "kod", depends_on: [], result: "anahtar yok" },
    ],
    members: [{ name: "kod", persona: "kodcu", status: "calisiyor", sub_id: "kod-1", wakes: 1 }],
    messages: [{ sender: "kod", recipient: "lider", text: "JS yarım", at: 1 }],
  };
}

describe("ekip panosu", () => {
  it("koşan ekibin panosu yerinde güncellenir, bitmiş ekip yeni turda yeni pano açar", () => {
    let akis = orkestrasyonOlayi([], panoOlayi("calisiyor"))!;
    akis = orkestrasyonOlayi(akis, panoOlayi("bitti"))!;
    akis = orkestrasyonOlayi(akis, panoOlayi("calisiyor"))!;

    expect(akis).toHaveLength(2);
    expect(akis[0].pano?.durum).toBe("bitti");
    expect(akis[1].grupBoyutu).toBe(16);
  });

  it("görevleri sütunlarda, üyeleri ve posta kutusunu gösterir", () => {
    const mesaj = orkestrasyonOlayi([], panoOlayi("calisiyor"))![0];
    render(<TeamBoard pano={mesaj.pano!} running />);

    expect(screen.getByText("Bekliyor · 0")).toBeTruthy();
    expect(screen.getByText("Çalışıyor · 1")).toBeTruthy();
    expect(screen.getByText("Bitti · 2")).toBeTruthy();
    expect(screen.getByText("başarısız: anahtar yok")).toBeTruthy();
    expect(screen.getByText(/çalışıyor · 1 uyanma/)).toBeTruthy();
    expect(screen.getByText("kod → lider")).toBeTruthy();
  });

  it("panel ekip panosunu /team goster ile açar", async () => {
    const request = vi.fn(async (name: string) => name === "ekip.liste"
      ? { ok: true, ekipler: [{ ad: "site", hedef: "Açılış", gorev: 3, tamam: 1 }] }
      : { ok: true, tanimlar: [], kosular: [] });
    const client = { request, onEvent: () => () => undefined } as unknown as ProtocolClient;
    const onCommand = vi.fn();
    render(<OrchestrationPanel client={client} onCommand={onCommand} />);

    (await screen.findByText("Pano")).click();

    expect(onCommand).toHaveBeenCalledWith("/team goster site");
    expect(screen.getByText("1/3 görev · Açılış")).toBeTruthy();
    expect(screen.queryByText("İş akışları")).toBeNull();
  });
});
