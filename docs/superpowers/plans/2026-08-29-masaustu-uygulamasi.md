# Masaüstü Uygulaması Uygulama Planı

> **Agentic worker'lar için:** ZORUNLU ALT BECERİ: Bu planı görev görev uygulamak
> için `superpowers:subagent-driven-development` (önerilen) ya da
> `superpowers:executing-plans` kullan. Adımlar takip için checkbox (`- [ ]`)
> sözdizimi kullanır.

**Hedef:** Fusion'ın masaüstü uygulaması — `fusion app` stdio protokolünü tüketen,
ölçülmüş görsel dili uygulayan bir Tauri masaüstü istemcisi.

**Mimari:** Tauri 2 kabuğu Python çekirdeğini alt süreç olarak doğurur ve stdio
köprüsünü kurar. Rust tarafı ince: süreç ömrü ve satır aktarımı. Ürün mantığı ve
tüm ekranlar React + TypeScript'te. Uygulama gerçeğin kaynağı değildir; model,
mod ve komut listesi protokolden okunur.

**Teknoloji:** Tauri 2, React 18, TypeScript, Vite. Node 22, Rust 1.98, Xcode CLT
makinede doğrulandı.

## Global Kısıtlar

- Uygulama kodu `app/` dizininde durur; `src/fusion_cli/` altına DOKUNULMAZ.
- Kullanıcıya görünen tüm metinler **Türkçe**.
- Tanımlayıcılar **İngilizce**, TypeScript'te `camelCase`, bileşenler `PascalCase`.
- Renkler CSS özel değişkenlerinden gelir; hiçbir bileşen ham hex yazmaz.
  Değerler ölçülmüştür (`docs/superpowers/specs/2026-08-29-uygulama-gorsel-dil.md`):
  zemin `#FFFFFF`, kenar çubuğu `#F9F9FA`, seçili satır `#EFEFF0`,
  kullanıcı balonu `#F5F5F5`, birincil buton `#000000`, vurgu hapı `#EBEBFA`,
  sönük metin `#7C7C7D`, kenarlık `#E9E9EB`.
- Kenar çubuğu genişliği 281px sabit; içerik alanı esnek.
- Konuşma görünümü SİMETRİK DEĞİLDİR: kullanıcı mesajı kabarcıklı, asistan
  mesajı kabarcıksız tam genişlikte metin.
- Rust tarafına ürün mantığı YAZILMAZ; yalnız süreç ve aktarım.
- Dosya 400 satırı, fonksiyon 50 satırı geçmez.
- Hiçbir protokol hatası arayüzü çökertmez.
- Kalite kapısı: `npm run build` (tip denetimi dahil) ve `npm test` temiz
  olmadan commit atılmaz.
- Commit mesajı conventional format, açıklama **Türkçe**, faz/adım numarası ve
  author/co-author bilgisi YOK.

## Dosya Yapısı

| Dosya | Sorumluluk |
|---|---|
| `app/src-tauri/src/core_process.rs` | Çekirdek sürecini bul, başlat, satır aktar |
| `app/src/protocol/client.ts` | Protokol istemcisi: istek/cevap eşleştirme, olay yayını |
| `app/src/protocol/types.ts` | Tel biçiminin TypeScript tipleri |
| `app/src/theme/tokens.css` | Ölçülmüş renk ve ölçü değişkenleri |
| `app/src/screens/Sidebar.tsx` | Oturum listesi ve gezinme |
| `app/src/screens/Conversation.tsx` | Mesajlar ve olay akışı |
| `app/src/screens/EmptyState.tsx` | Boş başlangıç ekranı |
| `app/src/dialogs/Approval.tsx` | Onay diyaloğu |
| `app/src/dialogs/Picker.tsx` | Çok adımlı seçici |
| `app/src/screens/Settings.tsx` | Komut defterinden kurulan ayarlar |

---

### Task 1: Tauri iskeleti ve çekirdek köprüsü

**Files:**
- Create: `app/` (Tauri iskeleti)
- Create: `app/src-tauri/src/core_process.rs`
- Create: `app/src/protocol/types.ts`
- Create: `app/src/protocol/client.ts`
- Test: `app/src/protocol/client.test.ts`

**Interfaces:**
- Produces: `ProtocolClient` — `request(name, data) -> Promise<result>`,
  `onEvent(handler)`, `onQuestion(handler)`, `reply(id, data)`, `close()`.

Bu görev bittiğinde **çalışan bir pencere** olur: açılır, çekirdeği başlatır,
`oturum.durum` isteği atar ve dönen kök dizini ekrana basar. Görsel yok, ama
zincirin tamamı kanıtlanmış olur.

- [ ] **Step 1: İskeleti kur**

```bash
cd /Users/motogate/Desktop/01-Projeler/fusion-cli
npm create tauri-app@latest app -- --template react-ts --manager npm --yes
cd app && npm install
```
Beklenen: `app/src-tauri/` ve `app/src/` oluşur, `npm run tauri --version` çalışır.

- [ ] **Step 2: Protokol tiplerini yaz**

`app/src/protocol/types.ts`:

```typescript
/** Tel biçimi: satır başına bir JSON nesnesi. Anahtarlar Türkçedir. */

export type GelenTip = "olay" | "sonuc" | "soru";

export interface GelenMesaj {
  tip: GelenTip;
  id?: string;
  veri: Record<string, unknown>;
}

export interface Istek {
  tip: "istek";
  id: string;
  ad: string;
  veri: Record<string, unknown>;
}

export interface Cevap {
  tip: "cevap";
  id: string;
  veri: Record<string, unknown>;
}

/** Onay ya da serbest metin sorusu. `tur` alanı hangisi olduğunu söyler. */
export interface Soru {
  tur: "onay" | "soru";
  arac?: string;
  argumanlar?: Record<string, string>;
  tehlike?: string | null;
  soru?: string;
  secenekler?: { deger?: string; etiket: string; aciklama?: string }[];
  onerilen?: string | null;
}
```

- [ ] **Step 3: Kırmızı testi yaz**

`app/src/protocol/client.test.ts`:

```typescript
import { describe, expect, it, vi } from "vitest";
import { ProtocolClient } from "./client";

/** Testte gerçek süreç yok: satır gönderen/alan sahte bir taşıma kullanılır. */
function sahteTasima() {
  const yazilan: string[] = [];
  let dinleyici: ((satir: string) => void) | null = null;
  return {
    yazilan,
    gonder: (satir: string) => yazilan.push(satir),
    dinle: (f: (satir: string) => void) => {
      dinleyici = f;
    },
    al: (satir: string) => dinleyici?.(satir),
  };
}

describe("ProtocolClient", () => {
  it("istek gönderir ve sonucu eşleştirir", async () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);

    const bekleyen = c.request("oturum.durum", {});
    const gonderilen = JSON.parse(t.yazilan[0]);
    expect(gonderilen.tip).toBe("istek");
    expect(gonderilen.ad).toBe("oturum.durum");

    t.al(JSON.stringify({ tip: "sonuc", id: gonderilen.id, veri: { ok: true, kok: "/x" } }));
    await expect(bekleyen).resolves.toEqual({ ok: true, kok: "/x" });
  });

  it("olayları dinleyiciye iletir", () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const gorulen: unknown[] = [];
    c.onEvent((e) => gorulen.push(e));

    t.al(JSON.stringify({ tip: "olay", veri: { olay: "TurnFinished" } }));

    expect(gorulen).toEqual([{ olay: "TurnFinished" }]);
  });

  it("soruyu iletir ve cevabı aynı kimlikle yollar", () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    let gelenKimlik = "";
    c.onQuestion((id) => {
      gelenKimlik = id;
    });

    t.al(JSON.stringify({ tip: "soru", id: "12", veri: { tur: "onay" } }));
    c.reply(gelenKimlik, { secim: "once" });

    expect(JSON.parse(t.yazilan[0])).toEqual({ tip: "cevap", id: "12", veri: { secim: "once" } });
  });

  it("bozuk satır istemciyi düşürmez", () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);
    const gorulen: unknown[] = [];
    c.onEvent((e) => gorulen.push(e));

    expect(() => t.al("{bozuk")).not.toThrow();
    t.al(JSON.stringify({ tip: "olay", veri: { olay: "X" } }));

    expect(gorulen).toEqual([{ olay: "X" }]);
  });

  it("eşleşmeyen sonuç kimliği yok sayılır", () => {
    const t = sahteTasima();
    const c = new ProtocolClient(t.gonder, t.dinle);

    expect(() => t.al(JSON.stringify({ tip: "sonuc", id: "yok", veri: {} }))).not.toThrow();
  });
});
```

- [ ] **Step 4: Testin başarısız olduğunu gör**

```bash
cd app && npm install -D vitest && npx vitest run src/protocol/client.test.ts
```
Beklenen: FAIL — `Cannot find module './client'`

- [ ] **Step 5: İstemciyi yaz**

`app/src/protocol/client.ts`:

```typescript
import type { Cevap, GelenMesaj, Istek } from "./types";

type Cozucu = (veri: Record<string, unknown>) => void;

/**
 * Protokol istemcisi.
 *
 * Taşımadan bağımsızdır: satır gönderen ve satır dinleyen iki fonksiyon alır.
 * Böylece gerçek süreç başlatmadan test edilebilir.
 *
 * Hiçbir bozuk satır istemciyi düşürmez; çözülemeyen satır atlanır.
 */
export class ProtocolClient {
  private sayac = 0;
  private bekleyen = new Map<string, Cozucu>();
  private olayDinleyicileri: ((veri: Record<string, unknown>) => void)[] = [];
  private soruDinleyicileri: ((id: string, veri: Record<string, unknown>) => void)[] = [];

  constructor(
    private readonly gonder: (satir: string) => void,
    dinle: (f: (satir: string) => void) => void,
  ) {
    dinle((satir) => this.satirAlindi(satir));
  }

  request(ad: string, veri: Record<string, unknown>): Promise<Record<string, unknown>> {
    const id = String(++this.sayac);
    const istek: Istek = { tip: "istek", id, ad, veri };
    return new Promise((cozumle) => {
      this.bekleyen.set(id, cozumle);
      this.gonder(JSON.stringify(istek));
    });
  }

  reply(id: string, veri: Record<string, unknown>): void {
    const cevap: Cevap = { tip: "cevap", id, veri };
    this.gonder(JSON.stringify(cevap));
  }

  onEvent(f: (veri: Record<string, unknown>) => void): void {
    this.olayDinleyicileri.push(f);
  }

  onQuestion(f: (id: string, veri: Record<string, unknown>) => void): void {
    this.soruDinleyicileri.push(f);
  }

  private satirAlindi(satir: string): void {
    let mesaj: GelenMesaj;
    try {
      mesaj = JSON.parse(satir) as GelenMesaj;
    } catch {
      return; // Çözülemeyen satır atlanır; arayüz bozulmaz.
    }
    if (!mesaj || typeof mesaj !== "object") return;
    if (mesaj.tip === "olay") {
      this.olayDinleyicileri.forEach((f) => f(mesaj.veri ?? {}));
      return;
    }
    if (mesaj.tip === "soru" && mesaj.id) {
      this.soruDinleyicileri.forEach((f) => f(mesaj.id as string, mesaj.veri ?? {}));
      return;
    }
    if (mesaj.tip === "sonuc" && mesaj.id) {
      const cozumle = this.bekleyen.get(mesaj.id);
      if (!cozumle) return; // Eşleşmeyen kimlik yok sayılır.
      this.bekleyen.delete(mesaj.id);
      cozumle(mesaj.veri ?? {});
    }
  }
}
```

- [ ] **Step 6: Testin geçtiğini gör**

```bash
cd app && npx vitest run src/protocol/client.test.ts
```
Beklenen: 5 passed

- [ ] **Step 7: Rust köprüsünü yaz**

`app/src-tauri/src/core_process.rs`:

```rust
//! Fusion çekirdeğini alt süreç olarak yönetir ve stdio satırlarını aktarır.
//!
//! Burada ürün mantığı YOKTUR: süreç bulunur, başlatılır, satırlar iki yöne
//! taşınır. Karar veren taraf her zaman arayüzdür.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter};

pub struct CoreProcess {
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
}

impl CoreProcess {
    pub fn new() -> Self {
        Self { child: Mutex::new(None), stdin: Mutex::new(None) }
    }

    /// Çekirdeği başlat. Önce paketlenmiş sidecar, bulunamazsa sistemdeki
    /// `fusion` komutu denenir; ikisi de yoksa hata döner ve arayüz kurulum
    /// yönergesi gösterir.
    pub fn start(&self, app: AppHandle) -> Result<(), String> {
        let mut cocuk = Command::new("fusion")
            .arg("app")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("çekirdek başlatılamadı: {e}"))?;

        let cikti = cocuk.stdout.take().ok_or("çekirdek çıktısı alınamadı")?;
        *self.stdin.lock().unwrap() = cocuk.stdin.take();
        *self.child.lock().unwrap() = Some(cocuk);

        std::thread::spawn(move || {
            for satir in BufReader::new(cikti).lines() {
                match satir {
                    Ok(s) => {
                        let _ = app.emit("cekirdek-satir", s);
                    }
                    Err(_) => break,
                }
            }
            let _ = app.emit("cekirdek-kapandi", ());
        });
        Ok(())
    }

    /// Arayüzden gelen satırı çekirdeğe yaz.
    pub fn send(&self, satir: String) -> Result<(), String> {
        let mut kilit = self.stdin.lock().unwrap();
        let giris = kilit.as_mut().ok_or("çekirdek çalışmıyor")?;
        writeln!(giris, "{satir}").map_err(|e| format!("yazılamadı: {e}"))?;
        giris.flush().map_err(|e| format!("boşaltılamadı: {e}"))
    }

    /// Pencere kapanınca çekirdeği sonlandır.
    pub fn stop(&self) {
        *self.stdin.lock().unwrap() = None; // stdin kapanır, çekirdek düzgün çıkar
        if let Some(mut c) = self.child.lock().unwrap().take() {
            let _ = c.wait();
        }
    }
}
```

`app/src-tauri/src/lib.rs` içine komutları ekle:

```rust
mod core_process;
use core_process::CoreProcess;

#[tauri::command]
fn cekirdek_baslat(app: tauri::AppHandle, durum: tauri::State<CoreProcess>) -> Result<(), String> {
    durum.start(app)
}

#[tauri::command]
fn cekirdege_yaz(satir: String, durum: tauri::State<CoreProcess>) -> Result<(), String> {
    durum.send(satir)
}
```

`run()` içinde `.manage(CoreProcess::new())` ve
`.invoke_handler(tauri::generate_handler![cekirdek_baslat, cekirdege_yaz])` kaydet.

- [ ] **Step 8: Uygulamayı çalıştır ve zinciri kanıtla**

`app/src/App.tsx` içeriğini geçici olarak şu doğrulama ile değiştir:

```tsx
import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ProtocolClient } from "./protocol/client";

export default function App() {
  const [durum, setDurum] = useState("bağlanıyor…");

  useEffect(() => {
    let istemci: ProtocolClient | null = null;
    const kur = async () => {
      await invoke("cekirdek_baslat");
      istemci = new ProtocolClient(
        (satir) => void invoke("cekirdege_yaz", { satir }),
        (f) => void listen<string>("cekirdek-satir", (o) => f(o.payload)),
      );
      const sonuc = await istemci.request("oturum.durum", {});
      setDurum(JSON.stringify(sonuc));
    };
    kur().catch((e) => setDurum(`hata: ${String(e)}`));
  }, []);

  return <pre style={{ padding: 24, fontFamily: "monospace" }}>{durum}</pre>;
}
```

Çalıştır: `cd app && npm run tauri dev`
Beklenen: pencere açılır ve `{"ok":true,"kok":"…","model":"…","mod":"auto"}` benzeri
bir satır gösterir. Bu, zincirin uçtan uca çalıştığının kanıtıdır.

- [ ] **Step 9: Commit**

```bash
cd /Users/motogate/Desktop/01-Projeler/fusion-cli
git add app
git commit -m "feat(app): Tauri iskeletini kur ve çekirdek köprüsünü bağla"
```

---

### Task 2: Tasarım token'ları ve kabuk düzeni

**Files:**
- Create: `app/src/theme/tokens.css`
- Create: `app/src/screens/Shell.tsx`
- Modify: `app/src/App.tsx`
- Test: `app/src/theme/tokens.test.ts`

**Interfaces:**
- Consumes: `ProtocolClient` (Task 1).
- Produces: `Shell` bileşeni — solda 281px kenar çubuğu, sağda esnek içerik.

- [ ] **Step 1: Token'ları yaz**

`app/src/theme/tokens.css`:

```css
/* Ölçülmüş değerler. Kaynak: docs/superpowers/specs/2026-08-29-uygulama-gorsel-dil.md
   Hiçbir bileşen ham hex yazmaz; hepsi buradan gelir. */
:root {
  --zemin: #ffffff;
  --kenar-cubugu: #f9f9fa;
  --secili-satir: #efeff0;
  --kullanici-balonu: #f5f5f5;
  --birincil-buton: #000000;
  --vurgu-hapi: #ebebfa;
  --sonuk-metin: #7c7c7d;
  --kenarlik: #e9e9eb;

  --kenar-cubugu-genislik: 281px;
  --icerik-en-fazla: 768px;
  --yaricap: 12px;
  --bosluk-birim: 8px;
}
```

- [ ] **Step 2: Kırmızı testi yaz**

`app/src/theme/tokens.test.ts`:

```typescript
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/** Ölçülmüş değerler sessizce değişmemeli; değişirse referanstan sapılmış olur. */
describe("tasarım token'ları", () => {
  const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

  it("ölçülmüş renkleri taşır", () => {
    expect(css).toContain("--zemin: #ffffff");
    expect(css).toContain("--kenar-cubugu: #f9f9fa");
    expect(css).toContain("--secili-satir: #efeff0");
    expect(css).toContain("--kullanici-balonu: #f5f5f5");
    expect(css).toContain("--vurgu-hapi: #ebebfa");
  });

  it("ölçülmüş kenar çubuğu genişliğini taşır", () => {
    expect(css).toContain("--kenar-cubugu-genislik: 281px");
  });
});
```

- [ ] **Step 3: Testin geçtiğini gör**

```bash
cd app && npx vitest run src/theme/tokens.test.ts
```
Beklenen: 2 passed

- [ ] **Step 4: Kabuğu yaz**

`app/src/screens/Shell.tsx`:

```tsx
import type { ReactNode } from "react";
import "../theme/tokens.css";

/** Sol kenar çubuğu sabit genişlikte, içerik alanı esnek. Ölçülmüş düzen. */
export function Shell({ kenar, icerik }: { kenar: ReactNode; icerik: ReactNode }) {
  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--zemin)" }}>
      <aside
        style={{
          width: "var(--kenar-cubugu-genislik)",
          flexShrink: 0,
          background: "var(--kenar-cubugu)",
          borderRight: "1px solid var(--kenarlik)",
          overflowY: "auto",
        }}
      >
        {kenar}
      </aside>
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {icerik}
      </main>
    </div>
  );
}
```

- [ ] **Step 5: Görsel doğrulama**

`npm run tauri dev` ile pencereyi aç; sol panelin `#F9F9FA`, sağın beyaz olduğunu
ve panel genişliğinin 281px olduğunu gör.

- [ ] **Step 6: Commit**

```bash
git add app && git commit -m "feat(app): ölçülmüş tasarım token'larını ve kabuk düzenini kur"
```

---

### Task 3: Konuşma ekranı ve olay akışı

**Files:**
- Create: `app/src/screens/Conversation.tsx`
- Create: `app/src/screens/EmptyState.tsx`
- Create: `app/src/protocol/olayMetni.ts`
- Test: `app/src/protocol/olayMetni.test.ts`

**Interfaces:**
- Consumes: `ProtocolClient`, `Shell`.
- Produces: `olayMetni(veri) -> string | null` — olay yükünü okunabilir tek
  satıra çevirir; gösterilmeyecek olaylar için `null`.

- [ ] **Step 1: Kırmızı testi yaz**

`app/src/protocol/olayMetni.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { olayMetni } from "./olayMetni";

describe("olayMetni", () => {
  it("araç çalıştırmayı okunabilir yazar", () => {
    expect(olayMetni({ olay: "ToolExecuted", name: "write_file" })).toContain("write_file");
  });

  it("tur sonucunu açıkça bildirir", () => {
    expect(olayMetni({ olay: "TurnOutcome", status: "completed" })).toContain("tamamlandı");
    expect(olayMetni({ olay: "TurnOutcome", status: "failed" })).toContain("başarısız");
  });

  it("ham JSON sızdırmaz", () => {
    const metin = olayMetni({ olay: "ToolExecuted", name: "run_shell", args: { command: "ls" } });
    expect(metin).not.toContain("{");
  });

  it("bilinmeyen olay için null döner", () => {
    expect(olayMetni({ olay: "BilinmeyenOlay" })).toBeNull();
  });
});
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

```bash
cd app && npx vitest run src/protocol/olayMetni.test.ts
```
Beklenen: FAIL — `Cannot find module './olayMetni'`

- [ ] **Step 3: Çeviriciyi yaz**

`app/src/protocol/olayMetni.ts`:

```typescript
/**
 * Olay yükünü kullanıcıya gösterilecek tek satıra çevirir.
 *
 * Ham JSON asla gösterilmez: kullanıcı ne olduğunu okumak ister, veri yapısını
 * değil. Karşılığı olmayan olaylar `null` döner ve akışta hiç görünmez.
 */
export function olayMetni(veri: Record<string, unknown>): string | null {
  const olay = String(veri.olay ?? "");
  const ad = typeof veri.name === "string" ? veri.name : "";
  switch (olay) {
    case "ToolExecuted":
      return `araç çalıştı: ${ad}`;
    case "ModelCallStarted":
      return "model düşünüyor…";
    case "FilesChanged":
      return `dosyalar değişti: ${(veri.paths as string[] | undefined)?.join(", ") ?? ""}`;
    case "TurnOutcome": {
      const durum = String(veri.status ?? "");
      if (durum === "completed") return "görev tamamlandı";
      if (durum === "partial") return "görev kısmi kaldı";
      return "görev başarısız";
    }
    default:
      return null;
  }
}
```

- [ ] **Step 4: Testin geçtiğini gör**

```bash
cd app && npx vitest run src/protocol/olayMetni.test.ts
```
Beklenen: 4 passed

- [ ] **Step 5: Konuşma ekranını yaz**

`app/src/screens/Conversation.tsx`:

```tsx
export interface Mesaj {
  rol: "kullanici" | "asistan" | "olay";
  metin: string;
}

/**
 * Kullanıcı ve asistan mesajları SİMETRİK DEĞİLDİR.
 *
 * Ölçüldü: kullanıcı mesajı sağa hizalı kabarcık, asistan mesajı kabarcıksız
 * tam genişlikte metin. İki taraflı kabarcık düzeni referansın görünümünü bozar.
 */
export function Conversation({ mesajlar }: { mesajlar: Mesaj[] }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px 0" }}>
      <div style={{ maxWidth: "var(--icerik-en-fazla)", margin: "0 auto", padding: "0 16px" }}>
        {mesajlar.map((m, i) => (
          <div key={i} style={{ marginBottom: 20, display: "flex", justifyContent: m.rol === "kullanici" ? "flex-end" : "flex-start" }}>
            {m.rol === "kullanici" ? (
              <div style={{ background: "var(--kullanici-balonu)", borderRadius: "var(--yaricap)", padding: "10px 16px", maxWidth: "82%" }}>
                {m.metin}
              </div>
            ) : m.rol === "olay" ? (
              <div style={{ color: "var(--sonuk-metin)", fontSize: 13 }}>{m.metin}</div>
            ) : (
              <div style={{ width: "100%", lineHeight: 1.65 }}>{m.metin}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add app && git commit -m "feat(app): konuşma ekranını ve olay akışını çiz"
```

---

### Task 4: Onay diyaloğu

**Files:**
- Create: `app/src/dialogs/Approval.tsx`
- Test: `app/src/dialogs/Approval.test.tsx`

**Interfaces:**
- Consumes: `Soru` tipi (Task 1), `ProtocolClient.reply`.

Protokol sözleşmesi: `soru` mesajının `veri` alanı `tur: "onay"`, `arac`,
`argumanlar`, `tehlike` ve `secenekler` taşır. Yıkıcı işlemde `secenekler`
içinde `session` YOKTUR — çekirdek onu hiç göndermez.

- [ ] **Step 1: Kırmızı testi yaz**

`app/src/dialogs/Approval.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Approval } from "./Approval";

const temel = {
  tur: "onay" as const,
  arac: "write_file",
  argumanlar: { path: "a.txt" },
  tehlike: null,
  secenekler: [
    { deger: "once", etiket: "Bir kez izin ver" },
    { deger: "session", etiket: "Oturum boyunca izin ver" },
    { deger: "deny", etiket: "Reddet" },
  ],
};

describe("Approval", () => {
  it("hangi aracın ve hangi argümanların onaylandığını gösterir", () => {
    render(<Approval soru={temel} onCevap={vi.fn()} />);
    expect(screen.getByText(/write_file/)).toBeTruthy();
    expect(screen.getByText(/a\.txt/)).toBeTruthy();
  });

  it("gelen seçenekleri olduğu gibi çizer", () => {
    render(<Approval soru={temel} onCevap={vi.fn()} />);
    expect(screen.getByText("Oturum boyunca izin ver")).toBeTruthy();
  });

  it("yıkıcı işlemde oturum seçeneği gösterilmez", () => {
    const yikici = { ...temel, tehlike: "dosya siler", secenekler: temel.secenekler.filter((s) => s.deger !== "session") };
    render(<Approval soru={yikici} onCevap={vi.fn()} />);
    expect(screen.queryByText("Oturum boyunca izin ver")).toBeNull();
    expect(screen.getByText(/dosya siler/)).toBeTruthy();
  });

  it("seçim yapılınca değeri bildirir", async () => {
    const onCevap = vi.fn();
    render(<Approval soru={temel} onCevap={onCevap} />);
    screen.getByText("Reddet").click();
    expect(onCevap).toHaveBeenCalledWith({ secim: "deny" });
  });
});
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

```bash
cd app && npm install -D @testing-library/react @testing-library/dom jsdom
npx vitest run src/dialogs/Approval.test.tsx --environment jsdom
```
Beklenen: FAIL — `Cannot find module './Approval'`

- [ ] **Step 3: Diyaloğu yaz**

`app/src/dialogs/Approval.tsx`:

```tsx
import type { Soru } from "../protocol/types";

/**
 * Onay diyaloğu.
 *
 * Seçenekler ÇEKİRDEKTEN gelir ve olduğu gibi çizilir; uygulama kendi listesini
 * kurmaz. Yıkıcı işlemde çekirdek oturum iznini hiç göndermez, bu yüzden burada
 * ayrıca filtrelemeye gerek yoktur — kural tek yerde uygulanır.
 */
export function Approval({
  soru,
  onCevap,
}: {
  soru: Soru;
  onCevap: (veri: Record<string, unknown>) => void;
}) {
  const argumanlar = Object.entries(soru.argumanlar ?? {});
  return (
    <div style={{ background: "var(--zemin)", border: "1px solid var(--kenarlik)", borderRadius: "var(--yaricap)", padding: 20, maxWidth: 480 }}>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>Bu işleme izin verilsin mi?</div>
      <div style={{ fontFamily: "monospace", fontSize: 13, marginBottom: 12 }}>
        {soru.arac}
        {argumanlar.length > 0 && (
          <div style={{ color: "var(--sonuk-metin)", marginTop: 4 }}>
            {argumanlar.map(([k, v]) => `${k}: ${v}`).join("  ·  ")}
          </div>
        )}
      </div>
      {soru.tehlike && (
        <div style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>⚠ {soru.tehlike}</div>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {(soru.secenekler ?? []).map((s) => (
          <button
            key={s.deger ?? s.etiket}
            onClick={() => onCevap({ secim: s.deger })}
            style={{
              padding: "8px 14px",
              borderRadius: 999,
              border: "1px solid var(--kenarlik)",
              background: s.deger === "deny" ? "var(--zemin)" : "var(--birincil-buton)",
              color: s.deger === "deny" ? "inherit" : "#fff",
              cursor: "pointer",
            }}
          >
            {s.etiket}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Testin geçtiğini gör**

```bash
cd app && npx vitest run src/dialogs/Approval.test.tsx --environment jsdom
```
Beklenen: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app && git commit -m "feat(app): onay diyaloğunu çiz"
```

---

### Task 5: Kenar çubuğu ve oturum listesi

**Files:**
- Create: `app/src/screens/Sidebar.tsx`
- Test: `app/src/screens/Sidebar.test.tsx`

- [ ] **Step 1: Kırmızı testi yaz**

`app/src/screens/Sidebar.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

const oturumlar = [
  { session_id: "1", title: "İlk iş", source: "claude" },
  { session_id: "2", title: "İkinci iş", source: "codex" },
];

describe("Sidebar", () => {
  it("oturumları kaynak etiketiyle listeler", () => {
    render(<Sidebar oturumlar={oturumlar} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    expect(screen.getByText("İlk iş")).toBeTruthy();
    expect(screen.getByText(/claude/)).toBeTruthy();
  });

  it("etkin oturumu vurgular", () => {
    const { container } = render(
      <Sidebar oturumlar={oturumlar} etkin="1" onSec={vi.fn()} onYeni={vi.fn()} />,
    );
    const vurgulu = container.querySelectorAll('[data-etkin="true"]');
    expect(vurgulu.length).toBe(1);
  });

  it("oturum yoksa liste bölümü hiç basılmaz", () => {
    render(<Sidebar oturumlar={[]} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    expect(screen.queryByText("Sohbetler")).toBeNull();
  });

  it("yeni sohbet tıklanınca bildirir", () => {
    const onYeni = vi.fn();
    render(<Sidebar oturumlar={[]} etkin={null} onSec={vi.fn()} onYeni={onYeni} />);
    screen.getByText("Yeni sohbet").click();
    expect(onYeni).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

```bash
cd app && npx vitest run src/screens/Sidebar.test.tsx --environment jsdom
```
Beklenen: FAIL — `Cannot find module './Sidebar'`

- [ ] **Step 3: Kenar çubuğunu yaz**

`app/src/screens/Sidebar.tsx`:

```tsx
export interface OturumSatiri {
  session_id: string;
  title: string;
  source: string;
}

/** Oturum yoksa "Sohbetler" başlığı hiç basılmaz — boş başlık gürültüdür. */
export function Sidebar({
  oturumlar,
  etkin,
  onSec,
  onYeni,
}: {
  oturumlar: OturumSatiri[];
  etkin: string | null;
  onSec: (id: string) => void;
  onYeni: () => void;
}) {
  return (
    <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 4 }}>
      <button
        onClick={onYeni}
        style={{ textAlign: "left", padding: "8px 10px", borderRadius: 8, border: "none", background: "transparent", cursor: "pointer", fontSize: 14 }}
      >
        Yeni sohbet
      </button>
      {oturumlar.length > 0 && (
        <>
          <div style={{ color: "var(--sonuk-metin)", fontSize: 12, padding: "12px 10px 4px" }}>
            Sohbetler
          </div>
          {oturumlar.map((o) => (
            <button
              key={o.session_id}
              data-etkin={o.session_id === etkin}
              onClick={() => onSec(o.session_id)}
              style={{
                textAlign: "left",
                padding: "8px 10px",
                borderRadius: 8,
                border: "none",
                cursor: "pointer",
                fontSize: 14,
                background: o.session_id === etkin ? "var(--secili-satir)" : "transparent",
              }}
            >
              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {o.title}
              </div>
              <div style={{ color: "var(--sonuk-metin)", fontSize: 11 }}>{o.source}</div>
            </button>
          ))}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Testin geçtiğini gör**

```bash
cd app && npx vitest run src/screens/Sidebar.test.tsx --environment jsdom
```
Beklenen: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app && git commit -m "feat(app): kenar çubuğunu ve oturum listesini çiz"
```

---

### Task 6: Ekranları bağla — çalışan uygulama

**Files:**
- Modify: `app/src/App.tsx`
- Test: `app/src/App.test.tsx`

Bu görev parçaları birleştirir: çekirdek başlar, oturum durumu okunur, görev
gönderilir, olaylar akar, soru gelince diyalog açılır.

- [ ] **Step 1: Kırmızı testi yaz**

`app/src/App.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Uygulama } from "./App";
import { ProtocolClient } from "./protocol/client";

/** Sahte taşıma: gerçek Tauri ve gerçek süreç olmadan tüm akış sınanır. */
function sahte() {
  let dinleyici: ((s: string) => void) | null = null;
  const yazilan: string[] = [];
  const istemci = new ProtocolClient(
    (s) => yazilan.push(s),
    (f) => {
      dinleyici = f;
    },
  );
  return { istemci, yazilan, al: (s: string) => dinleyici?.(s) };
}

describe("Uygulama", () => {
  it("soru gelince onay diyaloğunu açar", async () => {
    const s = sahte();
    render(<Uygulama istemci={s.istemci} />);

    s.al(
      JSON.stringify({
        tip: "soru",
        id: "1",
        veri: { tur: "onay", arac: "write_file", argumanlar: {}, secenekler: [{ deger: "deny", etiket: "Reddet" }] },
      }),
    );

    await waitFor(() => expect(screen.getByText(/izin verilsin mi/i)).toBeTruthy());
  });

  it("olayları konuşma akışında gösterir", async () => {
    const s = sahte();
    render(<Uygulama istemci={s.istemci} />);

    s.al(JSON.stringify({ tip: "olay", veri: { olay: "ToolExecuted", name: "write_file" } }));

    await waitFor(() => expect(screen.getByText(/write_file/)).toBeTruthy());
  });
});
```

- [ ] **Step 2: Testin başarısız olduğunu gör**

```bash
cd app && npx vitest run src/App.test.tsx --environment jsdom
```
Beklenen: FAIL — `Uygulama` dışa aktarılmamış.

- [ ] **Step 3: Uygulamayı bağla**

`app/src/App.tsx` — `Uygulama` bileşenini dışa aktar; istemciyi PROP olarak al
(testte sahte, üretimde gerçek). Sorumlulukları:

- `oturum.durum` ile açılışta durumu oku.
- Girdi gönderilince `tur.calistir` çağır.
- `onEvent` ile gelen olayları `olayMetni`'nden geçirip akışa ekle; `null`
  dönenleri hiç gösterme.
- `onQuestion` ile gelen soruyu diyaloğa ver; cevap seçilince `reply` çağır ve
  diyaloğu kapat.
- Kabuğu `Shell` ile kur: solda `Sidebar`, sağda `Conversation` ya da boşsa
  `EmptyState`.

Üretim girişi (`main.tsx`) gerçek istemciyi kurar: `cekirdek_baslat` çağırır ve
`cekirdek-satir` olayını dinler.

- [ ] **Step 4: Testin geçtiğini gör**

```bash
cd app && npx vitest run --environment jsdom
```
Beklenen: tüm testler geçer.

- [ ] **Step 5: Gerçek uygulamayla duman testi**

`npm run tauri dev` ile aç. Doğrula:
- Pencere açılır, kenar çubuğu ve boş başlangıç ekranı görünür.
- Bir görev gönderilince olaylar akışta belirir.
- Onay gerektiren bir işlemde diyalog açılır ve seçim tura geri döner.

- [ ] **Step 6: Commit**

```bash
git add app && git commit -m "feat(app): ekranları bağla ve akışı uçtan uca çalıştır"
```

---

### Task 7: Paketleme ve imzasız dağıtım

**Files:**
- Modify: `app/src-tauri/tauri.conf.json`
- Create: `app/KURULUM.md`

- [ ] **Step 1: Uygulama kimliğini ayarla**

`tauri.conf.json` içinde ürün adı `Fusion`, tanımlayıcı `com.fusion.app`,
pencere başlangıç boyutu 1440x900 (ölçülmüş referans genişliği).

- [ ] **Step 2: Derle**

```bash
cd app && npm run tauri build
```
Beklenen: `app/src-tauri/target/release/bundle/macos/Fusion.app` üretilir.
Boyutu raporla.

- [ ] **Step 3: İmzasız açılışı doğrula**

Üretilen `.app`'i çift tıklayarak aç. macOS'un engellemesi BEKLENEN davranıştır;
sağ tık → Aç ile açıldığını doğrula ve iki adımı da not et.

- [ ] **Step 4: Kurulum yönergesini yaz**

`app/KURULUM.md` — Türkçe, kısa: uygulamanın imzasız olduğu, ilk açılışta
macOS'un engelleyeceği, sağ tık → Aç ile geçileceği, ve Fusion CLI'ın kurulu
olması gerektiği.

- [ ] **Step 5: Commit**

```bash
git add app && git commit -m "feat(app): uygulamayı paketle ve kurulum yönergesini yaz"
```

---

## Öz Denetim

**Spec kapsamı.** Spec'in her bölümü bir göreve bağlı:

| Spec bölümü | Görev |
|---|---|
| Yığın ve çekirdek köprüsü | 1 |
| Görsel dil, kabuk düzeni | 2 |
| Konuşma görünümü, olay akışı, asimetri kuralı | 3 |
| Onay diyaloğu, yıkıcı işlemde oturum izni | 4 |
| Kenar çubuğu, oturum listesi | 5 |
| Durum sahipliği (protokolden okuma), hata yolları | 6 |
| Dağıtım, imzasız açılış | 7 |

**Bilinen boşluk.** Spec'teki "Seçici" ve "Ayarlar" ekranları bu plana DAHİL
DEĞİLDİR. Gerekçe: ikisi de `komut.secenekler` ve `komut.listele` üzerine kurulu
ve çok adımlı seçim yükünün gerçek davranışını görmeden tasarlanırsa iki kez
yazılır. Çalışan uygulama elde edildikten sonra ayrı bir planla eklenecekler.
Bu, kapsamın sessizce daraltılması değil, bilinçli sıralamadır.

**Tip tutarlılığı.** `ProtocolClient` (Task 1) 3., 4., 5. ve 6. görevlerde aynı
imzayla kullanılıyor. `Soru` tipi 1. ve 4. görevlerde aynı alanları taşıyor.
`olayMetni` (Task 3) yalnız 6. görevde çağrılıyor.

**Yer tutucu taraması.** Kod gerektiren her adımda kod var. Task 6 Step 3
sorumlulukları madde madde sayıyor ve bağlanacak parçaların tamamı önceki
görevlerde tam kodla tanımlı.
