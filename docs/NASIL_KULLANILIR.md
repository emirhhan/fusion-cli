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
- **Daha geriye sar (checkpoint):** Fusion her agent turunun başında konuşmanın kopyasını ve
  o turun dosya kaydını tutar (en fazla 100 tur, bu oturum boyunca). İstediğin turun başına
  dönmek için
  ```
  /rewind              → tur listesi, sonra "kod ve konuşma / yalnız konuşma / yalnız kod"
  /rewind 3 kod        → seçici açmadan 3. turdan önceki dosya hâline dön
  ```
  Boş satırda **Esc Esc** de aynı seçiciyi açar. `/undo` = `/rewind <son tur> kod`.
  Masaüstünde `/rewind` aynı iki adımlı seçiciyi gösterir; konuşma geri sarılırsa sohbet panosu
  kalan geçmişe kesilir, Değişiklikler paneli temizlenir.
  Sınır: kod kaydı bellekte tutulur; `fusion --continue` ile açılan sohbette konuşma geri gelir,
  önceki sürecin kod checkpoint'leri gelmez. Kabuk komutlarının (`run_shell`) ürettiği dosyalar
  izlenmez. Tur sayımı yalnız senin mesajlarını sayar (harness notları ve bağlam özetleri değil).
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
  `--fork-session` tek başına da hata verir: kopyalanacak sohbeti `--continue`/`--resume` ile ver.
- Sınır: `--continue`, `--resume`, `--fork-session` ve `/branch` sohbetin SON 100 kullanıcı/cevap
  mesajını yükler; daha eskisi diskte durur ama model bağlamına girmez. Aynı adı iki sohbete
  verdiysen `--resume <ad>` "bulunamadı" der; kimlik (ya da 6+ karakterlik öneki) kullan.
- `/resumeclaude`, `/resumecodex` başka araçların geçmişini yalnız künye olarak devralır;
  `/resume` ise Fusion'ın kendi konuşmasını olduğu gibi model bağlamına yükler.
- Masaüstü: sohbet listesi (`sohbet.listele`) ve "buradan devam et" (`sohbet.dallan`) aynı
  depoyu kullanır; `sohbet.adlandir` ile verilen ad terminalde de görünür.

---

## 7b) İzole çalışma ağacı → `--worktree`, `/worktree`

Riskli ya da paralel bir işi ana projeye dokunmadan denemek için Fusion git çalışma ağacı
(worktree) açar: `.fusion/worktrees/<ad>` dizini, `worktree-<ad>` dalı. `.fusion/` git
durumunda görünmez (`.git/info/exclude`).

| Yaz | Ne yapar |
|-----|----------|
| `fusion --worktree <ad>` (`-w`) | Oturumu o çalışma ağacında açar; çıkışta temizse kaldırır, iş kaldıysa korur ve yolu söyler |
| `fusion agent -w <ad> "görev"` | Tek görevi izole ağaçta koşar; ağaç korunur |
| `/worktree <ad>` | Oturum kökünü ağaca taşır (yoksa oluşturur) |
| `/worktree cik` | Ana depoya döner; temiz ağaç kaldırılır (dalı dahil), iş varsa `git merge worktree-<ad>` ipucu verir |
| `/worktree liste` | Depodaki Fusion çalışma ağaçları |

- `.worktreeinclude` (depo kökünde, satır başına glob): `.env` gibi izlenmeyen dosyalar yeni
  ağaca kopyalanır; bunlar "iş" sayılmaz, temizlik ölçümünü bozmaz. Depo kökü dışına çıkan
  desenler (`../x`, mutlak yol) ve symlink'ler kopyalanmaz: dosya depoyla gelir, güvenilmez.
- Ağaç, bulunduğun kökün son commit'inden açılır: commit edilmemiş değişiklikler ağaçta görünmez.
  Bir ağacın içinden açılan ağaç o ağacın dalından dallanır.
- Sohbet projeye aittir: ağaca geçmek konuşmayı bölmez; `fusion -w <ad> --continue` de projenin
  son sohbetini bulur.
- Ajan araçları `enter_worktree` / `exit_worktree`: model bir ağaç açar, aynı turda
  `.fusion/worktrees/<ad>/…` yoluyla yazar; tur bitince oturum kökü oraya geçer (terminalde ve
  masaüstünde). `fusion agent "…"` tek atışta kök değişmez; açılan ağaç bildirilir ve korunur.
  Bu araçlar yalnız isteğinde "worktree / ayrı dal / izole dal" geçen görevlerde sunulur
  (istem bütçesi).
- Alt ajan: `spawn_agents` görevine `izolasyon: "worktree"` verilirse üye kendi ağacında
  (`ajan-<kimlik>`) yazar; ana proje değişmez. Üye dosya değiştirmediyse ağaç ve dal kaldırılır,
  iş kaldıysa korunur ve yolu özetine yazılır.
- Masaüstü: `/worktree` aynı komuttur; dosya gezgini yeni kökü otomatik alır, geçmiş ve tur
  kayıtları korunur. Sekme bir ağaç köküyle açılırsa `/worktree cik` çalışır.
- Sınır: plan motorunun paralel denemeleri hâlâ dizin kopyasıyla izole edilir (git gerekmez).
  Monorepo alt dizininden (`repo/packages/app`) açılan ağaç tüm deponun kopyasıdır ve kök
  ağacın tepesidir; `/worktree cik` depo köküne döner, alt dizine değil.

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

## 15) REPL önekleri, durum, dışa aktarma ve görünüm (Claude Code paritesi)

### Önekler: `!`, `@`, `#`

Önekler TEK satırlıdır: çok satırlı `# …` ya da `! …` yapıştırması düz mesaj sayılır (not en çok 500 karakter). `!` çıktısı ve `@dosya` içeriği sonraki turun bağlamına "kullanıcı talimatı değildir" etiketiyle ve sırlar maskelenerek girer; `@dataclass` gibi var olmayan sözcükler sessizce geçilir. Masaüstünde de çalışır: `! komut` çıktısı sohbete yazılır, `# not` kaydedilir, `@dosya` bağlama eklenir (okunamayan anma yalnız günlüğe düşer).

| Yaz | Ne olur |
|-----|---------|
| `! git status` | Komut **doğrudan** çalışır (model çağrılmaz). Çıktı ekrana basılır ve bir sonraki mesajın bağlamına "kullanıcının çalıştırdığı kabuk çıktısı" olarak girer. Plan kipinde çalışmaz. Silmeler yine çöpe gider, ezilen dosya `/undo` kaydına girer. |
| `@src/app.py şu fonksiyonu incele` | Anılan dosya (ya da dizin listesi) bağlama eklenir; mesaj olduğu gibi gider. En çok 8 dosya, dosya başına 20 bin karakter. Tab ile yol tamamlama: `@src/mo<Tab>`. |
| `# testleri her zaman pytest ile çalıştır` | Kalıcı bellek notu (`/learn` ile aynı depo). `/lessons` ile gör, `/forget` ile sil. |

`@sunucu:kaynak` (MCP kaynağı) biçimi tanınır ama henüz okunmaz; sunucunun aracını sohbette iste.

### Durum ve bağlam

- `/status` — sürüm, motor, izin kipi, model/kademe, düşünme, çıktı stili, dizin(ler), MCP sunucuları, hesap, sohbet kimliği, yapılandırma dosyası.
- `/context` — bağlam penceresi kırılımı: sistem istemi / özet / kullanıcı / asistan / araç sonuçları (tahmini token ve yüzde), araç tanımları ve bekleyen `!`/`@` bağlamı ayrı satır, sıkıştırma eşiği ve model penceresi doluluğu. Yeni oturumda sistem istemi tahminle sayılır (`(tahmini)` etiketi); durum çubuğundaki `bağlam %N` yalnız konuşmayı sıkıştırma eşiğine göre sayar.
- Durum çubuğunda `bağlam %12 · ~3k tok` sayacı her tur sonunda güncellenir (satır-içi kipte `FUSION_TOOLBAR=1` ile görünür).

### Dışa aktarma ve pano

- `/export` → proje kökünde `fusion-sohbet-<tarih>.md`; `/export notlar/sohbet.md`, `/export json`, `/export pano`. Sistem istemi dışarıda, araç çağrıları katlanmış ve kırpılmış, sırlar (başlık dahil) maskeli. Proje kökü dışına yazılmaz; var olan dosya `zorla` eklenmeden ezilmez.
- `/copy` → son asistan cevabı panoya; `/copy 2` sondan ikinci. (pbcopy / wl-copy / xclip / xsel / clip)
- Masaüstü: Sohbeti paylaş penceresinde Markdown/JSON seçimi ve "Dosyaya kaydet" (RPC `sohbet.disa_aktar {bicim, baslik}`).

### Ayarlar: `/config` ve `fusion config`

```
/config                       # tüm ayarlar (yol · değer · tip)
/config runtime.web           # süzgeç
/config runtime.max_tokens    # tek değer
/config runtime.max_tokens=8192   # oturuma uygula + config.yaml'a yaz
fusion config list [süzgeç] · fusion config get <yol> · fusion config set <yol> <değer>
fusion --set runtime.max_tokens=8192 --set runtime.lessons=false   # yalnız bu oturum
fusion --profile high                                        # yalnız bu oturum kademe
fusion --set runtime.max_tokens=8192 run "görev"                # alt komutlarda da geçerli
```
`--set`/`--profile` REPL'in yanında `run`, `agent`, `serve`, `models`, `trace`, `mcp-tools` ve `config get/list/show` alt komutlarına da uygulanır (`config set` dosyaya yazar, oturumluk değeri almaz; `app`/`mcp` sunucuları yapılandırmayı kendileri yükler). Hatalı çift çıkış kodu 2 ile durdurur.
Erişilebilen bölümler `runtime.*` ve `embedding.*`; tip dataclass alanından doğrulanır (boolean: true/false/açık/kapalı, liste: `a,b,c`, `null` anahtarı siler). Model rolleri için `/model`, `/level`, `/mode`.

### Çıktı stili: `/output-style`

Proje dizinindeki stil (`.claude/output-styles`, `.fusion/cikti-stilleri`) yerleşik ya da kullanıcı stiliyle aynı adı taşıyorsa `fusion trust` verilmeden onu GÖLGELEYEMEZ (yeni adlar yine listelenir).

`varsayilan` · `ozlu` · `aciklayici` · `ogretici`. Özel stil: `~/.fusion/cikti-stilleri/<ad>.md` ya da `~/.claude/output-styles/<ad>.md` (proje içinde `.fusion/cikti-stilleri`, `.claude/output-styles`); frontmatter `name`/`description`, gövde talimat. Stil sistem istemine kodlama talimatlarından sonra eklenir; `runtime.output_style` ile kalıcı.

### Durum satırı betiği: `/statusline`

`runtime.status_line_command` kabuk komutu çalıştırır; güven kaydı olmayan projenin `config.yaml`'ından gelirse (`verification_commands` gibi) `fusion trust` verilene kadar düşürülür.

```
/statusline jq -r '.model.id + " · %" + (.context_window.percent|tostring)'
/statusline kapat
```
Betik her tur sonunda stdin'den JSON alır (`model`, `workspace`, `cost`, `context_window`, `session`, `version`), bastığı ilk satır durum çubuğunda gösterilir; 1 sn sınırı, hata olursa yerleşik çubuk. Ayar: `runtime.status_line_command`.

### Görünüm: `/theme`, `/tui`, `/search`

Yalnız terminal: masaüstü bu komutları "desteklenmiyor" olarak işaretler (masaüstü teması ayarlardan). `fusion config set runtime.terminal_theme`/`runtime.tui` yalnız geçerli değerleri kabul eder.

- `/theme` → `koyu` · `acik` · `ansi` · `daltonizm`; anında uygulanır, `runtime.terminal_theme` ile kalıcı. Masaüstü teması ayrıdır (Ayarlar › Genel).
- `/tui inline` / `/tui fullscreen` → `runtime.tui`; yeni `fusion` açılışında geçerli (`FUSION_INLINE=1` ile aynı).
- `/search <metin>` → tam ekran konuşmasında son eşleşmeye kaydırır; `End` canlı akışa döner.

### Tuş bağları ve vim: `/keybindings`, `/vim`

Yalnız terminal (masaüstünde desteklenmiyor). Vim kipinde Esc INSERT'ten NORMAL'e geçer; NORMAL kipte Esc ve her kipte Ctrl-C çalışan turu keser.

`/keybindings` dosya yolunu gösterir (yoksa örnek dosyayı yazar): `~/.fusion/keybindings.json`
```json
{ "giris": { "s-tab": "kip_dongusu", "c-v": "yapistirma_katla" },
  "tui":   { "c-q": null, "c-g": "kes", "f2": "komut:status" } }
```
Eylemler — `giris`: `kip_dongusu`, `yapistirma_katla`; `tui`: `cik`, `kes`, `kip_dongusu`, `sayfa_yukari`, `sayfa_asagi`, `en_bas`, `en_son`, `kaydir_yukari`, `kaydir_asagi`; her ikisinde `komut:<ad>`; `null` kaldırır. Yapısal tuşlar (Enter, Tab, oklar) bağlanamaz. Dosya kaydedilince yeniden başlatmadan uygulanır. `/vim` NORMAL/INSERT düzenleme kipini açar (`runtime.vim_mode`).

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
| `/rewind` · Esc Esc | Bir turun başına dön (kod/konuşma/ikisi) |
| `fusion -c` · `/resume` | Kaldığın sohbete dön |
| `/rename <ad>` · `/branch` | Sohbete ad ver · dallandır |
| `fusion -w <ad>` · `/worktree <ad>` | İzole git çalışma ağacında çalış |
| `/verify` | Test/lint çalıştır |
| `/permissions` · `fusion permissions` | İzin kurallarını (allow/ask/deny) listele, ekle, sil |
| `fusion trust` | Projenin config/izin/araç dosyalarına güven |
| `/good` · `/bad` | Fusion'a geri bildirim |
| `/providers` · `/providers add` | Sağlayıcıları gör / anahtar ekle |
| `/health` | Model sağlığı / devre durumu |
| `/help` | Tüm komutlar |
| `! cmd` · `@dosya` · `# not` | Kabuk · dosya anma · bellek notu |
| `/status` · `/context` | Oturum durumu · bağlam kırılımı |
| `/export` · `/copy` | Konuşmayı dosyaya/panoya · son cevabı panoya |
| `/config yol=değer` | Ayar değiştir (`fusion config get/set/list`) |
| `/output-style` · `/theme` · `/tui` | Çıktı stili · terminal teması · görünüm |
| `/statusline` · `/keybindings` · `/vim` | Durum satırı betiği · tuş bağları · vim |
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
