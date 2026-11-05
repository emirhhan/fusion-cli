# Karma güncel araştırma: bağımsız genel kod incelemesi

Sabit kaynak: `74fcc573fcd8afd94de7996397aadcfbf93eb603`.
`src`, `tests` ve `pyproject.toml` ayrı görev dizinine `git archive` ile çıkarıldı.
Üretim kodu değiştirilmedi. Sonradan yapılan arayüz açıklaması veya diğer
değişiklikler bu incelemeye dahil değil.

Karar: **WARNING — bir yeni MEDIUM olumsuzlama regresyonu**.

## MEDIUM: yeni İngilizce dosya fiillerinin yasak biçimleri mutasyon sayılıyor

Dosya: `src/fusion_cli/engines/effects/detect.py:447`, karar `:594`.
Yeni `_DIRECT_EN_FILE_MUTATION` eşleştiricisi `save`, `generate`, `edit`
fiillerini ekliyor. Ortak `_EN_NEGATED_MUTATION` filtresi bu fiilleri kapsamıyor;
bu nedenle açıkça yasaklanan cümlecikler olumlu metinde kalıyor ve yeni dalda
`workspace_mutation` üretiyor.

Bağımsız sonuçlar:

| İstek | Önceki sabit `f023b8a5` | İncelenen `74fcc573` |
|---|---|---|
| `Do not save report.html. Tell me the latest stable Python version.` | `web_lookup` | `workspace_mutation` |
| `Never generate report.html. Explain stable releases.` | etki yok | `workspace_mutation` |
| `Don't edit report.html; just explain the concept.` | etki yok | `workspace_mutation` |

İkinci istek gerçek ajan döngüsünde yalnız açıklama döndüren sahte sağlayıcıyla
da yeniden üretildi: dosya oluşturulmadı, ancak ajan başarılı dosya değişikliği
kanıtı istedi ve sonuç `ok=False` ile "çalışma alanını değiştirme … başarılı
değiştirici araç … doğrulanamadı" oldu. Yasaklanan işi yapma yönünde gereksiz
yeniden istem oluşturuluyor; bu genel doğal dil mükemmelliği talebi değil,
yeni tanınan fiillerin ortak olumlu/olumsuz sözleşmesine girmemesi.

Düzeltme: yeni fiilleri ortak olumsuzlama filtresiyle tutarlı ele al; ayrı bir
olumlu cümleciğin dosya üretimini koru. Bağımsız iki olumlu devam kontrolü
(`Do not save report.html. Create other.html.` ve
`Don't edit report.html; generate another.txt.`) mevcut kodda geçiyor ve
düzeltmeden sonra da geçmeli.

## Diğer incelenen davranış

Doğrudan kapsanan üç TR/EN güncel rapor isteğinde dosya mutasyonu ve web
araştırması ayrı yükümlülükler. Gerçek ajan kontrollerinde yalnız yazma veya
yalnız okuma başarısız; ikisi birlikte başarılı. İstenen URL varsa tam kaynak
okuması sözleşmesi korunuyor. Kaynak belirtilmeyen araştırmada desteklenen
sayfa okuma araçları kabul ediliyor; tarayıcı kontrol/durum araçları ve indirme
araştırma kanıtı sayılmıyor. Başarılı araç kanıtı kabulü ve gerçek dosya işlem
iddiaları ayrı kontrol ediliyor. İzin, doğrulama veya kaynak içeriğinin güven
sınırı gevşetilmedi.

Bu kanıt kaynak içeriğinin anlamsal doğruluğunu, konuya uygunluğunu veya
güncelliğini garanti etmiyor. Python incelemesinin ayrı dosyadaki iki bulgusu
(`93100554`) bu tek genel inceleme bulgusunun sayısına eklenmedi ve burada
kapatılmış sayılmıyor.

## Bağımsız doğrulama

Asıl Python yorumlayıcısı ve snapshot'a bağlı `PYTHONPATH=src` kullanıldı:

- On modülde **289 test geçti**, süreç `48444`, çıkış 0.
  Günlük: `general-current-74fcc-tests.log`.
- Dört bağımsız RED / iki olumlu kontrol: **4 başarısız, 2 geçti**, süreç
  `11020`, çıkış 1. Günlük: `general-current-negated-red.log`.
  Dosya: `test_general_current_negated_artifact.py`.
- Ruff dört kaynak ve yeni testte geçti; mypy dört kaynakta geçti.
  Süreç `79269`, çıkış 0.

Günlükler ve bağımsız test dosyası görev çalışma alanında
`work/reliability-v2/` altında. İncelemeye ait çalışan süreç kalmadı.

Kaynak SHA-256 parmak izleri:

| Dosya | SHA-256 |
|---|---|
| `agent/execution_policy.py` | `587090937009b731701a26f2f450fe2bd2ad17493ee3b6a79ccd06d45f2ae94b` |
| `agent/loop.py` | `46b50de5da64531468e0127013b80713af80c93be289432a9dad0667dfb3aeb8` |
| `agent/research_scope.py` | `987925734c79da49d443c900c6e45912213326e3550208cad102882d37057acd` |
| `effects/detect.py` | `4c8c2efdec664313bdec1a0d790192490490118bded01503d050ff01d7fabf16` |

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 0 | pass |

Verdict: **WARNING** — açık olumsuzlama regresyonu düzeltilmeli.
Yeni tam model koşusu, paket veya bütün ürün kabulü iddia edilmiyor.
