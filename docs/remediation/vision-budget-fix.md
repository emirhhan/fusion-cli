# E13 — Görsel açıklaması için sınırlı bütçe kurtarması

4 Kasım 2026. Kaynak kapsamı yalnız `engines/agent/image_view.py` ve
`tests/test_image_view_budget.py`. Kimlik bilgileri, model seçimi, provider
adaptörleri veya genel runtime ayarları değiştirilmedi.

## Kök neden ve değişiklik

Canlı Hesap Makinesi testinde yapılandırılmış Nano Omni reasoning görsel modeli,
200 tokenlık yardımcı bütçesini yalnız düşünmede tüketti. Bu sınır eski 11b
modelin tekrar üretmesini azaltmak için sabitti. Genel provider hata metnindeki
`runtime.max_tokens` önerisi bu yardımcı için geçerli değildi.

Başarılı kısa çağrı 200 token ile aynı kalır. Provider'ın yapılandırılmış
`ModelResult.truncated` sinyali gelirse aynı görsel ve soru bir kez 4096 tokenla
tekrar istenir. Model adına bakılarak reasoning yeteneği varsayılmaz; genel API
hatası, modelin kaldırılması veya boş yanıt yeniden denenmez. İki completion
isteği aynı 60 saniyelik süre sınırını paylaşır; ikinci istek kalan süreyi alır,
provider retry sayısı sıfırdır. Yedek provider zincirlerinin kendi davranışı bu
helper değişikliğinin dışındadır. Kesilmiş metin başarı/kanıt diye dönmez.

İkinci kesilme, görsel açıklama bütçesini belirten ve soruyu/görseli daraltmayı
veya başka görsel modeli seçmeyi öneren hata verir. Genel `runtime.max_tokens`
ayarını artırma önerisi bu durumda gösterilmez. İptal yayılır; timeout anlaşılır
hata döndürür. Dosya okuma ve provider kurma bu completion deadline'ından önce
olur; gerçek web credential çözümünün senkronluğu burada çözülmüş sayılmaz.

4096 token bir yeterlilik garantisi değildir. İstenen gerçek GUI açıklamasının
başarısı ve masaüstünde doğru pencereye yönelme ayrı canlı kabul gerektirir.
Bu dalgada model/ağ çağrısı veya gerçek anahtarlık erişimi yapılmadı.

## Doğrulama

- Önce yeni 8 test eski kaynakta: **5 failed, 3 passed**. Hatalar kurtarma
  eksikliği, kesik metnin kabul edilmesi, yanlış bütçe önerisi, kalan süre ve
  uygulanmayan toplam completion süresiydi.
- Düzeltme sonrası helper ve mevcut view_image testleri: **18 passed**.
- İlgili view_image, vision_capable_apprentice, image_flows ve image_tools
  dosyalarıyla geniş kapsam: **55 passed in 3.78s**.
- Ruff format/check temiz; scoped mypy **1 source file** temiz.
- Genel code-review: **APPROVE**. Kesik yanıtın kabul edilmemesi, ortak deadline,
  cancellation ve tek kurtarma davranışı incelendi.
- Bağımsız scoped Python review: **APPROVE**, actionable P1/P2 yok.
  Kalıcı kayıt: `e13-python-review.md`. Reviewer Ruff/format ve ortak mypy
  kontrolünü de temiz doğruladı. Completion deadline ve gerçek credential
  senkronluğu arasındaki sınır raporda korunur.
