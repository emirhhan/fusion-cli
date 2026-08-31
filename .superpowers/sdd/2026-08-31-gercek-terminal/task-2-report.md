# Task 2 Raporu — xterm köprüsü ve terminal görünümü

## Sonuç

- `TerminalRuntime`, Task 1 Tauri komutlarına ve `terminal://cikti` / `terminal://kapandi` olaylarına bağlandı.
- Terminal girdisi UTF-8 baytları olarak PTY'ye iletiliyor; Ctrl+C dahil xterm `onData` verisi React tarafından kesilmiyor.
- Çıktı tek bir streaming `TextDecoder` ile çözümleniyor. Parçalı UTF-8 karakterleri korunuyor, ANSI dizileri değiştirilmeden xterm'e aktarılıyor.
- xterm ve FitAddon küçük, enjekte edilebilir bir adapter arkasında tutuldu. ResizeObserver sonrası fit boyutları PTY'ye gönderiliyor.
- Terminal sekmesi artık ProcessManager komut composer'ını taklit etmiyor. “Yeni terminal”, kullanıcı shell'ini etkin proje kökünde açıyor.
- Çoklu terminal sekmeleri, odak, kopyala, yapıştır, temizle, kapat, çalışma/kapanma durumu ve ArrowLeft/ArrowRight/Home/End klavye navigasyonu eklendi.
- ProcessManager tabanlı komutlar ve geçmiş süreç çıktıları yalnız Processes ve Tests akışlarında kaldı.

## TDD kanıtı

1. `npm test -- terminalBridge XtermSession` önce iki eksik modül nedeniyle exit 1 verdi.
2. Köprü ve adapter uygulandıktan sonra aynı suite 7/7 geçti.
3. Yeni TerminalTabs testleri eski `ProcessController` arayüzünde 4/4 RED verdi.
4. PTY sekme modeli uygulandıktan sonra TerminalTabs 4/4 GREEN verdi.
5. Tam suite'teki eski composer entegrasyon beklentisi yeni PTY akışına güncellendi.

## Değişen alanlar

- `app/src/processes/terminalBridge.ts` ve testleri
- `app/src/processes/XtermSession.tsx` ve testleri
- `app/src/processes/TerminalTabs.tsx` ve testleri
- `app/src/processes/TerminalPanel.tsx`
- `app/src/processes/processes.css`
- `app/src/App.tsx` ve ilgili entegrasyon testleri
- `app/package.json`, `app/package-lock.json`

## Doğrulama

- `npm test -- terminalBridge XtermSession TerminalTabs`
- `npm test`
- `npm run build`

Üç komut da commit öncesi taze olarak exit 0 ile tamamlandı.

## Review fix round 1

- `openSession`, output/closed Tauri listener'larını `terminal_ac` çağrısından önce kuruyor. Handshake sırasında gelen olaylar terminal kimliği dönene kadar buffer'lanıp doğru session'a aktarılıyor.
- Xterm adapter artık effect mount başına üretiliyor. React StrictMode çift effect döngüsünde dispose edilmiş adapter yeniden kullanılmıyor.
- Doğal backend kapanışı sekme owner'ına taşındı; sekme noktası ve “Kapandı” durumu güncelleniyor. Bilinen kapalı terminal yerel state'ten backend close gerektirmeden kaldırılıyor ve session close idempotent davranıyor.
- TerminalTabs açtığı PTY'lerin sahibi. Panel unmount'ında çalışan terminaller tam bir kez kapatılıyor, event kanalları dispose ediliyor; open handshake sonrasında geç dönen PTY de sahipsiz bırakılmıyor.

### Round 1 TDD kanıtı

1. Senkron output/close handshake testleri `openSession is not a function` ile RED verdi; listener-before-open buffer sonrası 4/4 bridge testi GREEN oldu.
2. StrictMode testi dispose edilmiş adapter'ın yeniden kullanılmasını yakalayıp RED verdi; effect-mount başına fresh adapter sonrası 6/6 XtermSession testi GREEN oldu.
3. Natural close/idempotent local remove ve multi-PTY owner unmount testleri eski owner modeliyle RED verdi; session sahipliği sonrası TerminalTabs testleri GREEN oldu.
4. Deferred open sırasında unmount testi sahipsiz geç PTY'yi yakalayıp RED verdi; mounted-owner guard sonrası App + TerminalTabs 39/39 GREEN oldu.

## Review fix round 2

- Session output buffer'ı, ilk subscriber'ın tükettiği kuyruk yerine 256 KiB ile sınırlı retained transcript oldu. Her yeni subscriber kendi replay'ini alıyor; StrictMode'un ikinci fresh adapter'ı handshake sırasında gelen ilk prompt'u yeniden görüyor.
- Clear yalnız mevcut xterm ekranını temizliyor. Subscription yenilenmediği için retained transcript Clear sonrasında kendiliğinden tekrar yazılmıyor.
- `TerminalSession.close`, eşzamanlı çağrılar için tek shared closing promise/state kullanıyor. User close ile owner unmount yarışı tek `terminal_kapat` çağrısı üretiyor; bilinen doğal kapanma ve kapanma sırasında gelen not-found sonucu idempotent başarı.
- Output ve closed listener kurulumları sıralı ve rollback güvenli. İkinci listener veya `terminal_ac` başarısızsa daha önce kurulmuş bütün listener'lar kaldırılıyor.

### Round 2 TDD kanıtı

1. Handshake prompt + StrictMode testi RED'de ikinci adapter için 0 write gördü; per-subscriber retained replay sonrası iki fresh adapter da prompt'u aldı.
2. Eşzamanlı close testi RED'de 2 `terminal_kapat` gördü; shared close promise sonrası tam 1 çağrı gördü.
3. Partial listener testi RED'de ilk unlisten için 0 çağrı gördü; sıralı install/rollback sonrası tam 1 çağrı gördü ve `terminal_ac` hiç çağrılmadı.
4. Bounded transcript ve Clear davranışı ayrı regresyon testleriyle kilitlendi.

## Review fix round 3

- Retention artık byte tail kırpmıyor. Replay, epoch başlangıcından itibaren yalnız tamamlanmış ASCII span, UTF-8 codepoint ve ANSI kontrol dizisi unit'leri içeriyor.
- 256 KiB sınırına sığmayan ilk güvenli unit'te retention donuyor; eski baş drop/slice edilmiyor. Live subscriber'lar donmadan bağımsız olarak bütün raw output chunk'larını almaya devam ediyor.
- Split UTF-8 ve split CSI overflow sınırlarında yeni subscriber prompt ile başlayan güvenli prefix'i alıyor; continuation byte veya yarım escape dizisi replay başlangıcı olamıyor.
- Clear, xterm ekranıyla birlikte retained epoch'u sıfırlıyor. Önceki epoch'tan yarım kalmış unit varsa tamamlanınca retention'a alınmadan atlanıyor; sonraki güvenli output yeni epoch'u başlatıyor.

### Round 3 TDD kanıtı

1. Split UTF-8 overflow testi RED'de replay'in `[E2 82]` ile başladığını gösterdi; güvenli-unit retention sonrası prompt ile başladı ve taşan `€` yalnız live akışta kaldı.
2. Split ANSI overflow testi RED'de replay'in `ESC [` ile başladığını gösterdi; güvenli-unit retention sonrası prompt korundu ve taşan CSI yalnız live akışta kaldı.
3. Clear epoch testleri RED'de `clearRetention` eksikliği ve UI'dan 0 çağrı gördü; session API/UI bağlantısı sonrası eski epoch replay edilmedi.
