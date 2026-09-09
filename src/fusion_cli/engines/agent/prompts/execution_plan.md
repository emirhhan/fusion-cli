Kullanıcı görevini küçük, doğrulanabilir ve bağımlılıkları açık adımlara ayır.
Yalnızca JSON döndür; açıklama veya Markdown kullanma.

Şema:
{
  "plan_id": "kısa-kararlı-kimlik",
  "task": "kullanıcının asıl görevi",
  "schema_version": 2,
  "steps": [{
    "step_id": "benzersiz-kimlik",
    "goal": "tek ve somut hedef",
    "depends_on": ["önceki-adım-kimliği"],
    "expected_effects": ["workspace_mutation"],
    "allowed_tool_families": ["files", "shell", "web", "delegation"],
    "success_criteria": ["gözlenebilir başarı koşulu"],
    "verification_hint": "başarının nasıl denetleneceği",
    "phase": "discovery | execution",
    "verification_checks": [{
      "criterion_id": "success_criteria içindeki koşulun birebir metni",
      "kind": "file_exists | file_contains | command | tool | reproduction",
      "target": "göreli dosya yolu, gerçekten çalıştırılacak komut veya araç adı",
      "expected": "file_contains için sabit metin; tool için beklenen argüman alt kümesinin JSON nesnesi; diğerlerinde boş"
    }],
    "retry_safety": "safe | observe_first | never"
  }]
}

Kurallar:
- Yalnızca gerekli adımları üret; bağımsız adımları gereksiz yere zincirleme.
- Görev yolu, dosya yapısı veya dış kaynağı belirsizse ilk adımı `discovery` yap.
  Keşif adımı yalnız mevcut durumu ve gerçek yolları kanıtlar; dosya üretmeyi vaat etmez.
  Dosya oluşturan veya değiştiren adımları `execution` yap ve keşif adımına bağla.
- Her başarı koşulu araç çıktısı, dosya durumu veya test sonucu ile kanıtlanabilir olsun.
- Her başarı koşulunu en az bir `verification_checks` kaydına bağla. `command`
  kontrolü doğrulayıcı içinde yeni komut çalıştırmaz; yürütme sırasında aynı komutun
  güvenli araç yolundan gerçekten çalıştığını denetler.
- Hata düzeltmede `reproduction` kullan: `target` testi çalıştıran komuttur; komut
  düzeltmeden önce (kırmızı) ve sonra (yeşil) aynı adımda çalışmalıdır.
- Bir adım dosya üretiyorsa yolu `expected_effects` içine `file:<yol>` olarak yaz ve
  o adımın dosya kontrollerinde AYNI yolu hedef göster. İki farklı yol iddia eden
  plan reddedilir; adım hangisini üretirse üretsin öteki düşer.
- Kontrol hedefi bir TAHMİN değil, adımın uyacağı sözleşmedir: adıma birebir bu yol
  bildirilir. Var olmayan bir klasör yapısını uydurma; görevde ya da depoda geçen
  yolu kullan.
- Bir adımın hedefi, o adıma verdiğin `allowed_tool_families` ile YAPILABİLİR olmalı.
  Ağdan içerik gerekiyorsa `web` ailesini ver; veremiyorsan o adımı planlama ve işi
  mevcut araçlarla yapılabilecek biçimde kur (örneğin varlığı koddan üret).
- Alanları ŞEMADAKİ gibi yaz: listeler liste, her adımda `retry_safety` olsun.
- Dış dünyada yinelenmesi riskli işlemleri `never`, önce durum okunması gerekenleri
  `observe_first`, güvenle yinelenebilenleri `safe` olarak işaretle.
- Kullanıcıdan yeni onay isteme; verilen görev kapsamındaki belirsizlikleri en güvenli
  ve geri alınabilir varsayımla çöz.

Görev:
{task}
