# Belge teslim sunumu: bağımsız Python incelemesi

5 Kasım 2026. İncelenen ürün sürümü `74f3ec4f400be45d2f607b0a18b748a518d4c065`.
Sonuç: **BEKLET**, ana ajanın kabul ettiği üç sözleşme kusuru giderilmeden onay yok.
İlgisiz devam eden yürütme bağlamı değişiklikleri incelenmesin diye ayrı
`git archive` kaynak/test görüntüsü kullanıldı.

## Bulgular

**YÜKSEK — Eksik satırlarla gelen kritik sayaçlar başarılı karta dönüşebiliyor.**
`public_delivery_evidence`, doğrulandı/engellemiyor/yanlış iddia yok biçimindeki
bir belge zarfında `sorun_sayisi=3` ve boş `sorunlar` listesini belge sunumu olarak
koruyor. `criteria` alanı yokken `criteria_status_counts.failed=1` veya
`unverified=1` sessizce atılıyor ve yine doğrulanmış belge sunumu kalıyor. Kritik
sayaç denetimi, ayrıntı listesinin varlığına bağlı olmamalı; çelişki başarılı
sunumdan önce kapalı hata durumuna dönmelidir.

**ORTA — Kaynak URL sorgusu yanlış çıktı dosyasını eşleyebiliyor.**
Doğrulanmış raporun değişen yolu `rapor.html` iken görev
`Read https://example.org/?file=rapor.html and create a brief HTML report as other.html.`
olduğunda kısaltılmış sunum seçiliyor. Ham görevdeki dosya alt dizgesi, gerçek
çıktı hedefi yerine kaynak URL sorgusundan geliyor. Aynı hata
`/releases?name=rapor.html` biçiminde de üretildi. Eşleme, mevcut saf rapor kapsamı
mantığındaki gerçek çıktı hedefini kullanmalı; yolun bütünlüğü/büyük küçük harf
kimliği korunmalıdır.

**ORTA — Açık kod gösterme isteğinde eski sunum korunmuyor.**
Olağan rapor görevine `Show the source code in your reply.`,
`Cevabında HTML kodunu göster.` veya `Include the code changes in your answer.`
eklendiğinde belge sunumu seçiliyor. Model gövdesi değiştirilmedi; kusur,
tasarımdaki açık kod/denetim/kanıt çıktısı isteğine ilişkin sunum korumasının
uygulanmamasıdır. Ana ajan bu üç sınıfın da düzeltilmesini kabul etti.

## Bağımsız kanıt ve olumlu kontroller

- Sunum ve otomatik profil modüllerinde 55 test başarılı, 8,82 saniye.
- Altı değişen Python dosyasında Ruff, beş ürün dosyasında dar mypy temiz.
- Görev alanındaki `work/reliability-v2/document-delivery-python-review-v6/test_projection_contract.py`
  dosyasında yukarıdaki üç sınıf için sekiz bağımsız kırmızı kontrol var.
- Üç olumlu kontrol başarılı, 1,07 saniye: uzun Unicode/redaksiyon/32 KiB bütçe ve
  değişmeyen ya da bütünüyle çıkarılan yol; gerçek AppSession RPC → tek fiziksel
  TurnAnswered satırı → makbuz tekrarında ikinci yürütme olmaması → kapanıp açılan
  sohbetin aynı metin/kanıt/mesaj kimliğini yüklemesi; çalışan kabul edilmiş sohbet
  silinirse tam metne dönülmesi ve tombstone'un diriltilmemesi.
- Yeniden yüklenen model mesajına kanıt nesnesi enjekte edilmediği, kaynak
  AgentOutcome metninin değişmediği ve yeni sunumun tek satırda saklandığı sınandı.
- İlk makbuz tekrarı testinde aynı yanıt metni beklemek test hatasıydı: mevcut
  sözleşme kasıtlı boş metin ve aynı makbuzu döndürür. Test buna göre düzeltildi;
  bu durum ürün kusuru olarak sunulmadı.

Saf adaptörün incelenen SHA-256 değeri:
`41ab14efce2a52d4b33585d60a52b125e3738d81293f2eeccb97a86be28180cb`.

Bütün inceleme süreçleri terminaldir. Ürün dosyası değiştirilmedi; gerçek model,
ağ veya native çağrı yapılmadı. Ayrı yürütme kökü/sohbet bağlama kusurunun
giderildiği bu sürüm için ileri sürülmez; yetkilendirilmiş başka takip işidir.
