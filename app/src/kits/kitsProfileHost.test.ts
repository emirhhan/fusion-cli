import { describe, expect, it, vi } from "vitest";
import {
  KITS_PROFILE_DESCRIBE_RPC,
  KITS_PROFILE_EXPORT_RPC,
  KitsProfileHost,
  describeProfileRequest,
  parseProfileInput,
} from "./kitsProfileHost";

const ORIGIN = "http://127.0.0.1:4410";
const KOD = { id: "k1", name: "Kod" };
const GIZLI = "kit-cerezi-GIZLI-73";
const DURUM = { cookies: [{ name: "sid", value: GIZLI, domain: ".example.com" }], origins: [] };

function fixture(
  izin = true,
  tarif: Record<string, unknown> = { ok: true, status: "ok", alan_adlari: ["example.com"], profil_alanlari: ["example.com", "shop.example.com"] },
  aktar: Record<string, unknown> = { ok: true, status: "ok", cerez_sayisi: 1, storage_state: DURUM },
) {
  const listeners = new Set<(event: MessageEvent) => void>();
  const host = {
    addEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.add(l),
    removeEventListener: (_: "message", l: (event: MessageEvent) => void) => listeners.delete(l),
  };
  const frame = { postMessage: vi.fn() };
  const request = vi.fn(async (name: string, _data: Record<string, unknown>) =>
    name === KITS_PROFILE_DESCRIBE_RPC ? tarif : aktar,
  );
  const confirm = vi.fn(async (_summary: string) => izin);
  const client = new KitsProfileHost(host, frame, `${ORIGIN}/?theme=dark`, request, confirm);
  const send = (data: unknown, origin = ORIGIN, source: unknown = frame) =>
    listeners.forEach((l) => l({ data, origin, source } as MessageEvent));
  const replies = () => frame.postMessage.mock.calls.map((call) => call[0] as Record<string, unknown>);
  const disaAktarmalar = () => request.mock.calls.filter((call) => call[0] === KITS_PROFILE_EXPORT_RPC);
  return { client, frame, request, confirm, send, replies, disaAktarmalar };
}
const req = (nonce: string, input: unknown, kit: unknown = KOD) => ({ type: "fusion-profile-request", nonce, input, kit });
const GECERLI = { profile: "is", domains: ["Example.com"], reason: "Sipariş durumunu kontrol et" };

describe("KitsProfileHost", () => {
  it("her istekte Kit adı, profil ve alan adlarıyla sorar; onayda oturum yalnız iframe kökenine gider", async () => {
    const f = fixture(true);
    f.send(req("n1", GECERLI));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));

    expect(f.request).toHaveBeenCalledWith(KITS_PROFILE_DESCRIBE_RPC, { ad: "is", alanlar: ["example.com"] });
    const ozet = f.confirm.mock.calls[0][0];
    expect(ozet).toContain("«Kod» Kit'i");
    expect(ozet).toContain("«is» tarayıcı profilinin");
    expect(ozet).toContain("example.com");
    expect(ozet).not.toContain(GIZLI);
    const yanit = f.replies()[0];
    expect(yanit).toMatchObject({ type: "fusion-profile-result", nonce: "n1", status: "ok", state: DURUM });
    expect(String(yanit.text)).not.toContain(GIZLI);
    expect(f.frame.postMessage.mock.calls[0][1]).toBe(ORIGIN);

    // İzin hatırlanmaz: ikinci istek yeniden sorulur.
    f.send(req("n2", GECERLI));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));
    expect(f.confirm).toHaveBeenCalledTimes(2);
  });

  it("ret durumunda dışa aktarma RPC'si hiç çağrılmaz ve oturum dönmez", async () => {
    const f = fixture(false);
    f.send(req("n1", GECERLI));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));

    expect(f.disaAktarmalar()).toHaveLength(0);
    expect(f.replies()[0]).toMatchObject({ status: "denied" });
    expect(f.replies()[0].state).toBeUndefined();
  });

  it("tarif reddederse (kapalı araç, onay dışı alan adı) kullanıcıya sorulmaz", async () => {
    const f = fixture(true, { ok: false, status: "denied", text: "Profil bu alan adları için onaylı değil: bank.com." });
    f.send(req("n1", { profile: "is", domains: ["bank.com"] }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(1));

    expect(f.confirm).not.toHaveBeenCalled();
    expect(f.disaAktarmalar()).toHaveLength(0);
    expect(f.replies()[0]).toMatchObject({ status: "denied", text: expect.stringContaining("bank.com") });
  });

  it("yabancı köken, başka pencere ve geçersiz yük işlenmez", async () => {
    const f = fixture(true);
    f.send(req("n1", GECERLI), "https://kotu.example");
    f.send(req("n2", GECERLI), ORIGIN, {});
    f.send(req("n3", { profile: "../x", domains: ["a.com"] }));
    f.send(req("n4", { profile: "is", domains: [] }));
    await vi.waitFor(() => expect(f.frame.postMessage).toHaveBeenCalledTimes(2));

    expect(f.request).not.toHaveBeenCalled();
    expect(f.replies().map((r) => r.status)).toEqual(["failed", "failed"]);
  });

  it("girdi doğrulaması ve özet metni", () => {
    expect(parseProfileInput({ profile: "is", domains: Array.from({ length: 21 }, (_, i) => `s${i}.a.com`) })).toBeNull();
    expect(parseProfileInput({ profile: "is", domains: ["a.com\nb"] })).toBeNull();
    expect(parseProfileInput({ profile: "is", domains: [" A.com "], extra: 1 })).toEqual({ profile: "is", domains: ["a.com"] });
    const metin = describeProfileRequest({ profile: "is", domains: ["a.com"] }, { domains: ["a.com"], profileDomains: ["a.com"] }, null);
    expect(metin.startsWith("Kits,")).toBe(true);
  });
});
