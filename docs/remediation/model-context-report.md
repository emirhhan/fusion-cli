# B01–B07 uygulama raporu

Worktree: `/Users/motogate/.codex/worktrees/fusion-deep-fixes/fusion-cli`.
Temel: `2b2c8fe4` (önceki kullanıcı düzeltmeleri, bu işin kazanımı değil).
Commit atılmadı. Ana kaynak, kurulu uygulama, kullanıcı izinleri/hesapları değiştirilmedi.
Gerçek model veya ağ çağrısı yapılmadı. Bağımsız uzman review ve tüm repo kalite kapısı controller'ın sonraki adımıdır.

## Durumlar ve kök nedenler

| Madde | Durum | Değişiklik / kabul sınırı |
|---|---|---|
| B01 | Kod düzeltildi; canlı sentez kabulü açık | Genel kayan pencere, başarılı `web_fetch`/`web_search` kanıtını da yeniden üretilebilir çıktı sayıyordu. Araştırma kanıtı ayrı, ortak bütçeli projeksiyona alındı. 12 kaynak/12 bağımsız değer sentetik sentezinde bütün değerler ve kimlikler kalıyor; elle hesaplanan toplam 186 yeniden kuruluyor. Bu gerçek bir LLM sentez doğruluğu ölçümü değildir. |
| B02 | Kod düzeltildi | Tur içi özet izinin kaynağı temizlenmiş `old` yerine aynı sınırların özgün geçmiş segmenti oldu. Genel araç temizliği sonraki özetleyiciden kanıtı önceden alamaz. Kaynak çağrı/sonuç çiftleri ayrıca sınırlı projeksiyonla özete eklenerek sonraki aşamada kullanılabiliyor. |
| B03 | Kod düzeltildi | Kullanıcı mesajları yalnız baştan 2k örnekleniyordu; ara kullanıcı düzeltmeleri artık sıkıştırmada birebir korunuyor. Transcript örneklemesi baş/son alıyor. Son koşulu anahtar sözcüksüz ara mesajda ve ardışık iki sıkıştırmada koruyan test var. Çok uzun gerçek kullanıcı mesajları için sessiz kesme yapılmaz; mevcut toplam bağlam bütçesi durma yolunun devreye girmesi gerekebilir. |
| B04 | Kod düzeltildi | `apply_single_model` her seçimde boş metadata ile yeni spec kuruyordu. Tam model kimliğine ait etkin rol/kademe kaydı çözülüyor; aynı modelin effort/tags/context kaydı korunuyor, farklı/hiç bilinmeyen modele eski kanıt aktarılmıyor. Tek-model strict seçimin fallback'siz kalma semantiği korunuyor. |
| B05 | Kod düzeltildi | Factory yedeklerde koşulsuz boş yetenek kullanıyordu. `model_specs` ile yedeğin kendi tam kimlik kaydı çözülüyor; bilinmeyen yedek birincilin kanıtını miras almıyor. Bütün config sahibi üretim `build_provider` yollarına helper bağlandı (agent loop bağlaması controller tarafından). `liveness.ping_for` açıkça `fallback=()` ürettiği için kayıt listesi gerektirmiyor. Gerçekte uygulanan effort mevcut execution receipt alanlarından görülüyor. |
| B06 | Kod düzeltildi; canlı sağlayıcı davranışı açık | Başlık/URL dışı snippet ve açık tarih beyanı kayboluyordu; HTML ve RSS bunları koruyor. Arama zamanı, tarih filtresi ve filtre uygulanmasının yalnız sağlayıcıya istek düzeyinde olduğu structured sonuçta taşınıyor. `recency_days` veya `date_from`+`date_to` doğrulanarak DDG `df` parametresine iletiliyor. RSS yedeğinde filtre desteği doğrulanmadığından filtreyi sessiz düşürerek sonuç vermiyor. Tarihsiz sonuçta tarih uydurulmuyor. Canlı DDG'nin filtreye ne kadar sadık olduğu ölçülmedi. |
| B07 | Kod düzeltildi | Başarılı fetch final URL ve erişim saatini atıyordu. İstenen URL, final URL, UTC fetched_at, açık HTML meta published/modified beyanı, tarih kanıt türü ve sınırlı içerik özeti tek `structured.source` kaydına bağlandı. URL/saat modelin metin sonucunda da mevcut. Gövde tarihinden yayın tarihi tahmin edilmiyor. Tarihler kaynağın açık beyanıdır, bağımsız doğrulanmış yayın tarihi değildir. HTTP header/JSON-LD tarih kapsamı bu değişikliğin dışında kalır. |

## Kaynak bütçesi ve semantik güvenlik

- `research_evidence.py` ortak projeksiyon bütçesi **16.000 karakter**. Kaynak metni yanında URL/argüman, araç adı, çağrı kimliği ve sonuç kimlik zarfı da sayılır. Küçük kanıtlar tam kalır; büyükler baş/son örneklenir ve her örnekte açık eksiltme uyarısı bulunur. İlgili kaynak çağrısının URL'si generic argüman taslağına çevrilmez.
- Bu, bütün model prompt'una 16k sınırı iddiası değildir: en yeni henüz görülmemiş araç grubu, kök görev, son mesajlar ve diğer context bileşenleri kendi mevcut kurallarıyla korunur. Toplam prompt bütçesinin sahibi mevcut context budget mekanizmasıdır.
- 17.000 kaynak veya toplam bütçeyi aşan uzun kaynak URL kimliklerinde her kaynağı anlamlı temsil etmek matematiksel olarak sığmaz. Bu durumda sıkıştırma **özgün mesaj listesini geri verir**, sessiz boş kaynak/kimlik üretmez; mevcut bağlam bütçesi denetimi ilerleyemeyen sıkıştırmayı yönetir. Bu sınır iki ayrı regresyonla ölçüldü.
- Baş/son örnekleme ortadaki kritik bilgiyi garanti edemez; not tam kaynağı yeniden okumayı açıkça ister. Bu durum gerçek çok kaynaklı LLM bilgi doğruluğu kabulünü kapatmaz. 12 kaynaklı sabit fixture 16k'ya sığdığı için hiç örneklenmez ve tüm değerleri korur.
- Ara kullanıcı düzeltmesi birebir tutulduğu için transcript örneklemesinin ortayı atlaması nihai model girdisinde kullanıcı şartını silmez. Kullanıcı talimatları tool verisi veya harness talimatı gibi yeniden etiketlenmez. Kaynak kanıtı da tool rolünde kalır.

## Red / green kaydı

Tüm komutlarda çalışma dizini worktree'dir. Ortak önek:

```sh
PYTHONPATH=$PWD/src /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python -m pytest
```

1. `tests/test_model_metadata_remediation.py -q`: ilk **3 failed**; aynı kimlik metadata'sı boş, yeni kimlik kaydı çözülmüyor, factory `model_specs` keyword'unu kabul etmiyor. İlk düzeltme sonrası model kimlik/receipt testleriyle **15 passed**.
2. `tests/test_research_context_remediation.py -q`: ilk **3 failed**; Kaynak0 maskeli, özet izinde kaynak yok, ara düzeltme sonuçtan kayıp. İlgili mevcut paketlerle ilk yeşil **76 passed**.
3. `tests/test_web_provenance_remediation.py -q`: ilk **4 failed**; enjekte Clock parametresi yok, HTML snippet/tarih atılıyor, search zamanı/filtre sözleşmesi yok. Web mevcut paketleriyle ilk yeşil **68 passed**.
4. `tests/test_model_metadata_remediation.py::test_side_chat_factory_connects_configured_fallback_proof -q`: **1 failed** (yedek SDK çağrısında effort yok) → entegrasyon sonrası dosyanın **4 testi passed**.
5. Kaynak bütçesi sınır testleri: **3 failed** (metadata ölçümü yok, 17k kaynak/uzun URL için kayıplı özetleme deneniyor) → düzeltildi.
6. `tests/test_research_context_remediation.py::test_source_url_is_not_replaced_by_generic_argument_stub -q`: **1 failed** (uzun URL generic argüman stub'ına dönüşüyor) → düzeltildi; kaynak/context yeni dosyası son halinde **7 passed**.

## Son doğrulama

Son scoped test komutu (birebir):

```sh
PYTHONPATH=$PWD/src /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python -m pytest -o addopts='' -q -ra tests/test_model_metadata_remediation.py tests/test_research_context_remediation.py tests/test_web_provenance_remediation.py tests/test_model_identity_invalidation.py tests/test_model_execution_contract.py tests/test_output_masking.py tests/test_context_invariants.py tests/test_turn_compaction.py tests/test_original_trace_compaction.py tests/test_tools_web_planning.py tests/test_web_egress_pinning.py tests/test_risk_classifier.py tests/test_narration.py tests/test_visual_verify.py tests/test_side_chat.py tests/test_btw_side_question.py tests/test_prompt_opt_research_factory.py tests/test_d4_learning_robust.py tests/test_d4_narration_image.py tests/test_gateway.py tests/test_user_denial_stops_turn.py
```

Sonuç: **348 passed in 39.24s**.

Son sıcak REPL factory entegrasyonu sonrası ayrıca `PYTHONPATH=$PWD/src /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python -m pytest -o addopts='' -q -ra tests/test_repl.py`: **97 passed in 8.81s**.

```sh
/Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/ruff format --check $(cat docs/remediation/model-context-files.txt)
/Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/ruff check $(cat docs/remediation/model-context-files.txt)
PYTHONPATH=$PWD/src /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/mypy $(cat docs/remediation/model-context-files.txt | rg '^src/')
git diff --check
```

Ruff: **31 files already formatted; All checks passed!** Mypy ilk sınır düzeltmesinde metadata sözlüğünde iki `str | None` tip hatası verdi; açık annotation ile giderildi. Son scoped kontrol: **Success: no issues found in 26 source files**. `git diff --check` temiz.

Eval worker'ı yeni factory keyword'ünden sonra 19 fusion_research test fake'inde TypeError raporladı. `tests/fakes.py::patch_providers._build` ve `tests/test_user_denial_stops_turn.py` explicit fake imzaları yeni optional keyword ile eşlendi. `test_agent_loop.py` fake'ini controller eşledi. Eval worker'ına tekrar koşma bilgisi verildi; geniş eval sonucu kendi raporundadır.

Dosya listesi: `docs/remediation/model-context-files.txt`. Liste ana agent loop'taki controller entegrasyonunu içermez. Kurulum gerekliliği: yeni bağımlılık yok; standart paket yeniden derlemesi dağıtım öncesi ayrıca yapılmalıdır; bu işte kurulum yapılmadı.
