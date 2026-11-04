# URL ve talimat yükleme: bağımsız genel kod incelemesi

İncelenen kaynak: `790b396bae161899b661b13f756f02dc0a92294d`.
Kapsam: `17a07647..790b396b` içindeki URL düzeltmeleri (`2b947b00`,
`1ee40981`) ve talimat yükleme sözleşmesi (`790b396b`). Önceki inceleme
onayları bu değişikliklere aktarılmadı. Üretim kodu değiştirilmedi.

Karar: **APPROVE**. Bu kapsamda yeni bulgu yok.

## Davranış ve sınırlar

- Açık URL şemaları doğrulama öncesinde korunuyor. Desteklenmeyen şemalar,
  izinli yerel önizleme adreslerinde de tarayıcı başlatılmadan reddediliyor.
  HTTP(S), büyük harfli şemalar ve mevcut çıplak sunucu/port tamamlama
  davranışı korunuyor. Dosya adresinin hata metni HTTP önizleme yolunu açıklıyor.
- Varsayılan mod kullanıcı ve proje kurallarını başlangıçta yüklemeye devam
  ediyor. Açık `managed-only` seçimi olağan kuralları keşiften çıkarıyor;
  ajan döngüsündeki koruma alt klasör talimatlarını ve ek dizin kurallarını da
  engelliyor. Mevcut kurumsal talimat yolu korunuyor. Beceri keşfi bu değişikliğin
  dışında kalıyor.
- Başlangıç yükleyicisi gerçek eklenen kapsam dışı kuralları `kural` katmanlı
  dosya ölçümleriyle birlikte döndürüyor. Denetim ve ayarlar toplamı aynı
  yükleyiciyi kullanıyor; içerik karakterleri açıklama sarmalayıcılarını, ortam
  bilgisini, dış belleği ve ertelenen yol kapsamlı kuralları içermiyor.
- Kural kanca olayları güvenilir kullanıcı dosyaları için `User`, proje dosyaları
  için `Project` türünü taşıyor. Başlangıçtaki eski ve yeni olay yollarının
  birleşimi mevcut oturum tekilleştirmesinden geçiyor.

## Bağımsız doğrulama

Asıl sanal ortam Python'u ve `PYTHONPATH=src` kullanıldı. On beş modüllük
komut **242 testi** başarıyla bitirdi; süreç `98990`, çıkış kodu 0:

`test_instruction_startup_contract`, `test_instruction_layers`,
`test_instruction_rules`, `test_instruction_audit`, `test_instruction_layers_rpc`,
`test_birebir_extra_dir_rules`, `test_birebir_instructions_loaded`,
`test_instructions`, `test_project_instructions`, `test_url_normalization`,
`test_browser_local_origin`, `test_browser_request_guard`, `test_web_egress_pinning`,
`test_tools_browser`, `test_tools_web_planning`.

Ayrı `test_review_url_scheme_gate.py` dosyasındaki **11 bağımsız sınır testi**
de geçti; komut doğrudan çıkış kodu 0 döndürdü. Tarayıcı başlatma ve DNS sınırları
sahtelerle kaydedildi; gerçek yerel dosya erişimi veya saldırı çalıştırılmadı.

Ruff dokuz değişen kaynak modülünde geçti. Mypy, büyük ajan döngüsü dışındaki
sekiz değişen kaynak modülünde geçti. Başka bir genel test koşusu veya yeni
model, paketleme, kurulum ve canlı arayüz kabulü iddia edilmiyor.

Kanıt günlükleri görev çalışma alanında `work/reliability-v2/` altında:

- `general-url-instruction-final.log`
- `general-url-adversarial-final.log`

Kaynak SHA-256 parmak izleri:

| Dosya | SHA-256 |
|---|---|
| `tools/url_input.py` | `9e3f5ccf9effe7ae46c9b48cae7b2af9e1196d25f4c98f40b4f8f8b7fd54c706` |
| `tools/browser.py` | `fc656c96ffc1fdd9ca8ff227272f75099047dbe66e8596bc64aca87b819280f7` |
| `tools/web.py` | `2c6eab938825bfcac8ef87f0e1757b1cbc15ae91e4f82dfbcf4e86159749b362` |
| `engines/agent/instruction_rules.py` | `0feb947d6dfcecf3000097a0eaf0d74154e2df4f98c17d842887b2079420e5fb` |
| `engines/agent/project_instructions.py` | `4b992d989425f40cbe21d5c616ae0269261434d2d66d9b36e24564ac0f2c5624` |
| `engines/agent/instructions_hook.py` | `c482a7a63e62cfdad923617fe8985cbe1fe3beb0b057cb76eb0cc353b1a072cc` |
| `engines/agent/instruction_audit.py` | `f91fa22e4d2d2f8c0cbe9772039b8c4a13024d851446e6dda90a110e848918ab` |
| `appserver/instructions.py` | `c943d441b3fc4e809932d12ad6c2390477223e6cfd373fa86dec85c0b8697a8e` |
| `engines/agent/loop.py` | `203558635906913dbc955afad8ad1825b2f3dd084c66ea368fb802923ea67598` |

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE** — yalnız belirtilen kaynak kapsamı.
