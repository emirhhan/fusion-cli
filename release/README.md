# Yayın kapsamı ve kabul kanıtı

Bu kaynak ağacının mevcut dağıtım kapsamı geliştirici/önizleme paketleridir.
macOS ve Windows paketlerinin üretilebilmesi, temiz kullanıcı ortamında kabul
edildikleri anlamına gelmez. `known-gaps.json` içindeki macOS kurulum/yükseltme,
Windows izin/DPI/giriş, notarization, mağaza, gerçek telefon, OAuth ve uzun süreli
kabul eksikleri açıktır. Manifest `claimsReady=false` üretmeye devam eder.

`production.yaml` yerel smoke yeteneğini ölçer: gerçek MCP stdio initialize,
list_tools ve ping çağrısı; büyük dosyanın TARGET dışındaki tüm baytlarının
korunması; iki JSON dosyasının ayrı düzenlenmesi. Bu son görev gerçek uygulama
sohbet izolasyonu veya OAuth yaşam döngüsü kanıtı değildir. Bu iki ürün kabulü
ayrıca yapılmalıdır. Her görev 30 model çağrısı ve 180 saniye bütçelidir; önerilen
canlı karşılaştırma üç tekrardır. Bu tur gerçek model çağrısı yapılmamıştır.

Headless rapordaki `interactions.mode=headless_policy` sayaçları yalnız politika
karar taleplerini ve birebir aynı talebin tekrarlarını sayar. Tekrarın gereksiz
olduğu sonucunu çıkarmaz. Gerçek insan onay sayısı, yanıt süresi, müdahale,
yeni panelde pending sorunun geri gelmesi ve restart sonrası izin devamlılığı
ölçülmediyse `null` kalır; sıfır diye sunulmaz.

`scripts/release_manifest.py --live-acceptance rapor.json` verilirse raporun
standart `metadata`/`results` alanları yanında şu bağlayıcı alan aranır:

```json
{
  "binding": {
    "commit": "paketin kaynak commit kimliği",
    "artifacts": {"Fusion.dmg": "paketin SHA256 özeti"},
    "measured_at": 1793746800
  }
}
```

Bu alan kabulü çalıştıran güvenilir yayın işi tarafından koşu tamamlandığında
rapora eklenmelidir; eski raporu yeni pakete yeniden etiketlemek geçerli ölçüm
değildir. Doğrulayıcı tam production görev kümesini, güncel suite özetini,
model/config/source kimliğini, her görev için çağrı/süre bütçesini, en az üç
başarılı tekrarı, gözlenmiş sunulan model kimliklerini ve en fazla 48 saatlik
ölçüm yaşını denetler. Paket özetleri ve commit eşleşmek zorundadır. Kota veya
sağlayıcı sorunu ölçülmüş ürün başarısı sayılmaz. Geçersiz verilmiş rapor manifest
üretimini durdurur. Hiç rapor verilmezse `liveAcceptance.status=not_measured`
yazılır; mevcut CI hâlâ canlı kalite için yayın kapısı değildir.

Bu sözleşme kanıtı doğrular; canlı kabulü veya raporun güvenilir yayın ortamında
üretilmesini kendi başına gerçekleştirmez. Zorunlu canlı kabul işi ve gerçek
platform kabulleri tamamlanana kadar profesyonel hazır olma iddiası verilmez.
