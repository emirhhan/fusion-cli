# Sınırlı takip düzeltmeleri: bağımsız genel inceleme

Kaynak kapsamı: `caea6ae1` + `0e384844` talimat ölçümleri;
`99c7ce2e` + `39ca542e` + `30884bbc` kaynak/öğretmen sözleşmesi;
`17f483ce` iletişim formu sondası; `ab67554d` sistem istemi;
ayrıca `b27992c3` öğretmen görüşünün kaynağını koruyan düzeltme.
Temel snapshot `ab67554d`; sonradan eklenen otomatik öğretmen süre bütçesi ve
diğer kapsamlar bu onaya dahil değildir. Üretim dosyası değiştirilmedi.

## MEDIUM: açık başarısızlık mesajı yanlış teslim alındı iddiası sayılıyor

Dosya: `src/fusion_cli/engines/agent/contact_form_probe.py:22`, son karar `:272`.

`_RECEIPT`, `message` ile `sent`/`delivered` arasındaki olumsuzluğu dikkate
almıyor. `_DISCLOSURE` ise `could not be sent` ve `was not delivered` ifadelerini
kapsamıyor. Gerçek, izole Chromium sondasında `preventDefault()` yapan ve yalnız
şu görünür durumlardan birini yazan iki form da `false_receipt` döndürdü:

- `Your message could not be sent. Please try again.`
- `Your message was not delivered. Please try again.`

Her iki durumda taşıma denemesi sıfırdı. `BrowserVerifier` bu gözlemi engelleyici
bulguya çeviriyor; oysa form açıkça gönderimin başarısız olduğunu söylüyor.
Dar çözüm: olumlu teslim iddiasını kendi cümlesindeki olumsuzluktan ayırmak ve
bu gerçek tarayıcı kontrollerini eklemek. Ayrı bir olumsuz cümle, gerçek olumlu
teslim iddiasını aklamamalı.

Bağımsız test dosyası görev çalışma alanında
`work/reliability-v2/test_general_contact_negative_receipts.py`.
`general-contact-negative-red.log`: **2 başarısız**, süreç `18222`, çıkış 1.
İlk doğrudan Chromium yeniden üretimi `28674` çıkış 0 ile aynı iki yanlış
sınıflandırmayı kaydetti. İncelenen sonda SHA-256:
`c85ad6d33b197f2411e66e41988fa6efdf6428e3d8423a147335c6abc9a1973e`.

## Diğer kapsamların kararı: APPROVE

- Talimat ölçümü en fazla mevcut 4 MiB + 1 karakter örneği ve işbirlikli 50 ms
  ek-okuma sınırı kullanıyor. Önceden yüklenen önek değişmiyor. Kesin olmayan
  kırpma sayısı alt sınır olarak işaretleniyor; RPC kesin sayıyı `null` döndürüyor.
  Bu süre sınırı bloklayan bir dosya okumasını zorla kesen duvar saati garantisi
  değildir. Kancalar yalnız gerçekten yüklenen dosyalardan oluşturuluyor.
- Kaynaklı dosya üretimi mutasyon önceliğini korurken açıkça istenen URL okumasını
  ayrı şart olarak taşıyor. Araştırma fiilleri aynı kaynak ayrıştırıcısını
  kullanıyor; `Read README.md, include a link ...` uzak okuma sayılmıyor.
  API/CDN/runtime/auth/çok dosya/açık öğretmen kapsamı temkinli rotada kalıyor.
- İstem, aynı kapsamda düzeltme sonrası geçen kontrolün raporlanmasına izin
  veriyor; önceki hata ve sınanmayan kapsamın gizlenmesini istemiyor. Gerçek
  kullanıcı verisini koruyan izole program testi kuralı kalıyor. İstem 6096 karakter.
- `b27992c3` ham öğretmen değerlendirmesini doğrulanmış dış platform gerçeğine
  çevirmiyor. Nitelendirilmiş olay/iç not korunuyor; gerçek başarısız sonuç ve
  resmi platform bilgisi doğrulanmadığında çıkan uyarı aynen kalıyor.

## Bağımsız doğrulama

Asıl sanal ortam Python'u ve `PYTHONPATH=src` kullanıldı. Günlükler görev çalışma
alanında `work/reliability-v2/` altında tutuldu:

| Günlük | Sonuç | Sonlanmış süreç |
|---|---|---|
| `general-followup-boundary-final.log` | 257 geçti; kaynak/talimat/istem ve önceki dört bağımsız sınır testi | `54373`, çıkış 0 |
| `general-contact-final.log` | 62 geçti; iletişim sondası, BrowserVerifier ve yerleşim kontrolleri | `21881`, çıkış 0 |
| `general-teacher-provenance-final.log` | 171 geçti; görüş kaynağı, platform, renderer ve JSON sözleşmesi | `71104`, çıkış 0 |
| `general-contact-negative-red.log` | Yukarıdaki iki gerçek tarayıcı kontrolü başarısız | `18222`, çıkış 1 |

İlk kapsamın on değişen kaynak modülünde Ruff, büyük ajan döngüsü dışındaki
dokuz modülde mypy geçti (`24912`, çıkış 0). Öğretmen görüşü düzeltmesinin dört
kaynak modülünde Ruff ve mypy geçti (`5024`, çıkış 0). İncelemeye ait çalışan
test süreci kalmadı. Bu sonuçlar yeni tam model koşusu, kurulum, bütün ürün
kabulü veya tüm doğal dil ifadeleri için doğruluk iddiası değildir.

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 0 | pass |

Verdict: **WARNING** — iletişim sondasının iki yanlış engellemesi düzeltilmeli;
diğer belirtilen kapsamlar onaylandı.
