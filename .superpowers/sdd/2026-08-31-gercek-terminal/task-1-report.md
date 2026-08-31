# Task 1 — Rust PTY yöneticisi raporu

## Son durum

Task 1 tamamlandı. `portable-pty` tabanlı `TerminalManager`; etkileşimli kabuk açma, ham byte girdi/çıktısı, ANSI koruma, `100x40` dahil yeniden boyutlandırma, Ctrl+C ile foreground süreç kesme, tekli kapatma ve `close_all` temizliği sağlıyor. Mevcut Python `ProcessManager` ve Rust `SessionManager` değiştirilmedi.

Unix'te doğrudan `$SHELL` (geçersiz/yoksa `/bin/sh`), Windows'ta doğrudan `powershell.exe` ve ardından `cmd.exe` fallback kullanılıyor. Etkileşimli terminal hiçbir yerde `shell -lc` komut çalıştırıcısı olarak başlatılmıyor.

Tauri komutları `terminal_ac`, `terminal_yaz`, `terminal_boyutla`, `terminal_kapat`; olaylar `terminal://cikti` ve `terminal://kapandi` olarak bağlandı. Çıktı, 8 KiB parçalar ve terminal başına 128 öğelik tek ordered/bounded event kanalı üzerinden byte dizisi olarak aktarılıyor. `terminal://kapandi`, o terminalin bütün queued output olayları teslim edildikten sonra tam bir kez yayınlanıyor.

Review round 1 ile global terminal map mutex'i yalnız `Arc` handle bulma/çıkarma için kullanılacak şekilde daraltıldı. Blocking `write_all`, `flush`, resize, kill ve wait işlemleri terminal-scope mutex'lerinde ve global map kilidi dışında çalışıyor. Doğal reader kapanışı da map kaydını kaldırdıktan ve kilidi bıraktıktan sonra child wait yapıyor.

## Commit

`feat(app): gercek pty terminal altyapisini ekle`

Round 1: `fix(app): pty eszamanlilik ve olay sirasini duzelt`

Round 2: `fix(app): terminal close claim ve ansi pty testini duzelt`

## Test ve doğrulama

- TDD RED: `cargo test terminal -- --nocapture` eksik `TerminalManager`, `TerminalOutput`, `TerminalClosed` nedeniyle exit 101 ile başarısız oldu.
- TDD GREEN: 5 terminal testi geçti: geçici cwd, ANSI byte koruma, resize, Ctrl+C sonrası yaşayan shell ve tüm çocukların kapatılması.
- `cargo fmt --check`: exit 0.
- `cargo clippy --all-targets -- -D warnings`: exit 0.
- `cargo test terminal -- --nocapture`: exit 0; 5 geçti, 0 başarısız.
- `git diff --check`: exit 0.

### Review round 1

- TDD RED concurrency/order: event testi deterministik olarak `["closed:süreç kapandı", "output"]` gözledi; beklenen `["output", "closed:kullanıcı kapattı"]`. Global mutex altında doğal `wait` nedeniyle test paketi askıda kaldı ve süreç exit 130 ile sonlandırıldı.
- TDD GREEN: 7 terminal testi geçti; yeni testler bir terminalde kontrollü biçimde bloke edilen write'ın ikinci terminal resize'ını engellemediğini ve explicit close'un final output'tan sonra, `kullanıcı kapattı` nedeniyle, tam bir kez teslim edildiğini doğruluyor.
- Windows ANSI testi PowerShell 6 `` `e `` sözdizimi ve seçili shell varsayımından çıkarıldı; ham ANSI byte dizisi platform bağımsız event helper üzerinden doğrulanıyor.
- `cargo fmt --check`: exit 0.
- `cargo clippy --all-targets -- -D warnings`: exit 0.
- `cargo test terminal -- --nocapture`: exit 0; 7 geçti, 0 başarısız.
- `cargo test --all-targets`: exit 0; 63 geçti, 0 başarısız, 1 ignored.

### Review round 2

- Tek terminal explicit close, `kullanıcı kapattı` reason'ını global map kilidi altında claim ediyor ve terminali ancak bundan sonra map'ten çıkarıyor. Reader EOF map removal'ı gözlediğinde explicit reason artık görünür durumda.
- `close_all`, map kilidi altında önce bütün entry'lerin explicit reason'ını claim ediyor; ardından topluca drain ediyor ve kilidi bıraktıktan sonra kill/wait yapıyor.
- Deterministik race testi map removal sonrasında reader-side `queue_closed_once` çalıştırarak close event reason'ının `kullanıcı kapattı` kaldığını doğruluyor.
- ANSI testi event worker'a doğrudan veri yazmıyor. Platform bağımsız Rust helper executable gerçek PTY slave üzerinde ESC byte'ları üretiyor; test production reader → `forward_output` → bounded ordered worker hattının çıktısını doğruluyor.
- TDD RED 1: eksik atomic claim primitive'i nedeniyle `claim_explicit_terminal` unresolved import ile exit 101.
- TDD RED 2: claim GREEN olduktan sonra PTY helper bulunamadığı için ANSI testi başarısız; 7 test geçti, 1 test başarısız.
- Gerçek kullanıcı shell başlangıçlarının paralel PTY testlerinde komut tüketmesini önlemek için PTY entegrasyon testleri test-only guard ile seri çalışıyor; iki-terminal concurrency testi kendi içinde eşzamanlı kalıyor.
- `cargo fmt --check`: exit 0.
- `cargo clippy --all-targets -- -D warnings`: exit 0.
- `cargo test terminal -- --nocapture`: exit 0; 8 geçti, 0 başarısız.
- `cargo test --all-targets`: exit 0; 64 geçti, 0 başarısız, 1 ignored.

## Kalan kaygı

Gerçek Windows ConPTY çalışması bu macOS hostta yürütülemedi. Kurulu `x86_64-pc-windows-msvc` hedefiyle çapraz `cargo check` denendi; proje kaynaklarına ulaşmadan Tauri `tauri-winres` build script'i hostta `llvm-rc` bulunmadığı için durdu. Windows `cfg` yolu PowerShell→cmd fallback içeriyor ancak gerçek Windows hostta smoke test hâlâ önerilir.
