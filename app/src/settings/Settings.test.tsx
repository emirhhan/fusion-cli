import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { Settings } from "./Settings";

function client() {
  return {
    request: vi.fn(async (name: string) => {
      if (name === "kontrol.durum") return {
        ok: true,
        kok: "/Users/test/Fusion",
        gateway: { durum: "calisiyor", adres: "http://127.0.0.1:8787/v1" },
        izin: { mod: "auto", kokle_sinirli: true },
        model: {
          agent: "gemini_web/main/auto",
          hakem: "openrouter/hakem",
          adaylar: ["hizli", "derin"],
          saglayici: "gemini_web",
        },
        saglayicilar: [{ id: "openrouter", ad: "OpenRouter", kurulu: true }],
      };
      if (name === "ayar.talimat") return { ok: true, metin: "Kısa yaz.", sinir: 4000 };
      if (name === "kullanim.durum") return {
        ok: true,
        kullanim: {
          cagri: 0,
          girdi_token: 0,
          cikti_token: 0,
          toplam_token: 0,
          maliyet_usd: 0,
          modeller: [],
        },
        saglik: [],
      };
      if (name === "ses.durum") return {
        ok: true,
        ayar: { hiz: 1, model: null, robotik: 0.5 },
        kullanilabilir: true,
        model_kurulu: false,
        motor: "sistem",
        ses: "Cem",
        turkce: true,
        yukseltme: null,
      };
      return { ok: true };
    }),
  } as unknown as ProtocolClient;
}

function ciz(ekle: Partial<Parameters<typeof Settings>[0]> = {}) {
  const fake = ekle.client ?? client();
  render(
    <Settings
      client={fake}
      onClose={() => undefined}
      onThemeChange={() => undefined}
      themePreference="system"
      {...ekle}
    />,
  );
  return fake;
}

/** Bölüme geç: içerik artık tek yığında değil, sol menüyle ayrılmış durumda. */
function bolum(etiket: string) {
  fireEvent.click(screen.getByRole("button", { name: etiket }));
}

// Depodaki diğer testlerle aynı: render'lar birikirse sorgular çoklu eşleşir.
afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("Settings — yapı", () => {
  it("bölümleri sol menüde listeler ve Genel ile açılır", async () => {
    ciz();

    expect(await screen.findByRole("heading", { name: "Ayarlar" })).toBeTruthy();
    for (const etiket of ["Genel", "Hesap", "Modeller", "İzinler", "Güncellemeler", "Gelişmiş"]) {
      expect(screen.getByRole("button", { name: etiket })).toBeTruthy();
    }
    expect(screen.getByRole("button", { name: "Genel" }).getAttribute("aria-current")).toBe("page");
  });

  /* Kullanıcının ölçülmüş şikayeti: "Fusion for macOS" eyebrow'u ve "Çalışma
     alanı" kartı ne olduğu anlaşılmayan yerlerdi. */
  it("kaldırılan bölümleri ve etiketleri artık göstermez", async () => {
    ciz();
    await screen.findByRole("heading", { name: "Ayarlar" });

    expect(screen.queryByText("Fusion for macOS")).toBeNull();
    expect(screen.queryByText("Çalışma alanı")).toBeNull();
    expect(screen.queryByText(/^Gateway/)).toBeNull();
  });

  it("bölüm değiştirince yalnız o bölüm çizilir", async () => {
    ciz();
    await screen.findByRole("heading", { name: "Ayarlar" });
    expect(screen.getByRole("heading", { name: "Görünüm" })).toBeTruthy();

    bolum("İzinler");

    expect(screen.queryByRole("heading", { name: "Görünüm" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Çalışma modu" })).toBeTruthy();
  });
});

describe("Settings — Genel", () => {
  it("tema seçimini iletir ve geçmiş tercihini saklar", async () => {
    const onThemeChange = vi.fn();
    ciz({ onThemeChange });
    await screen.findByRole("heading", { name: "Ayarlar" });

    fireEvent.change(screen.getByRole("combobox", { name: "Tema" }), {
      target: { value: "dark" },
    });
    expect(onThemeChange).toHaveBeenCalledWith("dark");

    const gecmis = screen.getByRole("checkbox", {
      name: "Geçmiş bölümünü açık başlat",
    }) as HTMLInputElement;
    expect(gecmis.checked).toBe(true);
    fireEvent.click(gecmis);
    expect(localStorage.getItem("fusion.sidebar.history-open.v1")).toBe("false");
  });

  it("dil seçeneği tek ve kapalıdır; sebebini yazar", async () => {
    ciz();
    await screen.findByRole("heading", { name: "Ayarlar" });

    const dil = screen.getByRole("combobox", { name: "Dil" }) as HTMLSelectElement;
    expect(dil.disabled).toBe(true);
    expect(screen.getByText(/yalnız Türkçe/i)).toBeTruthy();
  });
});

describe("Settings — Modeller", () => {
  /* Ajan modunda TEK model çalışır; hakem ve aday havuzu yalnız Fusion
     motoruna aittir. İkisini birlikte göstermek, agent turunda hiç
     kullanılmayan kavramları kullanıcının önüne koyuyordu. */
  it("ajan modelini ayrı, Fusion motorunu ayrı gösterir", async () => {
    ciz();
    bolum("Modeller");

    await waitFor(() => expect(screen.getByText("gemini_web/main/auto")).toBeTruthy());
    expect(screen.getByRole("heading", { name: "Ajan modeli" })).toBeTruthy();
    const fusion = screen.getByRole("heading", { name: "Fusion motoru" }).closest("article");
    expect(fusion?.textContent).toContain("openrouter/hakem");
    expect(fusion?.textContent).toContain("hizli · derin");
  });

  it("düşünme düzeyi artık sunulmaz", async () => {
    ciz();
    bolum("Modeller");
    await waitFor(() => expect(screen.getByText("gemini_web/main/auto")).toBeTruthy());

    expect(screen.queryByText(/Düşünme düzeyi/i)).toBeNull();
  });

  it("model değiştirme isteğini komut olarak iletir", async () => {
    const onRunCommand = vi.fn();
    ciz({ onRunCommand });
    bolum("Modeller");
    await waitFor(() => expect(screen.getByText("gemini_web/main/auto")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Modeli değiştir" }));

    expect(onRunCommand).toHaveBeenCalledWith("/model");
  });
});

describe("Settings — İzinler", () => {
  it("etkin modu işaretler ve ne yaptığını yazar", async () => {
    ciz();
    bolum("İzinler");

    await waitFor(() => expect(screen.getByText("/Users/test/Fusion")).toBeTruthy());
    const otomatik = screen.getByText("Otomatik uygula").closest(".settings__choice");
    expect(otomatik?.getAttribute("data-active")).toBe("true");
    expect(screen.getByText(/yıkıcı işlemde yine sorar/i)).toBeTruthy();
  });

  it("klasör değiştirme isteğini iletir", async () => {
    const onChangeRoot = vi.fn();
    ciz({ onChangeRoot });
    bolum("İzinler");
    await waitFor(() => expect(screen.getByText("/Users/test/Fusion")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Klasörü değiştir" }));

    expect(onChangeRoot).toHaveBeenCalledTimes(1);
  });

  it("çalışma modu kartına basınca ilgili komutu gönderir", async () => {
    const onRunCommand = vi.fn();
    ciz({ onRunCommand });
    bolum("İzinler");
    await waitFor(() => expect(screen.getByText("/Users/test/Fusion")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /Her işlemde sor/ }));

    expect(onRunCommand).toHaveBeenCalledWith("/security");
  });
});

describe("Settings — Gelişmiş", () => {
  /* "gateway nedir ben bile bilmiyorum" — ad ne olduğunu değil ne YAPTIĞINI
     söylemeli. */
  it("yerel API ucunu adıyla değil işleviyle anlatır", async () => {
    ciz();
    bolum("Gelişmiş");

    expect(await screen.findByRole("heading", { name: "Yerel API ucu" })).toBeTruthy();
    expect(screen.getByText(/Cursor, Cline/)).toBeTruthy();
    expect(screen.getByText("http://127.0.0.1:8787/v1")).toBeTruthy();
  });

  it("çalışan ucu durdurma isteğini çekirdeğe gönderir", async () => {
    const fake = ciz();
    bolum("Gelişmiş");
    await screen.findByRole("heading", { name: "Yerel API ucu" });

    fireEvent.click(screen.getByRole("button", { name: "Durdur" }));

    await waitFor(() =>
      expect(fake.request).toHaveBeenCalledWith("kontrol.gateway_durdur", {}),
    );
  });

  it("kalıcı talimatı yükler ve kaydeder", async () => {
    const fake = ciz();
    bolum("Gelişmiş");

    const alan = (await screen.findByLabelText("Kalıcı talimat")) as HTMLTextAreaElement;
    expect(alan.value).toBe("Kısa yaz.");
    expect((screen.getByRole("button", { name: "Kaydet" }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.change(alan, { target: { value: "Cevapları kısa tut." } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

    await waitFor(() =>
      expect(fake.request).toHaveBeenCalledWith("ayar.talimat_kaydet", {
        metin: "Cevapları kısa tut.",
      }),
    );
  });

  /* MCP yönetimi TEK ekranda olmalı: Ayarlar'daki ikinci kopya, biri
     düzeltilirken ötekinin eskimesi demekti. */
  it("MCP yönetimi Ayarlar'da tekrar edilmez", async () => {
    ciz();
    bolum("Gelişmiş");
    await screen.findByRole("heading", { name: "Yerel API ucu" });

    expect(screen.queryByRole("button", { name: "Bağlantı ekle" })).toBeNull();
  });
});
