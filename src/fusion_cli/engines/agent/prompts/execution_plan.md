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
- Her başarı koşulu araç çıktısı, dosya durumu veya test sonucu ile kanıtlanabilir olsun.
- Her başarı koşulunu en az bir `verification_checks` kaydına bağla. `command`
  kontrolü doğrulayıcı içinde yeni komut çalıştırmaz; yürütme sırasında aynı komutun
  güvenli araç yolundan gerçekten çalıştığını denetler.
- HATA DÜZELTME görevlerinde `reproduction` kullan: `target` hatayı gösteren testi
  çalıştıran komuttur ve o komut düzeltmeden ÖNCE (kırmızı) ve SONRA (yeşil) aynı
  adımda çalıştırılmalıdır. Yalnız "şimdi geçiyor" kanıt sayılmaz: testin hatayı
  gerçekten yakaladığı ancak önce kırmızı görülerek bilinir.
- Dış dünyada yinelenmesi riskli işlemleri `never`, önce durum okunması gerekenleri
  `observe_first`, güvenle yinelenebilenleri `safe` olarak işaretle.
- Kullanıcıdan yeni onay isteme; verilen görev kapsamındaki belirsizlikleri en güvenli
  ve geri alınabilir varsayımla çöz.

Görev:
{task}
