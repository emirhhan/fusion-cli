# Araç Desteği Seviyeleri ve Model Uygunluğu

## Araç desteği (`ToolSupport`)

Her modelin araç (function/tool) çağırma yeteneği dört durumdan biridir:

| Seviye | Anlam | Mutation agent olabilir mi? |
|--------|-------|------------------------------|
| `native` | Gerçek tool-calling API | ✅ Evet |
| `emulated` | Taklit (prompt'a gömülü) | ❌ Eval eşiği gelene kadar hayır |
| `none` | Araç desteği yok | ❌ **Asla** (yalnızca sohbet/council) |
| `unknown` | Doğrulanmamış | ✅ Denenir (desteklenmeyen parametre düşer) |

Yetenek model **etiketlerinden** türetilir (uydurma tablo yok):

- `agent` etiketi → `native` (Fusion bu modelleri bugün araçlı agent turunda çalıştırıyor).
- `no-tools` etiketi → `none` (opak/web modelleri açıkça işaretlemek için).
- `emulated-tools` etiketi → `emulated`.
- Açık beyan (`no-tools`/`emulated-tools`) örtük çıkarımı (`agent`) ezer.

## Güvenlik kuralı (§5.3)

**Araç desteği olmayan model, dosya değiştiren/shell çalıştıran ana agent OLAMAZ.**
`select_agent_spec` araçsız bir adaya yönlendirilirse varsayılan (araç yetenekli)
`agent` rolüne düşer — no-tools model yapısal olarak mutation'a giremez. Bu tür
modeller yalnızca sohbet, council adayı, eleştiri ve özet rollerinde kullanılabilir.

## Profil uygunluğu (eligibility)

Model seçim ekranı, aktif profile göre modelleri süzer (`config/eligibility.py`).
Eşikler `defaults.yaml`'daki `profile_eligibility`'den gelir:

| Profil | min_context | araçsıza izin |
|--------|-------------|----------------|
| low | 0 | ✅ (sohbet modelleri) |
| medium | 0 | ❌ |
| high | 128000 | ❌ |
| max | 128000 | ❌ |

**Gerçekçilik kuralı:** filtre yalnızca *bilinen-kötü* modeli eler (araçsız model
mutation profilinde, bilinen-küçük bağlam eşiğin altında). **Bilinmeyen yetenek
gizlenmez** — canlı katalog modellerinin çoğu doğrulanmamıştır; hepsini gizlemek
listeyi işe yaramaz kılardı. `/development` katalog listesinde her model, uygun
olduğu profillerle rozetlenir.
