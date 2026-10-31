import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { resetLanguageCache } from "../i18n/language";
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
          ogretmen: "gemini_web/main/auto",
          ogretmen_etiket: "Gemini · 3.1 Pro",
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
  resetLanguageCache();
});

describe("Settings — kontrol.durum hataları", () => {
  /* Bkz. bug: "Ayarlar okunamadı" hatası hangi isteğin neden başarısız
     olduğunu hiç söylemiyordu — `catch` bloğu gerçek nedeni sabit bir
     metinle örtüyordu. Ayrıca `kontrol.durum` `{ok:false}` döndürdüğünde
     (istek REDDEDİLMEZ, başarısız bir SONUÇLA çözülür) ekran bunu hiç
     kontrol etmeden geçerli veri gibi kullanıyordu. */
  it("çekirdek {ok:false} dönerse gerçek nedeni gösterir ve 'Yeniden dene' ile düzelir", async () => {
    let hazir = false;
    const fake = {
      request: vi.fn(async (name: string) => {
        if (name === "kontrol.durum") {
          return hazir
            ? { ok: true, kok: "/p", gateway: {}, izin: {}, model: {}, saglayicilar: [] }
            : { ok: false, metin: "oturum henüz hazır değil" };
        }
        return { ok: true };
      }),
    } as unknown as ProtocolClient;
    ciz({ client: fake });

    expect(await screen.findByText(/Ayarlar okunamadı: oturum henüz hazır değil/)).toBeTruthy();

    hazir = true;
    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));

    await waitFor(() => expect(screen.queryByText(/Ayarlar okunamadı/)).toBeNull());
  });

  it("istek reddedilirse (transport hatası) gerçek istisna mesajını gösterir", async () => {
    const fake = {
      request: vi.fn(async (name: string) => {
        if (name === "kontrol.durum") throw new Error("Çekirdek bağlantısı kapatıldı.");
        return { ok: true };
      }),
    } as unknown as ProtocolClient;
    ciz({ client: fake });

    expect(await screen.findByText(/Ayarlar okunamadı: Çekirdek bağlantısı kapatıldı\./)).toBeTruthy();
  });
});

describe("Settings — yapı", () => {
  it("profil kısayolundan doğrudan bellek ve kalıcı talimatları açar", async () => {
    ciz({ initialSection: "kisisellestirme" });
    expect(await screen.findByLabelText("Kalıcı talimat")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Kişiselleştirme" }).getAttribute("aria-current")).toBe("page");
  });

  it("bağlı web öğretmenini modeller bölümünde gösterir", async () => {
    ciz();
    bolum("Modeller");
    expect(await screen.findByText(/Öğretmen: Gemini · 3.1 Pro/)).toBeTruthy();
  });

  it("sohbetin üstünde aranan ve Escape ile kapanan pencere açar", async () => {
    const onClose = vi.fn();
    ciz({ onClose });
    expect(await screen.findByRole("dialog", { name: "Ayarlar" })).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox", { name: "Ayarları ara" }), {
      target: { value: "model" },
    });
    expect(screen.getByRole("button", { name: "Modeller" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Genel" })).toBeNull();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("bölümleri sol menüde listeler ve Genel ile açılır", async () => {
    ciz();

    expect(await screen.findByRole("heading", { name: "Ayarlar" })).toBeTruthy();
    for (const etiket of ["Genel", "Hesap", "Ses", "Modeller", "İzinler", "Güncellemeler", "Gelişmiş"]) {
      expect(screen.getByRole("button", { name: etiket })).toBeTruthy();
    }
    expect(screen.getByRole("button", { name: "Genel" }).getAttribute("aria-current")).toBe("page");
  });

  it("ses tercihlerini kendi bölümünde açar", async () => {
    const fake = ciz();
    bolum("Ses");

    expect(await screen.findByText(/Konuşma hızı ve çevrimdışı/)).toBeTruthy();
    expect(vi.mocked(fake.request)).toHaveBeenCalledWith("ses.durum", {});
    bolum("Gelişmiş");
    expect(screen.queryByText(/Konuşma hızı ve çevrimdışı/)).toBeNull();
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

  it("dil seçeneği Türkçe ve İngilizce sunar; seçili dil işaretlidir, seçim hemen uygulanır ve kalıcıdır (P-065)", async () => {
    ciz();
    await screen.findByRole("heading", { name: "Ayarlar" });

    const grup = screen.getByRole("radiogroup", { name: "Dil" });
    const turkce = screen.getByRole("radio", { name: "Türkçe" }) as HTMLInputElement;
    const ingilizce = screen.getByRole("radio", { name: "English" }) as HTMLInputElement;
    expect(grup.contains(turkce)).toBe(true);
    expect(turkce.checked).toBe(true);
    expect(turkce.closest("label")?.textContent).toContain("✓");
    expect(ingilizce.closest("label")?.textContent).not.toContain("✓");
    expect(screen.getByText(/İngilizce çeviri şimdilik kısmi/i)).toBeTruthy();

    fireEvent.click(ingilizce);
    // Belge dili çeviri tamamlanana dek tr kalır; yalnız çevrilen kart lang="en" taşır (31 Ekim).
    expect(document.documentElement.lang).toBe("tr");
    expect(document.documentElement.dataset.language).toBe("en");
    expect(localStorage.getItem("fusion.language.v1")).toBe("en");
    expect((screen.getByRole("radio", { name: "English" }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole("radio", { name: "English" }).closest("label")?.textContent).toContain("✓");
    // Ayarlar'ın kendi gezinmesi de anında çevrilir: seçim "uygulanmadı" gibi görünmez.
    expect(screen.getByRole("heading", { name: "Settings" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "General" })).toBeTruthy();
    const tema = screen.getByRole("combobox", { name: "Theme" });
    expect(tema.closest("article")?.getAttribute("lang")).toBe("en");

    fireEvent.click(screen.getByRole("radio", { name: "Türkçe" }));
    expect(document.documentElement.dataset.language).toBe("tr");
    expect(screen.getByRole("heading", { name: "Ayarlar" })).toBeTruthy();
  });

  it("aynı bölüm yeniden istenince Ayarlar oraya döner ve istenen satıra odaklanır (menü › Dil)", async () => {
    const fake = client();
    const props = { client: fake, onClose: () => undefined, onThemeChange: () => undefined, themePreference: "system" as const };
    const view = render(<Settings {...props} />);
    await screen.findByRole("heading", { name: "Ayarlar" });
    fireEvent.click(screen.getByRole("button", { name: "Bildirimler" }));
    expect(screen.getByRole("button", { name: "Bildirimler" }).getAttribute("aria-current")).toBe("page");

    view.rerender(<Settings {...props} initialFocus="settings-language" initialSection="genel" requestKey={1} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Genel" }).getAttribute("aria-current")).toBe("page"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("radiogroup", { name: "Dil" })));
  });

  it("erişilebilirlik kartı yazı boyutunu belge köküne uygular (P-065)", async () => {
    ciz();
    await screen.findByRole("heading", { name: "Ayarlar" });
    fireEvent.change(screen.getByRole("combobox", { name: "Yazı boyutu" }), { target: { value: "large" } });
    expect(document.documentElement.dataset.fontScale).toBe("large");
    fireEvent.click(screen.getByRole("checkbox", { name: "Yüksek kontrast" }));
    expect(document.documentElement.dataset.contrast).toBe("high");
    fireEvent.change(screen.getByRole("combobox", { name: "Yazı boyutu" }), { target: { value: "normal" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "Yüksek kontrast" }));
    expect(document.documentElement.dataset.fontScale).toBeUndefined();
    expect(document.documentElement.dataset.contrast).toBeUndefined();
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
    const otomatik = screen.getByText("Otomatik").closest(".settings__choice");
    expect(otomatik?.getAttribute("data-active")).toBe("true");
    expect(screen.getByText(/yalnız riskli işlemde sorar/i)).toBeTruthy();
    expect(screen.getByText("İzinleri atla")).toBeTruthy();
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

    fireEvent.click(screen.getByRole("button", { name: /Manuel/ }));
    expect(onRunCommand).toHaveBeenCalledWith("/security");
    const edits = screen.getByRole("button", { name: /Düzenlemeleri kabul et/ });
    await waitFor(() => expect((edits as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(edits);
    expect(onRunCommand).toHaveBeenCalledWith("/edits");
    expect(onRunCommand).toHaveBeenCalledTimes(2);
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
    bolum("Kişiselleştirme");

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

describe("Nasıl yapılır", () => {
  it("Sistem grubunun en altında durur ve konuları ekran görüntüleriyle açar", async () => {
    ciz();
    const sistem = screen.getByRole("navigation", { name: "Ayar bölümleri" }).querySelectorAll("button");
    expect(sistem[sistem.length - 1].textContent).toContain("Nasıl yapılır");
    bolum("Nasıl yapılır");
    expect(await screen.findByRole("heading", { name: "Chrome eklentisi", level: 3 })).toBeTruthy();
    expect(screen.getAllByRole("img").length).toBeGreaterThan(10);
  });

  it("Ayarlar'da aç düğmesi ilgili ayar bölümüne geçirir", async () => {
    ciz();
    bolum("Nasıl yapılır");
    fireEvent.change(await screen.findByLabelText("Konularda ara"), { target: { value: "Eklentiyi kur" } });
    fireEvent.click(screen.getByRole("button", { name: "Ayarlar'da aç" }));
    expect(await screen.findByRole("heading", { name: "Chrome eklentisi" })).toBeTruthy();
  });
});

it("ayar menüsü görünür Ayarlar başlığını sunar", () => {
 ciz();
 expect(screen.getByRole("heading", { name: "Ayarlar" }).className).toBe("settings__title");
});

describe("Settings — dalga 4 (U2-37, U2-38, U2-53, U2-54)", () => {
  it("diyalog aria-modal'dır ve Tab odağı dışarı kaçırmaz", async () => {
    ciz();
    const dialog = await screen.findByRole("dialog", { name: "Ayarlar" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const focusable = Array.from(dialog.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled]), select:not([disabled])"));
    const last = focusable[focusable.length - 1];
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).toBe(focusable[0]);
  });

  it("yazarken Escape kaydedilmemiş girdiyi silmez: alandan çıkar, ikinci Escape kapatır", async () => {
    const onClose = vi.fn();
    ciz({ onClose });
    bolum("Kişiselleştirme");
    const input = await screen.findByRole("textbox", { name: "Yeni anı" });
    input.focus();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    expect(document.activeElement).not.toBe(input);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("üst bileşen her çizimde yeni onClose verse de odak çalınmaz", async () => {
    const fake = client();
    const props = { client: fake, onThemeChange: () => undefined, themePreference: "system" as const };
    const { rerender } = render(<Settings {...props} onClose={() => undefined} />);
    bolum("Kişiselleştirme");
    const input = await screen.findByRole("textbox", { name: "Yeni anı" });
    input.focus();
    rerender(<Settings {...props} onClose={() => undefined} />);
    expect(document.activeElement).toBe(input);
  });

  it("arama Ses, İzin modu gibi bölümleri de bulur ve bölüm başlığına odaklanır", async () => {
    ciz();
    fireEvent.change(await screen.findByRole("searchbox", { name: "Ayarları ara" }), { target: { value: "mikrofon" } });
    fireEvent.click(screen.getByRole("button", { name: "Ses ve konuşma ayarları" }));
    await waitFor(() => expect(document.activeElement?.id).toBe("settings-section-heading"));
    expect(document.activeElement?.textContent).toBe("Ses");
  });

  it("hata uyarı olarak duyurulur; veri gerektirmeyen bölümde 'yükleniyor' notu çıkmaz", async () => {
    const fake = client();
    vi.mocked(fake.request).mockImplementation(async (name: string) => name === "kontrol.durum" ? { ok: false, metin: "çekirdek yok" } : { ok: true });
    ciz({ client: fake });
    expect((await screen.findByRole("alert")).textContent).toContain("çekirdek yok");
    vi.mocked(fake.request).mockImplementation(() => new Promise(() => undefined));
    cleanup();
    ciz({ client: fake });
    expect(screen.queryByText("Ayarlar yükleniyor…")).toBeNull();
    bolum("Gelişmiş");
    expect(screen.getByText("Ayarlar yükleniyor…")).toBeTruthy();
  });
});

describe("Settings — dalga 4 bölümleri (U2-48, U2-50, U2-51)", () => {
  it("İzinleri atla tek tıkla açılmaz; önce açık onay ister (U2-51)", async () => {
    const onRunCommand = vi.fn(async () => ({ ok: true }));
    ciz({ onRunCommand });
    bolum("İzinler");
    await screen.findByText("İzinleri atla");
    fireEvent.click(screen.getByRole("button", { name: /İzinleri atla/ }));
    expect(onRunCommand).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("hiçbir");
    fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(onRunCommand).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /İzinleri atla/ }));
    fireEvent.click(screen.getByRole("button", { name: "Evet, izinleri atla" }));
    await waitFor(() => expect(onRunCommand).toHaveBeenCalledWith("/bypass"));
    // Diğer modlar onaysız geçer.
    fireEvent.click(screen.getByRole("button", { name: /Manuel/ }));
    await waitFor(() => expect(onRunCommand).toHaveBeenCalledWith("/security"));
  });

  it("aday listesi eksik gelirse Modeller bölümü çökmez (U2-50)", async () => {
    const fake = client();
    const inner = vi.mocked(fake.request).getMockImplementation()!;
    vi.mocked(fake.request).mockImplementation(async (name: string, data: Record<string, unknown>) => {
      const result = await inner(name, data);
      if (name === "kontrol.durum") { const { adaylar: _drop, ...model } = (result as { model: Record<string, unknown> }).model; return { ...result, model }; }
      return result;
    });
    ciz({ client: fake });
    bolum("Modeller");
    expect(await screen.findByText("Aday havuzu")).toBeTruthy();
    expect(screen.getByText("Yok")).toBeTruthy();
  });

  it("Zeka durumu eksik listelerle gelse de çökmez ve yükleme hatasında yeniden dene sunar (U2-50)", async () => {
    const fake = client();
    const inner = vi.mocked(fake.request).getMockImplementation()!;
    let kir = true;
    vi.mocked(fake.request).mockImplementation(async (name: string, data: Record<string, unknown>) => {
      if (name === "zeka.durum") {
        if (kir) throw new Error("zeka kapalı");
        return { ok: true, motor: "agent" };
      }
      return inner(name, data);
    });
    ciz({ client: fake });
    bolum("Zeka");
    expect((await screen.findByRole("alert")).textContent).toContain("zeka kapalı");
    kir = false;
    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    // Ayarlar kabuğu başlığı tek kez yazar; panel içi çift başlık yok (U2-54).
    expect(screen.getAllByRole("heading", { name: "Zeka" })).toHaveLength(1);
  });

  it("captcha doğrulama döngüsü bölüm kapanınca durur ve oturumu kaydetmez (U2-48)", async () => {
    vi.useFakeTimers();
    try {
      const fake = client();
      const inner = vi.mocked(fake.request).getMockImplementation()!;
      vi.mocked(fake.request).mockImplementation(async (name: string, data: Record<string, unknown>) => {
        if (name === "model.roller") return { ok: true, roller: { agent: "", teacher: "", judge: "", candidates: ["x"] }, secenekler: [], oturumlar: [{ saglayici: "gemini_web", hesap: "a", etiket: "Gemini", dogrulandi: false }] };
        if (name === "web.giris") return { ok: true, pid: 7 };
        if (name === "web.giris_durumu") return { ok: true, acik: true };
        return inner(name, data);
      });
      const { unmount } = render(<Settings client={fake} onClose={() => undefined} onThemeChange={() => undefined} themePreference="system" initialSection="modeller" />);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      fireEvent.click(screen.getByRole("button", { name: "Captcha'yı doğrula" }));
      await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
      const yoklama = () => vi.mocked(fake.request).mock.calls.filter(([n]) => n === "web.giris_durumu").length;
      expect(yoklama()).toBe(1);
      unmount();
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
      expect(yoklama()).toBeLessThanOrEqual(2);
      expect(vi.mocked(fake.request).mock.calls.some(([n]) => n === "web.baglan")).toBe(false);
    } finally { vi.useRealTimers(); }
  });
});

describe("Settings — kurulumu yeniden aç (U5-47)", () => {
  it("Genel bölümünde 'Kurulumu yeniden aç' düğmesi geri çağrıyı tetikler", () => {
    const reopen = vi.fn();
    ciz({ onReopenSetup: reopen });
    fireEvent.click(screen.getByRole("button", { name: "Kurulumu yeniden aç" }));
    expect(reopen).toHaveBeenCalledTimes(1);
  });

  it("geri çağrı verilmezse kurulum kartı gösterilmez", () => {
    ciz();
    expect(screen.queryByRole("button", { name: "Kurulumu yeniden aç" })).toBeNull();
  });
});

describe("Ayarlar › Hesap", () => {
  it("hesap içeriğini doğrudan gösterir; ayrı bir 'Hesabımı aç' adımı yoktur", () => {
    render(<Settings accountContent={<div data-testid="hesap-icerigi">Kullanici</div>} client={client() as unknown as ProtocolClient} initialSection="hesap" onClose={() => undefined} onOpenAccount={() => undefined} onThemeChange={() => undefined} themePreference="dark" />);
    expect(screen.getByTestId("hesap-icerigi").textContent).toBe("Kullanici");
    expect(screen.queryByRole("button", { name: "Hesabımı aç" })).toBeNull();
  });
});
