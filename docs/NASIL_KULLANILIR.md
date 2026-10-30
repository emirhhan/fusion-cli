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

### İzin kuralları (allow / ask / deny) — Claude Code ile aynı dosyalar

Fusion, Claude Code'un `permissions` listelerini okur ve yazar; iki araçta tek liste:

| Katman | Dosya | Ne zaman okunur |
|---|---|---|
| Fusion (kullanıcı) | `~/.config/fusion-cli/permissions.json` | her zaman |
| Claude (kullanıcı) | `~/.claude/settings.json` | her zaman |
| Proje | `<proje>/.claude/settings.json` | yalnız `fusion trust` sonrası |
| Proje (yerel) | `<proje>/.claude/settings.local.json` | yalnız `fusion trust` sonrası (Fusion'ın kendi yazdığı dosya otomatik güvenilir) |

Kalıplar: `Bash(npm run *)`, `Read(~/.ssh/**)`, `Edit(/src/**)` (`/` proje kökü, `//` disk kökü,
`~` ev), `WebFetch(domain:example.com)`, `Skill(deploy *)`, `Agent(arastirmaci)`,
`mcp__sunucu__arac`, ya da doğrudan bir Fusion aracı (`desktop_click`). Karar sırası sabittir:
**deny → yıkıcı komut → ask → allow → çalışma modu**. `deny` "İzinleri atla" modunda da
geçerlidir; `ask` Otomatik modda bile sordurur ve oturum hafızasıyla susturulamaz. Kurallar
yalnız yazan araçlarda değil **okuma, arama ve web araçlarında da** uygulanır
(`Read(~/.ssh/**)` deny → `read_file`, `search_code`, `glob`; `WebFetch(domain:x)` → `web_fetch`).
Arama/listeleme aracına `path` verilmediyse kök alınır: deny/ask kuralının kapsamı aramanın
içindeyse arama da yasaklanır/sorulur. `Agent(...)`/`Task(...)` çekirdekteki `spawn_agent`,
`spawn_agents` araçlarını kapsar; `Edit/Write(...)` indirme, arşiv açma ve görsel üretme
araçlarının hedefini de kapsar.

Kabuk zincirleri (`a && b`) parça parça değerlendirilir: bir parça yasaksa tamamı yasak, hepsi
izinliyse sorulmaz. Sarmalayıcılar açılır: `sh -c '…'`, `eval`, `timeout 5 …`, `sudo …`,
`/bin/rm` içindeki komut da kurala karşı denenir. Dosyaya yönlendirme (`> x`, `>> x`, `| tee x`)
içeren komut `allow` ile serbest kalmaz (deny/ask yine uygulanır). Bilinen sınır: `python -c "…"`
gibi satır içi kodun içi kurallara karşı çözülmez; o yol ayrı risk denetiminden geçer.

Güvenilmeyen proje dosyasından (`fusion trust` yapılmamış ya da içerik değişmiş) yalnız
**allow** kuralları düşer; deny ve ask kuralları yine okunur.

```
/permissions                              # listele
/permissions add allow Bash(npm test *)   # projeye yaz
/permissions add deny Read(~/.ssh/**) --user
/permissions remove allow Bash(npm test *)
fusion permissions add ask "Bash(git push *)"   # terminalden, aynı iş
```

Masaüstünde **Ayarlar › İzinler › İzin kuralları** tablosu aynı dosyaları gösterir; ekle/sil.
Silme yalnız Fusion'ın yazdığı dosyalarda çalışır (`permissions.json` ve güvenilir
`settings.local.json`); `~/.claude/settings.json` ve proje `settings.json` salt okunurdur
(sil düğmesi kapalı, kuralı dosyadan elle kaldır). Güvenilmeyen yerel dosyadan silme reddedilir:
silmek izin açmaz. Proje izin dosyası güvenilmiyorken kural kullanıcı dosyasına yazılır ve bu
**tüm projeleri** etkiler; kart ve komut çıktısı bunu açıkça söyler, masaüstünde "Bu proje"
kapsamı o durumda hata verir ("Tüm projeler"i seç ya da projeye güven).

### Onay kartında "bir daha sorma" ve ret gerekçesi

- Onay kartındaki **Evet, bir daha sorma (kalıcı)** seçeneği en dar kuralı yazar
  (`Bash(git status *)`, `Edit(/src/alt/**)`) ve sonraki oturumlarda da sorulmaz. Yorumlayıcı ve
  başlatıcılarda (`python`, `bash`, `node`, `npx`, `find`, `xargs`, `ssh`, `curl`…) ve ilk iki
  sözcüğü düz olmayan komutlarda kural komutun **kendisidir** (`Bash(python -m pytest)`), genel
  `python *` yazılmaz. Yıkıcı işlemlerde ve `ask` kurallı istekte bu seçenek çıkmaz. Terminalde
  (`fusion`, `fusion run`) `k` tuşu; kural yazıldı/yazılamadı bildirimi tur sonunda basılır.
- Reddederken **Not ekle** (masaüstünde Tab, terminalde `h <gerekçe>`) yazdığın gerekçe
  modele araç sonucu olarak gider; tur durmaz, model yolunu gerekçeye göre değiştirir.
  Notsuz ret ise turu durdurur ve "nasıl devam edeyim?" diye sorar. Bilinen sınır: **evet**
  cevabıyla yazılan not modele iletilmez (yalnız ret notu gider); etkiler (`effects`) yolundaki
  onaylarda not gösterilmez.

### Korumalı yollar ve klasör dışı

- `.git/`, `.claude/`, `.fusion/tools/`, `.codex/`, `.cursor/rules/`, `.github/workflows/`
  altına yazan her çağrı (dosya aracı, indirme/arşiv/görsel aracı ya da kabuk komutu) **her
  modda** sorulur ve oturum iznine dönüşmez; okumak serbesttir. Kabukta `cd .git && …` sonrası
  göreli hedefler, `tar -C`, `curl -o`, `unzip -d` de yakalanır; karşılaştırma büyük/küçük harf
  duyarsızdır (`.GIT/config`). Bilinen sınır: `python -c "open('.git/x','w')"` statik olarak
  çözülmez.
- `runtime.block_reads_outside_root` / `runtime.block_writes_outside_root` (Ayarlar › İzinler ›
  Proje klasörü anahtarları): açıkken proje klasörü (+ `--add-dir`) dışını okumak / dışına
  yazmak sorulmadan engellenir; modele dizinin `--add-dir` ile açılabileceği söylenir. Yazma
  engeli kabuk yönlendirmesini de kapsar (`echo x > ~/.zshrc`, `| tee /etc/hosts`); başka kabuk
  komutlarının (`cp a ~/b`) kök dışı yazması engellenmez, Otomatik modda sorulur.
  `restrict_to_root` ikisini birden kapatır.

### Proje güveni masaüstünde

İndirilmiş bir proje kendi `config.yaml`'ı (MCP sunucuları, doğrulama komutları),
`.claude/settings*.json` izin listeleri ya da `.fusion/tools` araçlarıyla geliyorsa sohbetin
üstünde **"Bu klasördeki dosyalara güveniyor musun?"** şeridi çıkar ve neyin devre dışı
kaldığını sayar. **Evet, güven** = `fusion trust`; Ayarlar › İzinler › Proje klasörü'nden güven
kaldırılabilir. Dosyalar sonradan değişirse güven kendiliğinden düşer.

---

## 7a) Kaldığın sohbete dönmek → `--continue`, `--resume`, `/resume`

Fusion her konuşmayı proje köküne göre diske yazar; kapatınca kaybolmaz.

| Yaz | Ne yapar |
|-----|----------|
| `fusion --continue` (`-c`) | Bu projedeki SON sohbeti geçmişiyle açar |
| `fusion --resume <kimlik\|ad>` (`-r`) | Kimliği, adı ya da kimlik önekiyle seçtiğin sohbeti açar |
| `fusion --resume <ad> --fork-session` | Seçilen sohbetin KOPYASINI yeni kimlikle açar; özgün sohbet değişmez |
| `fusion --name "Ödeme akışı"` (`-n`) | Yeni (ya da sürdürülen) sohbete ad verir |
| `/resume` | Bu projedeki sohbet listesini açar; `/resume <kimlik\|ad>` doğrudan geçer |
| `/rename <ad>` | Açık sohbete ad verir (`--resume <ad>` ile bulunur) |
| `/branch [ad]` | Buraya kadarki konuşmayı yeni bir sohbete kopyalar ve oradan sürer |

- Bulunamayan sohbet için Fusion sessizce yeni sohbet AÇMAZ; hata verir ve çıkar.
- `/resumeclaude`, `/resumecodex` başka araçların geçmişini yalnız künye olarak devralır;
  `/resume` ise Fusion'ın kendi konuşmasını olduğu gibi model bağlamına yükler.
- Masaüstü: sohbet listesi (`sohbet.listele`) ve "buradan devam et" (`sohbet.dallan`) aynı
  depoyu kullanır; `sohbet.adlandir` ile verilen ad terminalde de görünür.

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
| `/plan` | Önce planla, değiştirme |
| `/undo` | Son değişikliği geri al |
| `fusion -c` · `/resume` | Kaldığın sohbete dön |
| `/rename <ad>` · `/branch` | Sohbete ad ver · dallandır |
| `/verify` | Test/lint çalıştır |
| `/permissions` · `fusion permissions` | İzin kurallarını (allow/ask/deny) listele, ekle, sil |
| `fusion trust` | Projenin config/izin/araç dosyalarına güven |
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
