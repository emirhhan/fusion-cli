# E10 — Python scoped inceleme

Kapsam: `providers/web_registry.py`, `providers/web_session.py` ve
`tests/test_web_credentials_on_demand.py` mevcut dokuz vakası.
Diff: `/tmp/fusion-e10-review.diff`, SHA256
`008c0c167feb4b40f9cd0bb89d49c008721f93db11f4b944e0485fe5f905eda9`.
Üretim kodu değiştirilmedi; gerçek Keychain/sır, hesap, ağ veya model çağrısı
yapılmadı. İnceleme auth/thread/timeout kapsamına genişletilmedi.

## Değerlendirme

- Registry kurulması `secret_key` veya credential dosyasını artık okumuyor.
  Browser credential_ref bulunan adaptörün yalnız kurulması da sır erişimini
  başlatmıyor. API birincili başarılıysa hazırda duran web yedeği bu I/O'yu yapmıyor.
- Credential factory yalnız gerçek browser transport çağrısı sırasında çözülüyor.
  HTTP token'ı mevcut environ snapshot yolunda, credential'sız browser ise boş
  credential yolunda kalıyor. Credential seçimi/yetkisi genişletilmiyor.
- Lazy store cache registry örneğinin sahibi; global cache eklenmemiş.
  Açıkça enjekte edilmiş store factory'den önce geliyor. Factory exception'ında
  assignment gerçekleşmediğinden sonraki deneme tekrar deneyebiliyor.
- Her kullanımda store.get tekrar çağrılıyor; adapter kurulurken yakalanmış eski
  cookie zorla tutulmuyor. Yeni registry yeni master-key factory çözümü alıyor.
  Dokuz regresyon hem kullanılmayan/gerçekleşen fallback'i hem injection,
  exception retry, cookie güncellemesi ve registry yenilenmesini hedefliyor.

**Kapsam sınırı:** Gerçek credential_ref browser çağrısında factory/get hâlâ
senkron çalışır. `_call_transport` wait_for argümanı oluşturulurken factory
çağrıldığı için bu bekleme async timeout tarafından kesilemez. Bu inceleme bu
bilinen boşluğu kapatılmış saymaz. Onay, gözlenen API turundaki gereksiz credential
I/O kök nedeninin kaldırılması içindir; tam E10/Keychain hazır olma onayı değildir.

## Kanıt ve verdict

Review'da E10 ve bağımsız E13'ün toplam beş ilgili dosyasında:
- `ruff check`: **All checks passed!**
- `ruff format --check`: **5 files already formatted**
- Scoped mypy iki E10 ve bir E13 kaynak dosyasında:
  **Success: no issues found in 3 source files**.

Controller'ın fresh `/tmp/fusion-e10-final-tests.log` çıktısı okundu:
**96 passed in 9.35s**. Review testleri yeniden çalıştırmadı. Sağlanan önceki
168 test kanıtı bu son logun parçasıymış gibi sayılmadı.

**E10 darfix kabul verdict: APPROVE.**
**E10 darfix Python kalite/güvenlik verdict: APPROVE.**
İncelenen değişiklikte actionable P1/P2 bulunmadı; yukarıdaki senkron gerçek
browser credential beklemesi açık sınır olarak korunmalı.
