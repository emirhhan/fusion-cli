# Fusion — Sıfırdan Kullanım Kılavuzu

Hiçbir şey bilmiyormuş gibi, adım adım. Her adımda TAM olarak ne yazacağın yazıyor.

---

## 0) Fusion nedir? (tek cümle)

Terminalde çalışan bir kodlama asistanı — kod yazar, düzeltir, test eder. Bir de
"santral" gibi çalışıp birçok yapay zekâ modelini tek yerden kullanmanı sağlar.

---

## 1) Kurulum (bir kez yapılır)

Terminali aç, proje klasörüne gir ve şunu yaz:

```
make setup
```

Bu; Python ortamını kurar, gerekli her şeyi indirir, `.env` şablonu bırakır. Bitince
"kuruldu" der.

**Anahtar (ücretsiz):** Modellerin cevap vermesi için en az bir anahtar gerekir.
`.env` dosyasını aç, şu satırı gerçek anahtarınla doldur:

```
OPENROUTER_API_KEY=buraya-anahtarını-yapıştır
```

> Anahtarı https://openrouter.ai adresinden ücretsiz alırsın. Anahtar yoksa Fusion yine
> açılır ama model çağıramaz.

İsteğe bağlı ek özellikler için:
```
pip install 'fusion-cli[gateway]'   # web paneli / santral için
pip install 'fusion-cli[mcp]'       # MCP köprüsü için
```

---

## 2) İlk açılış

Terminale sadece şunu yaz:

```
fusion
```

Karşına renkli bir **FUSION** yazısı ve bir kutu çıkar. Artık içindesin — alta yazıp
Enter'a basarak konuşursun.

> **Not:** Büyük ASCII "FUSION" logosu terminal penceren GENİŞSE (≈91 sütun) çıkar.
> Pencere darsa otomatik olarak küçük "✦ FUSION" görünür. Pencereyi büyüt, büyük logo geri gelir.

---

## 3) En basit kullanım

Ne istiyorsan düz Türkçe yaz ve Enter'a bas. Örnek:

```
src/app.py dosyasındaki login hatasını bul ve düzelt
```

Fusion dosyayı okur, düzeltir, test eder ve ne yaptığını 1-2 cümleyle söyler. Sen hiçbir
şey ayarlamak zorunda değilsin — varsayılanlar iş görür.

---

## 4) İki motor: `agent` ve `fusion`

- **agent** (varsayılan) → İŞ yapar: dosya değiştirir, komut çalıştırır. Kodlama için bunu kullan.
- **fusion** → Aynı soruyu birçok modele sorar, en iyi cevabı seçer. Zor sorular / fikir için.

Geçiş:
```
/agent      → agent motoruna geç
/fusion     → fusion motoruna geç
```

---

## 5) "Ne kadar güçlü model?" → `/mode`

Yaz:
```
/mode
```
Bir liste çıkar; ok tuşlarıyla seç, Enter'a bas:

- `auto` → Fusion işe bakıp kendi seçer (önerilir).
- `low` → hızlı/ucuz · `medium` → dengeli · `high` → zor işler · `max` → en iyi.

Doğrudan da yazabilirsin:
```
/mode auto
/mode high
```

---

## 6) "Model ne kadar düşünsün?" → `/effort`

Bu, mode'dan AYRI. Yaz:
```
/effort high
```
Seçenekler: `auto · low · medium · high · xhigh · max`. Zor problemde `high`, basit işte
`low` mantıklı. Model desteklemiyorsa Fusion sessizce en yakınına iner.

---

## 7) Güvenlik ve geri alma (önemli)

- **Önce planı gör:** riskli/büyük değişiklikten önce
  ```
  /plan
  ```
  yaz. Fusion sadece PLAN yapar, dosyaya dokunmaz. Beğenirsen `/auto` ile uygulamaya
  geçersin.
- **Geri al:** son turun dosya değişikliklerini geri almak için
  ```
  /undo
  ```
- **Doğrula:** değişiklikten sonra test/lint çalıştırmak için
  ```
  /verify
  ```
- Yıkıcı bir komutta (`rm -rf` gibi) Fusion zaten durup sana sorar.

---

## 8) Fusion öğrensin → `/good` ve `/bad`

Fusion motorunda bir cevaptan memnunsan `/good`, değilsen `/bad` yaz. Fusion bunu
hatırlar ve zamanla senin için daha iyi model seçer.

---

## 9) Başka sağlayıcı / anahtar ekleme

İki yol var:

**A) Basit:** `.env` dosyasına ekle. Örnek OpenAI:
```
OPENAI_API_KEY=sk-...
```
Sonra model olarak `openai/gpt-4o` gibi yazabilirsin.

**B) Şifreli (önerilen):** Önce bir ana şifre belirle (bir kez):
```
export FUSION_SECRET_KEY=uzun-gizli-bir-cümle
```
Sonra Fusion içinde:
```
/providers add
```
Sağlayıcıyı seç, anahtarı yapıştır (ekranda görünmez). Anahtar **şifreli** saklanır.

Hangi sağlayıcılar tanınıyor, hangisi kurulu görmek için:
```
/providers
```

---

## 10) Çok hesap (ücretsizleri üst üste koy)

Aynı sağlayıcının birkaç ücretsiz hesabı varsa, `.env`'e şöyle yaz:
```
OPENROUTER_API_KEY=hesap1-anahtarı
OPENROUTER_API_KEY_2=hesap2-anahtarı
OPENROUTER_API_KEY_3=hesap3-anahtarı
```
Fusion istekleri bunlara dağıtır; biri "bugünlük doldu" derse otomatik ötekine geçer.
Üç hesap tek büyük kotaymış gibi çalışır.

---

## 11) Yerel web paneli + santral (başka araçları bağlama)

Bu, Fusion'ı "her aracın bağlanabildiği bir santral" yapar — hepsi SENİN bilgisayarında.

**Adım 1 —** Ayrı bir terminal aç, şunu yaz:
```
fusion serve
```
Ekranda iki adres görürsün:
- `http://127.0.0.1:8787/v1`  ← başka araçların bağlanacağı adres
- `http://127.0.0.1:8787/dashboard`  ← panel

**Adım 2 — Paneli aç:** Tarayıcına şunu yaz:
```
http://127.0.0.1:8787/dashboard
```
Sağlayıcıları, sağlık durumunu, modelleri görürsün. Kimse başkası göremez, sadece sen.

**Adım 3 — Başka bir aracı bağla** (ör. Cursor, Cline, OpenAI-uyumlu her şey):
o aracın ayarlarında:
- **Adres (base URL):** `http://127.0.0.1:8787/v1`
- **API key:** herhangi bir şey (yerelde kontrol edilmez, ör. `fusion`)
- **Model:** `auto` (ya da `low`/`medium`/`high`/`max`, ya da `openai/gpt-4o` gibi bir kimlik)

Artık o araç Fusion üzerinden çalışır: yedekleme, sağlık, çok-hesap otomatik devrede.
Durdurmak için `fusion serve`'ün olduğu terminalde **Ctrl-C**.

---

## 12) MCP köprüsü (alet paylaşımı)

**Fusion'ın aletlerini başka AI uygulamasına açmak** (ör. Claude masaüstü Fusion'ın kod
aramasını kullansın):
```
fusion mcp
```
(Claude masaüstü/Cursor'ın MCP ayarına bu komutu eklersin.)

**Fusion'a dışarıdan alet takmak** (ör. GitHub aleti): `~/.config/fusion-cli/config.yaml`
dosyasına ekle:
```yaml
mcp_servers:
  - name: github
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
```
Bağlı sunucuların aletlerini görmek için:
```
fusion mcp-tools
```
Bundan sonra ajan turlarında bu dış aletler otomatik kullanılabilir (onayınla).

---

## 13) Uygulama içindeki gerçek terminal

Masaüstü uygulamasında sağdaki çalışma panelinden **Terminal** sekmesini aç ve
**Yeni terminal** düğmesine bas. Yeni sekme, seçili çalışma alanının içinde senin
varsayılan kabuğunu açar; burada yazdığın komutlar Fusion ajanından bağımsızdır.

- Terminal ANSI renklerini ve etkileşimli programları korur; çıktıyı otomatik olarak
  sohbete ya da bir sağlayıcıya göndermez.
- `+` ile birden fazla terminal sekmesi açabilirsin. Sekmeleri ok tuşlarıyla,
  `Home` ve `End` ile klavyeden seçebilirsin.
- `×` yalnız etkin terminali kapatır. Kabuğun doğal olarak kapanması sekmede
  **Kapandı** olarak görünür.
- **Temizle** sadece ekrandaki birikmiş çıktıyı temizler; çalışan komutu durdurmaz.
  **Kopyala** seçili metni, **Yapıştır** ise panodaki metni terminale yollar.

### Paketli macOS duman kontrolü

Paketlenmiş uygulamada aşağıdaki dört kısa kontrolü yap. Her komut bitince kabuk
isteminin (`%` veya `$`) geri geldiğini doğrula:

1. Yeni bir terminalde `python3` yaz. Ardından `print("fusion-pty-ok")` ve
   `exit()` yaz; `fusion-pty-ok` görünmeli ve kabuk açık kalmalı.
2. `python3 -c 'import time; time.sleep(30)'` çalıştır, sonra **Ctrl+C** gönder.
   İşlem kesilmeli; terminal sekmesi kapanmamalı ve kabuk istemi yeniden görünmeli.
3. `vim /tmp/fusion-terminal-smoke.txt` aç, `:q!` yazıp Enter'a bas. Vim kapanmalı
   ve kabuk kullanılabilir durumda kalmalı. Vim kurulu değilse bunu paketin hatası
   olarak değil, makinedeki eksik araç olarak kaydet.
4. Uzun bir komut çalıştır (`python3 -c 'print("x" * 200)'` yeterlidir), ardından
   uygulamanın sağ çalışma panelini daraltıp genişlet. Satırlar yeniden sığmalı ve
   terminal yeni ölçülerde yazmaya devam etmelidir.

Bu kontroller kullanıcı girdisi, gerçek PTY ve macOS pencere yeniden boyutlandırması
gerektirdiği için tarayıcı görsel testinin yerine geçmez; paketli uygulamada elle
yapılır.

---

## 14) macOS'ta Fusion Talk ve doğrudan dağıtım

Fusion'ın doğrudan indirilen macOS paketi App Store için değil, geliştirici hesabı
gerektirmeyen ad-hoc dağıtım için hazırlanır. Uygulama ve DMG içindeki uygulama her
yeniden derlemede aynı `com.fusion.desktop` kimliğini taşır; mikrofon ve konuşma
tanıma izinleri bu kimlikle ilişkilendirilir.

DMG'yi aç, **Fusion**'ı **Applications** kısayoluna sürükle ve uygulamayı
`/Applications/Fusion.app` konumundan başlat. Talk'ı ilk açışta Fusion önce neden
mikrofon ve konuşma tanıma izni istediğini açıklar; devam ettiğinde macOS izinleri
sırayla sorabilir. İzin reddedilirse Talk mesaj uydurmaz, Sistem Ayarları'na giden
yeniden deneme yolunu gösterir.

Talk kullanırken:

- **Dinliyorum** görünmeden konuşma kaydedilmez.
- Sessizlik veya düşük güvenli ses sohbete mesaj olarak gönderilmez.
- Fusion konuşurken söze girmek seslendirmeyi kesip dinlemeyi yeniden başlatır.
- Yeşil pencere düğmesi mini/normal görünümü değiştirir; kırmızı düğme yalnız Talk'ı
  kapatır. Fusion'dan çıkmak mikrofon, tanıma ve seslendirme yardımcılarını da kapatır.

Ad-hoc paket Apple tarafından notarize edilmez. macOS ilk açılışı engellerse Finder'da
Fusion'a Control-tıkla, **Aç**'ı seç ve gösterilen yerel uygulamayı açtığını doğrula.

---

## Komut kopya kâğıdı

| Yaz | Ne yapar |
|-----|----------|
| `fusion` | Fusion'ı aç (REPL) |
| `/agent` · `/fusion` | Motor değiştir |
| `/mode` · `/mode high` | Model gücü profili |
| `/effort high` | Düşünme yoğunluğu |
| `/model` | Model değiştir |
| `/plan` · `/plan goster` · `/plan ac` | Plan kipine geç · kayıtlı planı yaz · planı editörde aç |
| `/undo` | Son değişikliği geri al |
| `/verify` | Test/lint çalıştır |
| `/review` (`/code-review`) · `/simplify` | Değişen kodu incele / sadeleştir (hata avı değil) |
| `/security-review [yol]` | Değişiklikleri OWASP başlıklarıyla tara; kod değiştirmez |
| `/debug [belirti]` | Fusion'ın kendi sorununu teşhis et (doctor + son eylemler) |
| `/batch <talimat>` | Talimatı bağımsız parçalara bölüp paralel alt ajanlarla uygula |
| `/doctor` | Kurulum denetimi (`fusion doctor` ile aynı çıktı) |
| `/loop 5m <görev>` · `/loop list` · `/loop stop [id]` | Görevi aralıkla yinele (oturum boyunca) |
| `/good` · `/bad` | Fusion'a geri bildirim |
| `/providers` · `/providers add` | Sağlayıcıları gör / anahtar ekle |
| `/health` | Model sağlığı / devre durumu |
| `/help` | Tüm komutlar |
| `fusion serve` | Yerel santral + panel |
| `fusion mcp` | Araçları MCP ile dışa aç |
| `fusion mcp-tools` | Dış MCP araçlarını listele |

---

## Sık karşılaşılanlar

- **"FUSION yazısı küçük çıktı"** → Terminal pencereni genişlet (≈91 sütun); büyük ASCII geri gelir. Ayar değil, ekran genişliği.
- **"Hiçbir model yanıt veremedi"** → Anahtar eksik/yanlış. `.env`'i kontrol et, `/providers` ile kurulu mu bak, ya da `fusion doctor` çalıştır.
- **Bir model sürekli hata veriyor** → Fusion onu otomatik bir süre atlar; `/health` ile görebilirsin.
- **Değişiklikten memnun değilim** → `/undo`.
- **Yavaş** → `/mode low` ya da `/effort low`.

Takıldığın her yerde `/help` yaz — bütün komutlar orada.

---

## İş-akışı makroları (`/simplify`, `/security-review`, `/debug`, `/batch`)

Claude Code'un paketli becerileriyle aynı adları taşırlar; Fusion'da hazır görev metni
olarak çalışır, agent'ın davranışını değiştirmezler.

- `/security-review` argümansız çalışma ağacındaki tüm değişiklikleri (`git diff`,
  staged + unstaged) tarar; `/security-review src/api/` gibi bir yol verilirse kapsam
  o olur. Bulgular `[KRİTİK|YÜKSEK|ORTA|DÜŞÜK]` başlıklarıyla, `dosya:satır` yerleriyle
  listelenir; kod değiştirilmez, sır değeri rapora yazılmaz.
- Masaüstünde **Değişiklikler** panelinin üstündeki "Güvenlik incelemesi" ve
  "Sadeleştir" düğmeleri aynı komutları gönderir.
- Kendi kuralını öne almak için `.claude/skills/<ad>/SKILL.md` yaz (ör.
  `.claude/skills/security-review/SKILL.md`): gövdesi yerleşik metnin ÖNÜNE eklenir,
  yerleşik metin silinmez.

---

## Plan kipi: plan dosyası ve kabul kartı

`/plan` ile plan kipine geçince agent yalnız okur ve planlar. Tur bitince plan
`~/.config/fusion-cli/plans/<sohbet>.md` dosyasına yazılır (`runtime.plan_files: false`
ile kapatılır; kapalıyken ya da dosya yazılamazsa kart da çıkmaz, plan sohbette durur)
ve "Plan hazır — uygulansın mı?" kartı çıkar:

- **Evet, otomatik kipte uygula** → `auto` kipine geçer ve planı uygulamaya başlar.
- **Evet, düzenlemeleri kabul ederek uygula** → `edits` kipi.
- **Evet, her adımda sor** → `security` (manuel) kipi.
- **Hayır, planlamaya devam et** → plan kipinde kalır.

Plan kipindeki her cevap plan sayılmaz: soruyla biten ya da başlıksız/listesiz kısa cevap
("Hangi veritabanı?") dosyayı değiştirmez ve kart açmaz; yeni plan eskisinin üzerine
yazılırken eskisi `<sohbet>.onceki.md` olarak saklanır. Kabulde oturum boyunca verilen
izinler sıfırlanır; uygulama görevi plan dosyasının yolunu taşır. Terminalde `/plan goster` planı basar, `/plan ac` `VISUAL`/`EDITOR` ile açar
(Claude Code'daki Ctrl+G karşılığı). Masaüstünde sohbette "Plan dosyası" kartı durur:
"Editörde aç" ve "Konumunu göster". Boru/CI gibi etkileşimsiz ortamda kart açılmaz,
yalnız yol basılır.

---

## Oturum zamanlayıcısı: `/loop` ve `cron_*` araçları

Claude Code'un `/loop` ve `CronCreate/List/Delete`, `ScheduleWakeup` araçlarının karşılığı.
Görevler **oturumla yaşar**: en çok 50 görev, en az 1 dakika aralık, 7 gün sonra düşer.
Vadesi gelen görev Fusion boştayken (tur yokken, soru beklemiyorken) **yeni tur** olarak
gönderilir; sohbette kullanıcı mesajı gibi görünür ve aynı onay kipinden geçer.

- `/loop 5m testleri koştur` · `/loop 30m /verify` (slash komutu da görev olabilir)
- `/loop <görev>` → varsayılan 10 dk; argümansız `/loop` → `.claude/loop.md` (proje ya da ev),
  yoksa yerleşik bakım görevi.
- `/loop list`, `/loop stop <id>`, `/loop stop all`.
- Ajan araçları: `cron_create {prompt, every|cron|in}`, `cron_list`, `cron_delete {id}`,
  `schedule_wakeup {in, note}` (uzun dış iş için kendini uyandırma). Cron 5 alanlıdır:
  `*/15 9-18 * * 1-5`.
- Kayıt: `memory_dir/oturum-cron/<sohbet>.json`; masaüstü sekmesi aynı kimlikle açılınca
  süresi dolmamış görevler geri gelir. Terminal REPL'inde her açılış yeni sohbet kimliği
  üretir (P-014 `--resume` gelince aynı dosya devralınır).
- Masaüstü: sohbet `cron.vadesi_gelenler` RPC'sini 15 sn'de bir yoklar (`cron.listele`,
  `cron.sil` de var). Kullanıcının kurduğu `/loop 30m /verify` masaüstünde de komut olarak
  çalışır; ajanın kurduğu satır (`cron_create`, `schedule_wakeup`) iki yüzeyde de yalnız düz
  tur olur, slash komutu olarak çalışmaz. Gönderilemeyen görev `cron.geri_ver` ile geri
  verilir, vade boşa gitmez. İstemde yarım yazılmış satır varken vade beklenir, yazılan silinmez.
  Sohbet kimliği gelmeden kurulan görevler kimlik gelince o sohbete taşınır; 7 günden eski
  kayıt dosyaları yüklemede süpürülür. Kalıcı **Zamanlananlar** ekranına "Cron ifadesi" türü eklendi
  (en sık 15 dakikada bir; denetim ifadenin iki eşleşmesi arasındaki en kısa farka bakar,
  `* 9 * * *` kayıtta reddedilir). Oturum zamanlayıcısı (`/loop`, `cron_create`) 1 dakikaya
  kadar iner. Cron saatleri yerel duvar saatidir; yaz saati geçişinde 09:00 görevi 09:00'da kalır.
