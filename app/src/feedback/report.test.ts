import { describe, expect, it } from "vitest";
import { ISSUE_URL_LIMIT, buildIssueUrl, redact, reportBody } from "./report";

const ortam = { surum: "0.4.6", platform: "macOS arm64" };

describe("redact", () => {
  it("kullanıcı klasörünü ~ ile değiştirir", () => {
    expect(redact("/Users/kullanici/Desktop/proje/a.ts okunamadı")).toBe("~/Desktop/proje/a.ts okunamadı");
  });

  it("API anahtarı ve Bearer token'ı gizler", () => {
    const metin = "anahtar nvapi-ABCdef1234567890xyz ve sk-proj-abcdefghijklmnop12 Authorization: Bearer eyJhbGciOi.abc.def";
    const temiz = redact(metin);
    expect(temiz).not.toContain("nvapi-ABC");
    expect(temiz).not.toContain("sk-proj-abc");
    expect(temiz).not.toContain("eyJhbGciOi");
    expect(temiz).toContain("[gizlendi]");
  });

  it("e-posta adresini gizler", () => {
    expect(redact("hesap ali@ornek.com bulunamadı")).toBe("hesap [e-posta] bulunamadı");
  });
});

describe("reportBody", () => {
  it("hata raporunda mesaj, ayrıntı ve ortam bilgisi bulunur", () => {
    const govde = reportBody({ tur: "hata", mesaj: "Tur yarıda kaldı", ayrinti: "TypeError: x is undefined" }, ortam);
    expect(govde).toContain("Tur yarıda kaldı");
    expect(govde).toContain("TypeError: x is undefined");
    expect(govde).toContain("0.4.6");
    expect(govde).toContain("macOS arm64");
  });

  it("ayrıntı yoksa teknik bölüm yazılmaz", () => {
    const govde = reportBody({ tur: "geri-bildirim", mesaj: "Harika olmuş" }, ortam);
    expect(govde).not.toContain("Teknik ayrıntı");
  });
});

describe("buildIssueUrl", () => {
  it("GitHub yeni issue adresini başlık önekiyle doldurur", () => {
    const url = new URL(buildIssueUrl({ tur: "hata", mesaj: "Model cevap vermedi" }, ortam));
    expect(url.origin + url.pathname).toBe("https://github.com/emirhhan/fusion-cli/issues/new");
    expect(url.searchParams.get("title")).toBe("[Hata] Model cevap vermedi");
    expect(url.searchParams.get("body")).toContain("Model cevap vermedi");
  });

  it("geri bildirim başlığı ayrı önek alır ve uzun ilk satır kısaltılır", () => {
    const uzun = "a".repeat(200);
    const url = new URL(buildIssueUrl({ tur: "geri-bildirim", mesaj: `${uzun}\nikinci satır` }, ortam));
    const baslik = url.searchParams.get("title") ?? "";
    expect(baslik.startsWith("[Geri bildirim] ")).toBe(true);
    expect(baslik.length).toBeLessThanOrEqual(96);
  });

  it("çok uzun ayrıntıda adres sınırı aşılmaz ve kısaltma belirtilir", () => {
    const url = buildIssueUrl({ tur: "hata", mesaj: "çöktü", ayrinti: "satır\n".repeat(5000) }, ortam);
    expect(url.length).toBeLessThanOrEqual(ISSUE_URL_LIMIT);
    expect(new URL(url).searchParams.get("body")).toContain("kısaltıldı");
  });

  it("gönderilen metin de gizlenir", () => {
    const url = buildIssueUrl({ tur: "hata", mesaj: "/Users/kullanici/x bozuk" }, ortam);
    expect(url).not.toContain("kullanici");
  });
});

describe("destek raporu sır sınırları", () => {
  it.each([
    ['refresh_token="SENTINEL_REFRESH_VALUE"', 'SENTINEL_REFRESH_VALUE'],
    [JSON.stringify({ password: 'prefix\"SENTINEL_QUOTED_TAIL' }), 'SENTINEL_QUOTED_TAIL'],
    ['{"password":"SENTINEL TWO WORDS"}', 'SENTINEL TWO WORDS'],
    ['-----BEGIN PRIVATE KEY-----\nSENTINEL_PEM_BODY\n-----END PRIVATE KEY-----', 'SENTINEL_PEM_BODY'], // gitleaks:allow
    ['-----BEGIN RSA PRIVATE KEY-----\nSENTINEL_TRUNCATED_BODY', 'SENTINEL_TRUNCATED_BODY'],
    ['https://user:SENTINEL_URL_PASSWORD@example.com/a?key=SENTINEL_QUERY_VALUE#SENTINEL_FRAGMENT', 'SENTINEL_URL_PASSWORD'],
    ['https://example.com/a?unknown=SENTINEL_QUERY_VALUE', 'SENTINEL_QUERY_VALUE'],
    ['https%3A%2F%2Fexample.com%2Fa%3Ftoken%3DSENTINEL_ENCODED', 'SENTINEL_ENCODED'],
    ['progress 100% https%3A%2F%2Fexample.com%2Fa%3Funknown%3DSENTINEL_ENCODED_MIXED', 'SENTINEL_ENCODED_MIXED'],
  ])("önizleme ve issue adresi %s içindeki sırrı taşımaz", (source, sentinel) => {
    const input = { tur: 'hata' as const, mesaj: source, ayrinti: source };
    expect(reportBody(input, ortam)).not.toContain(sentinel);
    expect(decodeURIComponent(buildIssueUrl(input, ortam))).not.toContain(sentinel);
  });
  it("ortam ve ayrıntı override da aynı filtreden geçer", () => {
    const body = reportBody({ tur: 'hata', mesaj: 'Hata' }, { surum: 'access_token=SENTINEL_ENV', platform: 'macOS' }, 'password=SENTINEL_OVERRIDE');
    expect(body).not.toContain('SENTINEL_ENV');
    expect(body).not.toContain('SENTINEL_OVERRIDE');
  });
});
