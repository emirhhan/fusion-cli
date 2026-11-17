# Araştırmada hazır web araçlarını önceleme

## Kısa tasarım ve uygulama planı

Amaç, güncel bilgi araştırmasını hazır web arama/sayfa okuma araçlarıyla başlatmayı
tercih ettirmektir. Kullanıcının açık komut isteği ve web araçlarının bulunmaması
veya çalışmaması halinde diğer yetkili yollar korunur. Bu bir izin kuralı veya
shell yasağı değildir; kaynak kanıtı kapısı, model ayarları ve araç sözleşmeleri
değişmez.

Seçilen yaklaşım, kök istemin mevcut araştırma maddesini sade bir araç tercihiyle
değiştirmektir. Yeni yürütme politikası veya komut metnini kaynak kanıtı saymak
gereksiz ve daha riskli olurdu. Kök istemde araç protokolünü yinelememe sözleşmesi
korunur; araç adları yerine hazır web arama/okuma yetenekleri tarif edilir.

Plan:

1. Mevcut kök istemi ve yükleme/bütçe/katman/manifest kontrollerini oku.
2. Araştırma maddesini değiştir; iki doğrulama cümlesindeki tekrarı kısaltarak
   6.100 karakter sınırını koru. Kaynak, erişim tarihi ve doğruluk kurallarını koru.
3. Mevcut ilgili kontrolleri çalıştır, kapsamı ve sınırlamayı kaydet.
4. Yalnız sahip olunan istem ve bu notu commit et; bağımsız incelemeye sun.

## Gerekçe ve kanıt sınırı

`configured-default-f3f` denemesinde ilk ana yanıt araştırma için `curl | python3 -c`
komutu önerdi. Test düzeneği bu komutu shell sınırında engelledi. Ayrı, ağsız
derleme kontrolü Python yükünün mevcut Python 3.11 ortamında f-string sözdizimi
hatası taşıdığını gösterdi. Daha sonra hazır web araması güncel resmî bilgiyi
başarıyla aldı; fakat süre sınırında HTML yoktu. Engellenmiş komutun gerçekten
çalıştırıldığı veya tek başına bütün gecikmeyi açıkladığı iddia edilmiyor.

[Anthropic'in bağlam mühendisliği açıklaması](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents),
açık talimatları ve sınırlı bağlamı gözeten araç tasarımını destekleyen genel tasarım
gerekçesidir; bu değişikliğin model davranışını düzelttiğinin kanıtı değildir.

Statik istem ve mevcut çalışma akışı kontrolleri, modelin sonraki gerçek istekte
hangi aracı seçeceğini kanıtlamaz. Davranış kabulü ayrıca gerçek görev gerektirir.

## Uygulama ve doğrulama

Araştırma maddesi hazır web arama/okuma tercihini ve iki istisnayı artık açıkça
taşıyor. Kod doğrulama ve işlevsel davranışı doğrulama cümlelerindeki tekrar
kısaltıldı; test/lint/build/çalışma kontrolü ile dosyanın varlığıyla yetinmeme
gereksinimleri korunuyor. Diğer maddeler değiştirilmedi. Yeni bir araç adı veya
protokol eklenmedi; izin ve kanıt kapıları değişmedi.

Kök istem **6.096 karakter** olarak kaldı (tavan 6.100).
`system.md` SHA-256:
`71299a1a7d92b4f9dce6db85be73b422a4fe752947d5f56504e1b044e77220a9`.

Çalışma ağacı kökünde `PYTHONPATH=src` ve mevcut ana çalışma dizininin Python
yorumlayıcısıyla aşağıdaki 11 modül çalıştırıldı:

```text
tests/test_system_prompt_diet.py
tests/test_system_prompt_layers.py
tests/test_prompts.py
tests/test_prompt_butcesi.py
tests/test_prompt_manifest.py
tests/test_session_agent_prompt_parity.py
tests/test_research_source_contract.py
tests/test_scoped_source_read.py
tests/test_research_artifact_followup.py
tests/test_mixed_report_source_gate.py
tests/test_teacher_source_reports.py
```

Komut: `python -m pytest -o addopts='' -q <yukarıdaki modüller> --junitxml=<kanıt dizini>/targeted.xml`.
Sonuç: **183 başarılı, 21,04 saniye**; hata, başarısızlık veya atlama yok.
`git diff --check` temiz.

Kanıt dizini:
`/Users/motogate/Documents/Codex/2026-11-04/fusion-u-a-ve-bir-kullan/work/reliability-v2/research-tool-guidance-v5/`.
Modül listesi, çıktı ve JUnit XML burada saklandı. Bu geri alınabilir metin
düzeltmesi için birebir sözcük eşleştiren yeni test eklenmedi. Gerçek sağlayıcı,
tarayıcı veya native uygulama çalıştırılmadı; asıl çalışma dizini ve paketler
değiştirilmedi. Gerçek model davranışı ve görevin tamamlanması henüz kanıtlanmadı.
