# Task 1 — Rust PTY yöneticisi raporu

## Son durum

Task 1 tamamlandı. `portable-pty` tabanlı `TerminalManager`; etkileşimli kabuk açma, ham byte girdi/çıktısı, ANSI koruma, `100x40` dahil yeniden boyutlandırma, Ctrl+C ile foreground süreç kesme, tekli kapatma ve `close_all` temizliği sağlıyor. Mevcut Python `ProcessManager` ve Rust `SessionManager` değiştirilmedi.

Unix'te doğrudan `$SHELL` (geçersiz/yoksa `/bin/sh`), Windows'ta doğrudan `powershell.exe` ve ardından `cmd.exe` fallback kullanılıyor. Etkileşimli terminal hiçbir yerde `shell -lc` komut çalıştırıcısı olarak başlatılmıyor.

Tauri komutları `terminal_ac`, `terminal_yaz`, `terminal_boyutla`, `terminal_kapat`; olaylar `terminal://cikti` ve `terminal://kapandi` olarak bağlandı. Çıktı, 8 KiB parçalar ve 128 öğelik bounded kanal üzerinden byte dizisi olarak aktarılıyor.

## Commit

`feat(app): gercek pty terminal altyapisini ekle`

## Test ve doğrulama

- TDD RED: `cargo test terminal -- --nocapture` eksik `TerminalManager`, `TerminalOutput`, `TerminalClosed` nedeniyle exit 101 ile başarısız oldu.
- TDD GREEN: 5 terminal testi geçti: geçici cwd, ANSI byte koruma, resize, Ctrl+C sonrası yaşayan shell ve tüm çocukların kapatılması.
- `cargo fmt --check`: exit 0.
- `cargo clippy --all-targets -- -D warnings`: exit 0.
- `cargo test terminal -- --nocapture`: exit 0; 5 geçti, 0 başarısız.
- `git diff --check`: exit 0.

## Kalan kaygı

Gerçek Windows ConPTY çalışması bu macOS hostta yürütülemedi. Kurulu `x86_64-pc-windows-msvc` hedefiyle çapraz `cargo check` denendi; proje kaynaklarına ulaşmadan Tauri `tauri-winres` build script'i hostta `llvm-rc` bulunmadığı için durdu. Windows `cfg` yolu PowerShell→cmd fallback içeriyor ancak gerçek Windows hostta smoke test hâlâ önerilir.
