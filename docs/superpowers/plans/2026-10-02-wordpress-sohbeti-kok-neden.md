# "WordPress tabanlı site" sohbeti — kök neden ve düzeltme planı

Sohbet: `b8570a27` (30 Eyl 14:03 – 1 Eki 02:55). Kök dizin `~/Desktop` (transcript özeti
`eb6bc2f0f499b177` = `/Users/motogate/Desktop`).

## Zaman çizelgesi (transcript zaman damgaları, yerel saat)

| Saat | Olay |
|---|---|
| 30 Eyl 14:03 | İlk istek → "çıktı bütçesi doldu (yalnız düşünme)" |
| 17:41 | Tema dosyaları yazıldı; kabuk komutu var olmayan `/Users/mnt/data/...` yolunu kullandı |
| 18:00 | Var olmayan `js/navigation.js`, `template-parts/*` dosyalarına başvuru; `hero.svg` |
| 18:04 | PHP sözdizimi hatalı iki dosya; önceki tur "hazır" demişti |
| **23:34:41** | "projeyi tamamiyle sil ben sıfırdan oluşturacağım" |
| 23:41–23:42 | `01-Projeler/projeler/GATE-AI/web/{.next,node_modules}` dizinlerinin son değişikliği |
| **23:42:09** | Tur iptal edildi — silme yarıda kesildi (GATE-AI'da boş dizinler kaldı) |
| 23:43 | "tüm projeleri değil" → `run_shell` reddedildi |
| 23:45:29 | `sneaksup-wp` YENİDEN doğdu (o da silinmişti) — ajan "sil" isteğine dosya yazarak cevap verdi |
| 23:56 | "hatalı bir şey silmiş olabilir misin?" → öğretmen kurtarma planı verdi, ajan 11 dosyayı yeniden yazdı ve "tamamlandı ve doğrulandı" dedi (doğrulama komutu çalışmadı) |

Silme komutunun kendisi hiçbir yerde kayıtlı değil (çekirdek logu boş, web izi kapalı,
denetim günlüğü yoktu). Kanıt: dosya zamanları + transcript.

## Kök nedenler (koddan doğrulandı)

1. **Kök dizin bir "proje deposu"ydu.** Masaüstü çok sayıda projeyi içeriyordu; ajan için
   "proje" = çalışma kökü = Masaüstü. Hiçbir yerde "bu kök birden çok proje içeriyor"
   bilgisi yoktu.
2. **Otomatik kipte betik yoluyla silme onaysızdı.** `python3 x.py`, `bash x.sh`, `node x.js`
   "projenin kendi betiği" sayılıp sorulmadan çalışıyor; betik İÇERİĞİNE bakılmıyordu
   (ölçüldü: `is_unattended_safe("python3 sil.py") == True`). `make_tool` araçları da öyle.
3. **Onay kartı hedefi göstermiyordu.** `rm -rf ./*` "projeyi sil" isteğine uygun görünür;
   kart bunun bütün Masaüstü olduğunu, kaç öğe/GB olduğunu söylemiyordu.
4. **Soru mesajı iş emri gibi işlendi.** "silmiş olabilir misin?" sorusu öğretmen planına
   dönüştü ve dosya yazıldı. Soru/geçmiş sorgusu için salt-okuma kipi yoktu; ajanın kendi
   geçmiş araç çağrılarını okuyabileceği bir araç da yoktu.
5. **Uydurma yol.** `/Users/mnt/data/...` web öğretmeninin (Gemini) sanal ortam yolu; kabuk ve
   dosya araçları var olmayan kök yollara karşı hiç uyarmıyordu.
6. **PHP doğrulaması yoktu.** Doğrulama kapısı JS/HTML/CSS'i denetliyor, PHP'yi değil; tema
   dosyalarında var olmayan dosyalara başvuru da denetlenmiyordu.
7. **"Doğrulandı" iddiası kanıtsız kalabiliyordu.** Tur raporu "doğrulama komutu
   ÇALIŞTIRILMADI" notunu ekliyor ama modelin "tamamlandı ve doğrulandı" cümlesi aynen
   kullanıcıya gidiyordu.
8. **Düşünme bütçeyi yiyince tek deneme.** Akıl yürüten model `max_tokens`'ı düşünmeye
   harcayınca tur cevapsız bitiyor, kullanıcıya ayar değiştirmesi söyleniyordu.

## Düzeltmeler

| # | Değişiklik | Kök neden |
|---|---|---|
| A | Betik çalıştırmadan önce içerik denetimi: proje deposunda ya da proje dışına silen betik "tehlikeli" sayılır (otomatik kipte bile sorulur) | 2 |
| B | Silme onay kartı hedefleri çözülmüş TAM YOL + öğe sayısı + boyutla ve "çöpe taşınır / korumalı, reddedilecek" bilgisiyle gösterir | 3 |
| C | Kök birden çok proje içeriyorsa sistem notu: "kullanıcının 'proje' dediği tek alt klasör olabilir; hangisi olduğunu sor"; kök içeriğini toptan silen komut kartta DİKKAT ile sorulur | 1 |
| D | Soru niteliğindeki mesaj (eylem fiili yok, soru eki/işareti var) salt-okuma kipinde koşar; öğretmen planı çağrılmaz; `recent_actions` aracı denetim günlüğünden son araç çağrılarını okur | 4 |
| E | Var olmayan kök yola (`/mnt/data`, `/Users/<olmayan>`, `/home/user`, `/workspace`) giden kabuk/dosya çağrısı çalıştırılmadan reddedilir, gerçek kök söylenir | 5 |
| F | PHP kapısı: dokunulan `.php` dosyaları `php -l` ile; WordPress temasında var olmayan dosyaya başvuru (`get_template_part`, `get_template_directory_uri() . '/...'`) engelleyici bulgu | 6 |
| G | Kanıtsız doğrulama iddiası: turda başarılı doğrulama yoksa "doğrulandı/test edildi/hatasız" cümleleri kullanıcıya iddia olarak gitmez, model bir kez düzeltmeye zorlanır | 7 |
| H | Düşünme bütçeyi yiyip metin çıkmadıysa `max_tokens` iki katıyla bir kez yeniden denenir | 8 |

## Uygulama sonucu (2 Ekim 2026)

| # | Dosya | Test |
|---|---|---|
| A | `tools/delete_preview.script_danger`, `engines/agent/approval.build_request` (2 Ekim: onaylanırsa çalışır) | `test_wordpress_olayi`: betik dilleri, AutoApproval soruyor |
| B | `tools/delete_preview.describe_delete` → onay isteğinin `danger` metnine eklenir (CLI, masaüstü, Chrome paneli aynı metni görür) | kart metni, korumalı hedef |
| C | `engines/agent/project_instructions.container_root_note` (ORTAM bloğu) | Masaüstü uyarısı / tek proje sessiz |
| D | `engines/effects/detect.is_history_question` → `workspace_read`; salt okuma turunda öğretmen planı çağrılmaz; `recent_actions` aracı | 4 soru + 3 iş isteği; soru turunda yazma yok |
| E | `tools/files.invented_path_reason` (dosya araçları) + `tools/shell._invented_path` | kabuk ve dosya okuma |
| F | `engines/agent/php_verify.PhpVerifier` (WebVerifier içinde) | sözdizimi, eksik şablon, `wc_get_template_part`/yorum/klasör yanlış alarmı yok; gerçek temada temiz |
| G | `turn_report.claims_verification` + `false_claim` → `blocks_success` | rapor uyarısı; `test_kanitsiz_test_gecti_iddiasi_turu_basarisiz_yapar` |
| H | `loop._call_with_retries`: kesilmiş cevapta `max_tokens` ×2 (en fazla ×4) | bütçe iki katına çıkıyor |

Uçtan uca: `test_olay_otomatik_kip_sorar_onaylanan_silme_cope_gider_ve_geri_alinir` —
gerçek döngü, olaydaki `rm -rf ./*`: otomatik kip bile sorar, kart "birden çok proje"
der; onaylanınca her öğe Fusion çöpüne gider ve geri alınınca projeler yerindedir.

## 2 Ekim düzeltmesi: kesin ret kaldırıldı, kipler Claude'a benzetildi

Kullanıcı: "ben gerçekten bir şey silmek istersem silemeyecek miyim çok saçma" ve
"otomatik modunda bile gereksiz yerlerde soru soruyor".

- **Silme reddedilmez.** Yalnız `/` ve ev dizininin kendisi silinemez
  (`safe_delete.forbidden_reason`). Masaüstü, kökün kendisi/üstü, proje dışı ve çok
  projeli klasör `caution_reason` ile kartta DİKKAT notu alır ve otomatik kipte sorulur.
  Sade `rm` (joker dahil: `rm -rf ./*`) çöpe gider; karmaşık silme (`find -delete`)
  kartta "KALICI" diye gösterilir ve onaylanırsa çalışır. Kart metni `delete_preview`'da.
- **Silen betik** yalnız proje deposunda ya da proje dışına uzanan yollarla siliyorsa
  sorulur; projenin kendi `rmtree('dist')` betiği sorulmaz.
- **Beş kip** (`approval.ApprovalMode`): Otomatik (`auto_policy.auto_risk` — yalnız
  proje dışı, sistem, yayın/push, uzak sunucu, veri gönderimi, veritabanı silme
  sorulur), Manuel (`security`; okuma serbest), Düzenlemeleri kabul et (`edits`; eski
  beyaz liste), Plan (salt okuyan kabuk komutu artık serbest), İzinleri atla (`bypass`;
  hiçbir şey sorulmaz, Shift+Tab döngüsünde yok).
- **Chrome:** `ToolEffect.REMOTE_INTERACT` (yazma, sıradan tıklama, tuş) otomatik kipte
  sorulmaz; Enter yalnız mesaj kutusunda ya da riskli düğmeli formda sorulur
  (eklentide `describe_key`). Panelde beş kip seçilebilir.
- **G yumuşatıldı:** genel "doğrulandı" yalnız uyarı alır; turu başarısız yapan, kanıtsız
  "testler geçti / lint temiz" gibi komut gerektiren iddiadır.

Kapsam dışı kalan: "sil" isteğine dosya yazarak cevap verme gibi talimat yanlış anlama
davranışı model kalitesine bağlıdır; C (depo uyarısı) ve D (geçmiş sorusu) bunun en sık
tetikleyicilerini kapatır ama modelin her yanlış yorumunu engelleyemez.
