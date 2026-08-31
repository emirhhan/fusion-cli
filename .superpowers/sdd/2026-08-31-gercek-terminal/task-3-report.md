# Task 3 — Gerçek terminal kabul kapısı raporu

## Round 1 düzeltmesi — 2026-08-31

`TerminalClosed` artık doğal PTY kapanışında `exit_code: Option<u32>` taşır.
`exit 0` yeşil **Bitti**, sıfır-dışı çıkış kırmızı **Hata (kod)**, açık kullanıcı
kapatması `null` kodla nötr **Durduruldu** gösterilir. Tek-seferlik, sıralı close
teslimi korunmuştur. Kanonik görsel kabul dosyası `app/e2e/terminal.visual.ts`'dir;
kapalı-hata sözleşmesi hata metnini ve kırmızı noktayı doğrular.

Round 1 kanıtı: terminal Rust 11/11, hedef React/köprü 32/32, tam `npm run check`
408 Vitest ve 67 Rust test, `terminal.visual.ts` 4/4 geçti. Ayrıntılı izlenebilir
rapor: `docs/superpowers/reports/2026-08-31-gercek-terminal-kabul.md`.

Tarih: 2026-08-31

## Uygulanan kabul sözleşmesi

- `app/e2e/terminal.visual.ts`, Playwright'ın kanonik `*.visual.ts` eşleşmesine
  uyar. Dört kararlı durum kapsar: boş, etkin, ANSI renkli çıktı ve kapanmış/hatalı.
- E2E preview, Tauri çağrısı yapmayan deterministik bir `TerminalRuntime` kullanır;
  gerçek xterm canvas'ına ANSI baytlarını verir. Böylece tarayıcı testi PTY'ye veya
  makinedeki kabuğa bağlı değildir.
- Eski workspace terminal hata görseli gerçek xterm kapalı durumuna taşındı.
- `docs/NASIL_KULLANILIR.md`, kullanıcı davranışını ve paketli macOS için manuel
  `python3`, Ctrl+C, `vim` çıkışı ve yeniden boyutlandırma kontrolünü açıklar.

## TDD kanıtı

İlk sözleşme, preview terminali bağlamadığı için kırmızıydı:

```text
cd app && npm run test:visual -- terminal.visual.ts
4 failed
locator('.terminal-tabs'): element(s) not found
```

Deterministik fixture eklendikten sonra referanslar oluşturuldu:

```text
cd app && npm run test:visual -- terminal.visual.ts --update-snapshots
4 passed
```

## Görsel referanslar

- `/Users/motogate/Desktop/01-Projeler/fusion-cli/app/e2e/terminal.visual.ts-snapshots/terminal-empty-darwin.png`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/app/e2e/terminal.visual.ts-snapshots/terminal-active-darwin.png`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/app/e2e/terminal.visual.ts-snapshots/terminal-ansi-color-darwin.png`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/app/e2e/terminal.visual.ts-snapshots/terminal-closed-error-darwin.png`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/app/e2e/workspace.visual.ts-snapshots/workspace-terminal-error-darwin.png`

## Doğrulama

```text
cd app && npm run check
Vitest: 65 files, 405 test geçti.
Cargo: 65 geçti, 0 başarısız, 1 atlandı.
Terminal Rust kontrolleri: ANSI baytlarının korunması, PTY açma, Ctrl+C sonrası
shell'in açık kalması ve yeniden boyutlandırma dahil geçti.

cd app && npm run test:visual
56 geçti, 14 aday-inceleme testi tasarım gereği atlandı.
Terminal 4/4 görsel sözleşmesi geçti.
```

## Paketli macOS duman testi

Çalıştırılan komut:

```text
cd app && npm run bundle:mac
```

Runtime oluşturma ve `runtime:smoke` başarıyla bitti ("Duman testi geçti"). Tauri
paketleme adımı ise mevcut Cargo yapılandırmasında uygulama ikilisi seçilemediği için
başlatılamadı:

```text
failed to find main binary, make sure you have a `package > default-run` in the Cargo.toml file
```

Bu nedenle paketli uygulamada kullanıcı girdisi gerektiren `python3`, Ctrl+C, `vim`
ve panel yeniden boyutlandırma UI duman adımları bu çalışmada otomatik veya elle
çalıştırılmış olarak iddia edilmez. Adımlar kullanım kılavuzunda paket üretilince
uygulanmak üzere yer alır.
