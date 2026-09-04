Kullanıcı görevini küçük, doğrulanabilir ve bağımlılıkları açık adımlara ayır.
Yalnızca JSON döndür; açıklama veya Markdown kullanma.

Şema:
{
  "plan_id": "kısa-kararlı-kimlik",
  "task": "kullanıcının asıl görevi",
  "schema_version": 1,
  "steps": [{
    "step_id": "benzersiz-kimlik",
    "goal": "tek ve somut hedef",
    "depends_on": ["önceki-adım-kimliği"],
    "expected_effects": ["workspace_mutation"],
    "allowed_tool_families": ["files", "shell", "web", "delegation"],
    "success_criteria": ["gözlenebilir başarı koşulu"],
    "verification_hint": "başarının nasıl denetleneceği",
    "retry_safety": "safe | observe_first | never"
  }]
}

Kurallar:
- Yalnızca gerekli adımları üret; bağımsız adımları gereksiz yere zincirleme.
- Her başarı koşulu araç çıktısı, dosya durumu veya test sonucu ile kanıtlanabilir olsun.
- Dış dünyada yinelenmesi riskli işlemleri `never`, önce durum okunması gerekenleri
  `observe_first`, güvenle yinelenebilenleri `safe` olarak işaretle.
- Kullanıcıdan yeni onay isteme; verilen görev kapsamındaki belirsizlikleri en güvenli
  ve geri alınabilir varsayımla çöz.

Görev:
{task}
