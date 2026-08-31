# Task 3 — Güvenilir konuşma tanıma yaşam döngüsü

## Uygulanan sözleşme

- Rust `SpeechManager`, her yeni yardımcı süreç için artan bir oturum token'ı üretir; çalışan yardımcı yeniden kullanılırsa token korunur.
- `tanima_baslat` token'ı döndürür. `ses://tanima` çıktı ve `ses://tanima-sonlandi` bitiş olayları token'ı taşır.
- React aktif token dışındaki çıktı/bitiş olaylarını yok sayar. Stop idempotenttir ve çağrılar tek kuyrukta sıralanır.
- Kısmi metin yalnız görüntülenir; aynı oturumun aynı finali yalnız bir `finalRevision` üretir ve `emitVoiceMessage` yalnız bir kez çağrılır.
- Mini/normal görünüm değişimi recognition çağrısı yapmaz. Belirsiz sözlü onay fail-closed kalır.
- Mikrofon başlangıcı, dar ve enjekte edilebilir `preflightRecognition` seam'ından sonra gerçekleşir; izin reddi ve başlatma/durdurma hataları eyleme dönük Türkçe metinlere çevrilir.

## TDD ve regresyon kanıtı

Başlangıçta eklenen lifecycle testleri kırmızıydı: React hedefinde 7 başarısız test ve Rust hedefinde eksik `SpeechStart::session()` nedeniyle derleme hatası görüldü.

Geçici revert kanıtı: `voiceMachine` içindeki stale-session koruması kaldırıldığında `npm test -- --run src/voice/voiceMachine.test.ts` 6 testten 1'ini başarısız kıldı (`eski oturumun kısmi ve final metnini reddeder`). Koruma geri yüklendikten sonra hedef React testleri yeniden geçti.

## Doğrulama

- `npm test -- --run src/voice/voiceMachine.test.ts src/voice/VoiceWindow.test.tsx` — 19/19 geçti.
- `npm run build` — TypeScript ve Vite üretim derlemesi geçti.
- `cargo fmt --check && cargo clippy --all-targets -- -D warnings && cargo test` — biçim, clippy ve Rust testleri geçti; 51 geçti, 1 bilinçli olarak ignore edildi.

## Kapsam notu

PermissionCenter davranışı bu göreve kopyalanmadı. Varsayılan preflight seam'ı `true` döner; izin sistemi hazır olduğunda aynı runtime sınırından enjekte edilmelidir.

## Fix round 1 — inceleme düzeltmeleri

- Start tokenı dönmeden senkron gelen çıktı/bitiş olayları, start handshake'i boyunca tamponlanır ve kurulan token eşleşirse sırayla oynatılır.
- Her dinleme isteği monotonik bir niyet nesli taşır. Stop, bekleyen preflight'ı geçersizleştirir; eski izin sonucu yardımcı süreci başlatamaz.
- Final, hem reducer hem pencere katmanında oturum başına bir kez tüketilir. Farklı ikinci final de sohbet mesajı üretemez.
- Sözlü onay eşleştiğinde `askRef` React render'ını beklemeden boşaltılır; aynı turdaki ikinci final tekrar onaylayamaz. Kısmi/final reducer olayları gerçek oturum tokenını iletir.

### Kırmızı-yeşil kanıtı

Yeni deterministik testler eklendiğinde React hedefi 24 testten 5'ini başarısız kıldı: hızlı start olayı, bekleyen preflight sonrası stop, farklı ikinci final, çift onay ve reducer'ın oturum-başına final koruması. Düzeltmeden sonra aynı hedef 24/24 geçti.

### Fix round 1 doğrulaması

- `npm test -- --run src/voice/voiceMachine.test.ts src/voice/VoiceWindow.test.tsx` — 24/24 geçti.
- `npm run build` — TypeScript ve Vite üretim derlemesi geçti.
- `cargo test speech::tests --lib` — 9 geçti, 1 bilinçli olarak ignore edildi.
- `cargo fmt --check && cargo clippy --all-targets -- -D warnings` — geçti.
