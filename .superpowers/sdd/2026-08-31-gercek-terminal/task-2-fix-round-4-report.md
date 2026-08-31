# Terminal Task 2 — fix round 4 raporu

## Kapsam ve sonuç

- `SafeReplayRetention`, retained güvenli prefix ile pending parser buffer'ının toplamını 256 KiB byte bütçesi içinde tutuyor.
- Bütçeyi aşan ilk output'ta pending unit bırakılıyor ve retention donduruluyor; sonraki output retention'a alınmıyor.
- Retention'ın donması live subscriber dağıtımını etkilemiyor; raw output chunk'ları eksiksiz teslim edilmeye devam ediyor.
- Replay yalnız tamamlanmış UTF-8 codepoint ve ANSI unit'lerinden oluşuyor; yarım unit replay başlangıcı olamıyor.
- `clearRetention()` retained prefix, pending unit, frozen flag ve parser epoch durumunu birlikte sıfırlıyor. Sonraki güvenli output bağımsız yeni epoch'u başlatıyor.

## TDD kanıtı

Üretim kodu değişmeden önce dört deterministik regresyon testi eklendi. `npm test -- terminalBridge` şu beklenen RED sonucu verdi:

- unterminated OSC sonrası clear: eski dev pending parser yeni epoch'u bloke etti,
- unterminated DCS sonrası clear: yeni output replay edilmedi,
- incomplete UTF-8 sonrası clear: yeni ASCII output replay edilmedi,
- clear-during-pending CSI: yeni epoch'un ilk byte'ı eski unit tarafından tüketildi.

Sonuç: 4 failed, 10 passed. Minimal retention/reset değişikliğinden sonra aynı komut 14/14 GREEN verdi.

## Taze doğrulama

- `cd app && npm test -- terminalBridge XtermSession TerminalTabs` — 3 dosya, 29/29 test, exit 0.
- `cd app && npm test` — 65 dosya, 405/405 test, exit 0.
- `cd app && npm run build` — TypeScript ve Vite production build, exit 0.
- `git diff --check` — exit 0.

Vite yalnız mevcut 500 kB chunk-size uyarısını verdi; build başarısızlığı veya yeni test uyarısı oluşmadı.
