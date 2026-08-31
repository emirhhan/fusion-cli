# Gerçek terminal kabul raporu — Task 3, round 1

Tarih: 2026-08-31

## Sonuç

Doğal PTY kapanışları artık `terminal://kapandi` olayında `exitCode` taşır.
`exit 0` arayüzde yeşil **Bitti**, sıfır-dışı çıkış kırmızı **Hata (kod)**,
kullanıcının açık kapatması ise `exitCode: null` ile nötr **Durduruldu** olur.

Kapatma olayının tek-seferliği ve son çıktıdan sonra teslim edilmesi korunmuştur:
doğal kapanışta okuyucu sürecin `portable-pty::Child::wait()` sonucunu alır;
açık kapatmada süreç sonlandırılır ancak bu sonuç kullanıcıya bir doğal çıkış kodu
olarak bildirilmez.

## Kanonik görsel sözleşme

Kanonik kabul dosyası `app/e2e/terminal.visual.ts`'dir; eski plan adındaki
`terminal.spec.ts` değildir. Kapalı-hata senaryosu şu ikisini zorunlu kılar:

- durum metni: `Terminal hata ile kapandı (çıkış kodu: 1)`
- kırmızı `.terminal-tabs__dot--hata` göstergesi

Bu sözleşmenin mevcut `terminal-closed-error-darwin.png` referansı ile birlikte
çalışması doğrulandı. Aynı hata-metni kuralı `workspace.visual.ts` içindeki
workspace terminal hatası senaryosuna da taşındı.

## TDD kanıtı

Önce yeni Rust testleri `TerminalClosed.exit_code` alanını istediği için derleme
başarısız oldu (`E0609: no field exit_code`). Aynı anda köprü/UI testleri eski
tek-string kapanış değerini aldığı için başarısız oldu. Ardından en dar katmanlar
uygulandı: Rust olay alanı, TypeScript olay tipi ve sekme durum sınıflandırması.

## Doğrulama

```text
cd app/src-tauri && cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test terminal -- --nocapture
11 terminal testi geçti.

cd app && npm test -- terminalBridge TerminalTabs XtermSession && npm run build
32 hedef React/köprü testi geçti; TypeScript ve Vite build geçti.

cd app && npm run check
65 Vitest dosyası / 408 test geçti.
Rust: 67 geçti, 0 başarısız, 1 tasarım gereği atlandı.

cd app && npm run test:visual -- terminal.visual.ts
4/4 terminal görsel sözleşmesi geçti.
```

Vite, mevcut büyük bundle için 500 KiB üstü chunk uyarısı verdi; bu değişiklikten
bağımsız bir performans uyarısıdır ve doğrulamayı başarısız kılmadı.
