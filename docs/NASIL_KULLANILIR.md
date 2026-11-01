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
- **Geri al:** Fusion’ın yazdığı ve sonradan değişmemiş dosyaları geri almak için
  ```
  /undo        → /rewind ile aynı menü (tur, sonra "yalnız kod" seç)
  ```
  Yalnız Fusion’ın yazdığı doğrulanabilen dosyalar otomatik geri alınır. Senin sonradan
  değiştirdiğin dosyalar ve yazarı doğrulanamayan kabuk değişiklikleri korunur; çakışma
  bildirilir, önceki hâlin kaydı bellekte tutulur.
- **Daha geriye sar (checkpoint):** Fusion her agent turunun başında konuşmanın kopyasını ve
  o turun dosya kaydını tutar (en fazla 100 tur, bu oturum boyunca). İstediğin turun başına
  dönmek için
  ```
  /rewind              → tur listesi, sonra "kod ve konuşma / yalnız konuşma / yalnız kod / Vazgeç"
                         (kod seçenekleri yalnız o turdan beri dosya değiştiyse görünür)
  /rewind 3 kod        → seçici açmadan 3. turdan önceki dosya hâline dön
  ```
  Konuşma geri sarılınca (konuşma ya da ikisi) seçilen turun istemi giriş kutusuna geri konur (terminal ve TUI).
  Kapsam menüsünde Claude Code'daki gibi **Buradan itibaren özetle** (seçilen turdan sonrası
  `/compact` sıkıştırıcısıyla özetlenir, turun istemi giriş kutusuna döner) ve **Buraya kadar özetle**
  (öncesi özetlenir, sonrası kalır) da var; Enter ile seçilince isteğe bağlı talimat sorulur
  (`/rewind 3 ozet-buradan <talimat>`), TUI'de numara tuşuyla seçilince talimatsız hemen özetlenir
  (seçicilerde 1-9 tuşları satırı doğrudan seçer). Dosyalar değişmez, özgün mesajlar transcript'te
  kalır; `DISABLE_COMPACT=1` bu seçenekleri gizler. Daha önceki bir özetin ya da `/compact`ın
  içinde kalan tur oradan özetlenemez (açık ileti verilir); "Buraya kadar özetle" sonrasındaki
  turlar yeniden özetlenebilir.
  Aynı oturumda daha önce `/clear` çalıştıysa menünün başında `/resume <kimlik> (önceki oturum)` satırı
  durur (terminal ve TUI; masaüstü sohbetleri sekmelerle sürdürür); seçilince `/clear` öncesi konuşma sürdürülür. Başka bir sohbete
  geçince satır kaybolur.
  Boş satırda **Esc Esc** de aynı seçiciyi açar. Girdi doluyken (tur sürmüyorsa) **Esc Esc** metni temizler; taslak Up ile geri gelir (yalnız bu oturumda, son 10 taslak; geçmiş dosyasına yazılmaz). `/undo` ve `/checkpoint` Claude Code'daki gibi `/rewind` takma adıdır ve aynı menüyü açar.
  Masaüstünde `/rewind` aynı iki adımlı seçiciyi gösterir; konuşma geri sarılırsa sohbet panosu
  kalan geçmişe kesilir, Değişiklikler paneli temizlenir.
  Checkpoint'ler Claude Code'daki gibi konuşmayla birlikte diske yazılır
  (`<bellek>/oturum-durum/<sohbet>.json`, 0600) ve `~/.claude/settings.json` içindeki
  `cleanupPeriodDays` (varsayılan 30) gün saklanır: `--continue`/`--resume`/`/resume` ile
  açılan sohbette `/rewind` önceki sürecin turlarına da çalışır. Kabuk komutlarının (`run_shell`) tüm etkileri
  kaydedilmez; bazı mevcut dosyalar için başlangıç yedeği alınır ve dosya farkı gözlenir.
  Bu gözlem, kabuk değişikliklerinin otomatik geri alınacağı anlamına gelmez. Tur sayımı
  yalnız senin mesajlarını sayar (harness notları ve bağlam özetleri değil).
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
içindeyse arama da yasaklanır/sorulur. `Agent(...)`/`Task(...)` `Agent` aracını ve eski `spawn_agent`,
`spawn_agents` adlarını kapsar (`Agent(Explore)` yalnız o tipi); `Edit/Write(...)` indirme, arşiv açma ve görsel üretme
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

### Kabuk sandbox'ı (`/sandbox`)

`run_shell` komutları isteğe bağlı olarak işletim sistemi sandbox'ında çalışır (macOS
Seatbelt, Linux bubblewrap): yazma proje köküyle sınırlı, `~/.ssh`/`~/.aws` gibi yollar
okunamaz, ağ istenirse yalnız izinli alan adlarına açık. `/sandbox on`, `/sandbox izin
github.com`, `fusion sandbox durum`; masaüstünde **Ayarlar › İzinler › Kabuk sandbox'ı**.
Sandbox dışında çalıştırma isteği her seferinde ayrıca sorulur. Ayrıntı: [SANDBOX.md](SANDBOX.md).

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

### Otomatik kip denetçisi (risk sınıflandırıcısı) — `/auto-mode`

Claude Code'un auto mode sınıflandırıcısının Fusion karşılığı. Otomatik kipte kuralların
**soracağı** bir çağrı (`git push`, proje dışına yazma, `brew install`, uzak sunucu, MCP'de
uzak yazma…) önce küçük/hızlı bir modele sorulur. Model yalnız **senin mesajlarını** ve
eylemi (komut, yol) görür; araç çıktısı, web sayfası ve yazılacak dosya içeriği gönderilmez
(yalnız uzunluğu), sırlar maskelenir:

- "güvenli" derse çağrı **sorulmadan** çalışır; akışta `denetçi (model): güvenli…` satırı kalır.
- "riskli" derse onay kartı açılır; kartta `Denetçi: <gerekçe>` yazar.
- Model yoksa, anahtar kurulu değilse, zaman aşımında ya da cevap bozuksa **kurallar geçerli**
  (eski davranış: sorulur). Üst üste 3 model hatasından sonra oturumun kalanında model çağrılmaz.
- Yıkıcı işlem (`rm -rf`, `git reset --hard`, uzakta silme/harcama), `ask` kuralı, `sudo`,
  sistem ayarı, ortam dökümü (`printenv`), `curl … | sh`, veritabanı silme, satır içi kodla
  silme ve girişli tarayıcı oturumu **hiçbir ayarda** modele bırakılmaz; her zaman sorulur.
- Üst üste **3** ya da oturumda toplam **20** "riskli" model kararında oturum **Manuel**e
  düşer (kalıcı ayar değişmez). Geri dönmek: `/auto-mode devam`, masaüstünde besteci
  çubuğundaki **Otomatik'e dön** ya da izin modundan Otomatik'i yeniden seçmek.
- Alt ajanların çağrıları denetçiye girmez (niyetleri model yazımıdır); kurallar geçerlidir.

Ayar `runtime.auto_classifier` (`/auto-mode ac` ya da `fusion auto-mode ayar ask_only`):
`off` (varsayılan: yalnız kurallar) · `ask_only` (sorulacakları sınıflandır) · `on` (ek olarak
salt okunur olmayan **her** kabuk komutunu da sınıflandır; riskli bulunursa sorulur, yavaşlatır).
Varsayılan kapalıdır: açıkken son 3 mesajın ve eylem denetçi modelinin sağlayıcısına gider ve
onun (ücretsiz) günlük kotasını kullanır; `/auto-mode` ve ayar kartı hangi modele gittiğini yazar.
Model `runtime.auto_classifier_model` (boş = hakem rolü ve yedekleri; web oturumu olamaz),
süre sınırı `runtime.auto_classifier_timeout_s` (12 sn).

```
/auto-mode                 # ayar, model, sayaçlar, son 5 karar
/auto-mode devam           # Manuel'e düşen oturumu Otomatik'e döndür
/auto-mode off|ask_only|on # ayarı kalıcı yaz (kapat | ac | tum de olur)
fusion auto-mode durum
fusion auto-mode ayar off
fusion auto-mode dene "git push origin main" --niyet "değişiklikleri main'e pushla"
```

Masaüstü: izin modu düğmesinin yanında **Denetçi** rozeti (ipucunda model ve engel sayacı),
Ayarlar › İzinler › **Otomatik kip denetçisi** kartı (ayar, son kararlar, Otomatik'e dön). RPC:
`oto.durum`, `oto.ayar {deger}`, `oto.devam`. Olaylar `AutoReviewDecided` ve `AutoModeFellBack`
akışta kalıcı adım olur ve denetim günlüğüne `tur: sınıflandırıcı` etiketiyle yazılır.

### Proje güveni masaüstünde

İndirilmiş bir proje kendi `config.yaml`'ı (MCP sunucuları, doğrulama komutları),
`.claude/settings*.json` izin listeleri ve kanca (hook) komutları ya da `.fusion/tools`
araçlarıyla geliyorsa sohbetin üstünde **"Bu klasördeki dosyalara güveniyor musun?"** şeridi
çıkar ve neyin devre dışı kaldığını sayar. Projede kanca varsa şerit ayrıca uyarır: güvenirsen
o komutlar her araç çağrısında senin yetkinle çalışır (`fusion hooks list` ile gözden geçir;
bkz. [KANCALAR.md](KANCALAR.md)). **Evet, güven** = `fusion trust`; Ayarlar › İzinler › Proje klasörü'nden güven
kaldırılabilir. Dosyalar sonradan değişirse güven kendiliğinden düşer.

---

## 7a) Kaldığın sohbete dönmek → `--continue`, `--resume`, `/resume`

Fusion her konuşmayı proje köküne göre diske yazar; kapatınca kaybolmaz.

| Yaz | Ne yapar |
|-----|----------|
| `fusion --continue` (`-c`) | Bu projedeki SON sohbeti geçmişiyle açar |
| `fusion --resume <kimlik\|ad>` (`-r`) | Kimliği, adı ya da kimlik önekiyle seçtiğin sohbeti açar |
| `fusion --resume <ad> --fork-session` | Seçilen sohbetin KOPYASINI yeni kimlikle açar; özgün sohbet değişmez |
| `fusion "soru"` · `fusion -r <ad> "soru"` · `fusion -c "soru"` | Etkileşimli oturumu açar (ya da sürdürür) ve istemi ilk mesaj olarak gönderir (Claude Code `claude "query"`); ilk sözcük bir alt komut adıysa (`run`, `agent`…) alt komut çalışır |
| `fusion --session-id <uuid>` | Yeni sohbete bu UUID'yi kimlik olarak verir (`session-<hex>` olarak saklanır); kullanılmış kimlik reddedilir; `--continue`/`--resume` ile yalnız `--fork-session` birlikte |
| `fusion --name "Ödeme akışı"` (`-n`) | Yeni (ya da sürdürülen) sohbete ad verir |
| `/resume` (`/continue`) | Bu projedeki sohbet listesini açar; `/resume <kimlik\|ad>` doğrudan geçer |
| `/rename [ad]` | Açık sohbete ad verir (`--resume <ad>` ile bulunur); argümansız ad ilk istemden üretilir |
| `/branch [ad]` | Buraya kadarki konuşmayı yeni bir sohbete kopyalar ve oradan sürer; argümansız dal ilk isteme göre adlandırılır, onay yeni ve özgün kimliği basar |

- Oturum seçicisi Claude Code tuşlarıyla gezilir: Up/Down, J/K, Home/End; tam ekranda `/` ya da
  yazdırılabilir karakter arama kipine geçip listeyi ad/açıklamaya göre süzer, Backspace siler, ilk
  Esc aramadan çıkar, ikincisi seçiciyi kapatır. Henüz yok: Space önizleme, Ctrl+R yeniden adlandırma,
  Ctrl+W/Ctrl+A/Ctrl+B kapsam süzgeçleri ve satır içi seçicide arama.
- Bulunamayan sohbet için Fusion sessizce yeni sohbet AÇMAZ; hata verir ve çıkar.
  `--fork-session` tek başına da hata verir: kopyalanacak sohbeti `--continue`/`--resume` ile ver.
- Sürdürme (`--continue`, `--resume`, `/resume`) Claude Code'daki gibi mesajları,
  araç çağrılarını ve sonuçlarını, compaction özetini ve agent modelini geri yükler. İzin
  kipi sürdürme yoluna bağlıdır: `fusion --continue` ve `fusion --resume <kimlik|tek sohbete
  ait ad>` kayıtlı kipi geri yükler (`bypass` hariç: o kip yalnız açılış bayrağıyla girilir);
  seçiciden seçilen sohbet (argümansız `--resume`, `--from-pr`, belirsiz ad) ve oturum içi
  `/resume` geçerli kipte sürer, yalnız plan kipinde biten sohbet plan kipine döner. Bu süreçte
  zaten açılmış bir sohbete (`/clear` ya da `/resume` ile bıraktığın) `/resume` ile dönersen
  plan kipi de geri gelmez. Kayıtlı durum yoksa ya da
  sohbet sonradan başka yüzeyde (masaüstü) sürdüyse transcript'in SON 100 kullanıcı/cevap
  mesajı yüklenir; `--fork-session` ve `/branch` kopyası da metin geçmişiyle başlar. Aynı adı iki sohbete
  verdiysen `fusion --resume <ad>` Claude Code'daki gibi seçiciyi o adı taşıyan sohbetlerle açar,
  `/resume <ad>` ise hata verir (argümansız `/resume` seçiciyi açar). Ad tam eşleşir (büyük/küçük
  harf duyarlı). `--resume <kimlik>` önce bu projede (ve çalışma ağaçlarında), sonra makinedeki
  öteki projelerde arar; kimlik yalnız tek bir projede bulunursa açılır. Fusion'ın eski büyük/küçük
  duyarsız ad ve 6+ karakterlik kimlik öneki eşleşmesi tam eşleşme yoksa yedek olarak kalır.
  `--resume <mutlak-yol.jsonl>` o transcript dosyasındaki sohbeti açar (Fusion dosyası proje başına
  tek `events.jsonl`'dır; içinde birden çok sohbet varsa seçici açılır). Claude Code'un kendi
  `.jsonl` biçimi okunmaz; onun için `/import history claude`.
- `/import history <kaynak> [oturum]` (ör. `/import history claude`) başka araçların geçmişini yalnız
  künye olarak devralır; `/resume` ise Fusion'ın kendi konuşmasını olduğu gibi model bağlamına yükler.
  Claude Code'da `/resume<kaynak>` komutları yok; Fusion'ın eski `/resumeclaude`, `/resumecodex` adları
  bir sürüm boyunca listede görünmeyen, kullanımdan kalkmış takma ad olarak çalışır ve bir kez uyarır.
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
- Alt ajan: `Agent` çağrısına `isolation: "worktree"` verilirse (ya da tanımda `isolation: worktree` varsa) üye kendi ağacında
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

### Otomatik bellek (düz metin, `/memory`)

Fusion, projeye ve sana dair kalıcı bilgileri kendi yazdığı düz metin dosyada tutar
(Claude Code'un `MEMORY.md` düzeni): `<bellek dizini>/projeler/<proje>/bellek/BELLEK.md`
indeksi + `konular/<konu>.md` dosyaları. İndeksin ilk 200 satırı / 25 KB her turun
bağlamına girer; konu dosyalarını model `memory_read` ile ister, `remember` ile yazar.
Yazılan her satır sır/e-posta maskelenerek kaydedilir; dosyayı istediğin gibi düzenle.

- `/memory` → durum (dosya yolu, satır sayısı, konular) · `/memory on|off` → aç/kapa
  (ayara kalıcı yazılır: `runtime.auto_memory`) · `/memory edit` → `$EDITOR`'da aç ·
  `/memory list` · `/memory <konu>` → konu dosyasını göster ·
  `/memory import claude` → `~/.claude/projects/<proje>/memory` içeriğini al.
- `#` öneki yoktur (Claude Code ile aynı): `# ...` ile başlayan satır olağan istem olarak
  modele gider. Kalıcı not için `/memory edit` kullanılır.
- Dizin: `runtime.auto_memory_dir` (boş = varsayılan). Masaüstü: Ayarlar › Kişiselleştirme ›
  **Otomatik bellek** paneli (Markdown düzenleyici, "bu oturumda ilk N satır yüklendi",
  Claude'dan içe aktar).
- Kapalıyken `remember`/`memory_read` araçları hiç sunulmaz, blok eklenmez. `--no-memory`
  ile çalışan tek atışlık `fusion agent` de bu belleği kullanmaz.

### Alt ajan tanımları (`.claude/agents/<ad>.md`)

Fusion, Claude Code'un ajan dosyalarını olduğu gibi okur (`~/.claude/agents`, proje
`.claude/agents`, `~/.codex/agents`) ve frontmatter'daki ayarları alt ajana uygular.
Öncelik Claude Code'daki gibi yönetilen > `--agents` > proje (çalışma dizinine en yakın) >
kullanıcı; Codex (`~/.codex/agents`), `fusion yetenek kur` repoları ve yerleşik roller bunların
ALTINDADIR: aynı ad hiçbir zaman belirsizlik üretmez, önce gelen tanım kazanır.
Claude Code ile birebir katalog için `config.yaml` › `agent_launch.extra_agent_sources: false`
bu ek kaynakları tümden kapatır: Codex (`.md` ve `.toml`) ve kurulu repo ajanları taranmaz,
yerleşik rosterdan yalnız Claude'un yerleşikleri (`general-purpose`, `Explore`, `Plan`,
`statusline-setup`, `claude-code-guide`) kalır.
Claude Code'daki gibi şu dosyalar sessizce atlanır (yalnız hata ayıklama günlüğüne düşer):
`name` yok (dosya belge sayılır), açılış `---` ilk satırda değil, `name` `-` ile başlıyor,
`:` içeriyor ya da 256 karakteri aşıyor, `description` yok. Kimlik dosya adından değil `name`
alanından gelir. Kullanıcı, proje, yönetilen ve `--add-dir` ajan dosyaları izlenir: düzenlenen
ya da eklenen dosya yeniden başlatmadan bir sonraki turda etkin olur.

| Alan (İngilizce / Türkçe) | Fusion'da ne olur |
|---|---|
| `tools`, `disallowedTools` / `yasak_araclar` | Araç kümesi yalnız DARALIR; `mcp__sunucu__arac` ve `mcp__sunucu` (tüm araçları) tanınır; `Agent`, `Skill`, `AskUserQuestion`, `NotebookEdit`, `TodoWrite` eşlenir; tanınmayan ad günlüğe uyarı düşer. `tools` girdilerinin hiçbiri eşleşmezse Agent ajanı başlatmaz, `Agent would be spawned with zero tools` hatasıyla girdileri sayar. Her alt ajandan `AskUserQuestion` (`ask_user`), `ScheduleWakeup` ve `Workflow` (`workflow_run`) alınır; derinlik sınırındaki ajandan `Agent` da alınır |
| `model` | Claude Code sırası: çağrıdaki `model` > tanımdaki `model` > `CLAUDE_CODE_SUBAGENT_MODEL` > ana model (`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` ortam modelini zorlar). `inherit` ana modeldir; `sonnet`/`opus`/`haiku`/`fable` ana model aynı ailedeyse ana modelin kendisi, değilse `agent_launch.model_aliases` / `ANTHROPIC_DEFAULT_<AİLE>_MODEL` ya da aday modellerdeki aynı aileden model; çözülemezse alt ajan açık hatayla başlamaz. Tam kimlik (`claude-opus-5-5` ya da `<sağlayıcı>/<model>`) kabul edilir |
| `permissionMode` / `izin_kipi` | Claude Code kuralları: ana oturum `bypassPermissions`, `acceptEdits` ya da `auto` ise alt ajan o kipte koşar (alan yok sayılır); `plan` ise plan kipinde kalır; `default`/`dontAsk` ise tanımdaki kip uygulanır (`bypassPermissions` ve kullanılamayan `auto` hariç, o zaman ana kip korunur). Değerler: `default`, `acceptEdits`, `auto`, `dontAsk`, `bypassPermissions`, `plan`, `manual` (= `default`). Eklenti ajanlarında alan yok sayılır |
| `maxTurns` / `en_fazla_tur` | Alt ajanın adım tavanı, olduğu gibi uygulanır (yalnız `runtime.agent_max_steps` aşılmaz). Sınıra ulaşan alt ajanın sonucu `[Kısmi çıktı…]` ile başlar, Agent alındısında `status: partial` döner ve `SendMessage` ile sürdürülebilir |
| `skills` / `beceriler` | Başlangıçta TAM içeriğiyle yüklenen beceriler (kırpma ve adet sınırı yok) |
| `mcpServers` | Ad listesi yapılandırmadaki sunuculardan yalnız bunları açar; satır içi sunucu tanımı yalnız bu ajanın koşusu için bağlanır ve ajan bitince kapatılır. Yapılandırmada olmayan ad günlüğe uyarı düşer |
| `effort` / `efor` | `low` · `medium` · `high`: yalnız o alt ajanın düşünme yoğunluğu |
| `memory` / `bellek` | `user` · `project` · `local`: ajana özel kalıcı bellek (bkz. aşağı) |
| `background` | `true` ise ajan beklenmesi istense de arka planda kalır (ana konuşmadan açılan alt ajan zaten varsayılan olarak arka planda başlar) |
| `isolation` | `worktree`: ajan geçici bir git çalışma ağacında koşar |
| `hooks` | `PreToolUse`, `PostToolUse`, `Stop` (alt ajanda `SubagentStop` olur) yalnız o ajan etkinken çalışır; proje ajanında klasör güveni gerekir, eklenti ajanında yok sayılır. Desteklenmeyen kanca alanı varsa ajan başlatılmaz (sessizce atlanmaz) |
| `initialPrompt` | Ajan `--agent` ya da `agent` ayarıyla ana oturum ajanıysa ilk kullanıcı turu olarak kendiliğinden gönderilir |
| `omitClaudeMd` | `true` ise alt ajan CLAUDE.md / proje talimatı olmadan başlar |
| `color` | Claude Code değerleri: `red`, `blue`, `green`, `yellow`, `purple`, `orange`, `pink`, `cyan` (eski Türkçe `renk` adları bir sürüm okunur); tanınmayan değer uyarıyla düşer, ajan gri görünür |
| `autoCompactWindow` | `100000`-`1000000` belirteç: yalnız bu alt ajanın otomatik özetleme penceresini düşürür; aralık dışı değer uyarıyla yok sayılır |
| `experimental.cacheTtl` | `5m` ya da `1h`: o ajanın (alt ajan ya da `--agent` ana ajanı) Claude model isteklerinde sistem istemi bu süreyle istem önbelleğine işaretlenir (`cache_control`); Claude dışı modelde etkisizdir |

Alt ajan bir izin isterse terminal, masaüstü kartı ve Telegram bildirimi
"Alt ajan izin istiyor: Denetçi (denetci-3f9a1c)" diye kimin istediğini söyler. Masaüstü:
Beceriler › Ajanlar › ayrıntı panelinde tanımdaki ayarlar listelenir.

### Alt ajan belleği (`memory: user | project | local`)

Tanımında `memory` alanı olan ajan, oturumlar arasında kendi `MEMORY.md` + `konular/`
dizinini tutar ve her çalışmasında ilk 200 satırı istemine alır. Claude Code'daki gibi Read,
Write ve Edit kısıtlı araç kümesinde de kendiliğinden açılır ve bellek dizini (kök dışındaki
`user` kapsamı dahil) dosya araçlarına erişilir olur; istemdeki blok dizin yolunu gösterir.
`remember`/`memory_read` aynı dosyalara giden kısayol olarak kalır. `disallowedTools`'ta
yasaklanan açılmaz; salt-okur görevde yalnız okuma araçları kalır; Write/Edit olağan onay
kurallarına tabidir. Projenin otomatik belleğini devralmaz.
Bellek yazmaları sınır dizinin (proje kökü ya da bellek dizini) dışına çıkamaz: depodan gelen
sembolik bağ izlenmez, yazma reddedilir.

| Kapsam | Dizin |
|---|---|
| `user` | `~/.claude/agent-memory/<ad>/` (her projede aynı; Claude Code ile ortak) |
| `project` | `<proje>/.claude/agent-memory/<ad>/` (depoya girer, ekiple paylaşılır) |
| `local` | `<proje>/.claude/agent-memory-local/<ad>/` (otomatik `.gitignore`, git dışı) |

Eski Fusion yerleri (`<bellek>/ajan-bellek`, `.fusion/ajan-bellek`, `.fusion/ajan-bellek-yerel`,
indeks `BELLEK.md`) bu sürüm boyunca okunur: yeni dizin yoksa düzenli dosyalar ilk açılışta bir
kez kopyalanır (sembolik bağ izlenmez), eski kayıt silinmez.

- `/memory ajan <ad>` → kapsam, yol, satır sayısı, konular ve indeks metni ·
  `/memory ajan <ad> sil` → belleği sıfırla. Claude Code'daki gibi ajan belleği otomatik
  belleğin parçasıdır: `runtime.auto_memory: false` iken `memory` alanı etkisizdir (alt ajan
  bellek talimatı ve bellek araçları olmadan başlar).
- Masaüstü: Beceriler › Ajanlar › ayrıntı › **Kalıcı bellek** bölümü (metin + "Belleği sil" →
  "Evet, sil / Vazgeç" onayı; silme geri alınamaz).
- RPC: `yetenek.detay` yanıtında `bellek`, silme için `yetenek.bellek_sil {ad}`.
- **Kişiye özel dersler:** `memory` alanlı ajanın turundan çıkan dersler `ajan:<ad>` etiketi
  alır ve `recall_lessons` ile yalnız o ajana döner; ana ajan ve diğer ajanlar görmez. Projeye
  özel ajan dersi (çalışma alanı etiketli) başka projede yalnız ajan adı ortak diye geri
  gelmez. `memory` alanı olmayan ajanların dersleri eskisi gibi ortak havuza yazılır.

### Oturumu bir ajan kişiliğiyle açmak (`--agent`, `/persona`)

Claude Code'un `claude --agent <ad>` karşılığı: oturumun ana iş parçacığı o ajanın araç
kısıtlarını VE modelini alır. Gövde doluysa varsayılan sistem isteminin TAMAMININ yerine geçer
(`--system-prompt` gibi); proje talimatları (CLAUDE.md/FUSION.md) olağan mesaj akışıyla yine
yüklenir. `tools`/`disallowedTools` araçları daraltır, `tools: Agent(a, b)` ana ajanın
açabileceği alt ajan tiplerini sınırlar. Tanımdaki `mcpServers`, `hooks` ve `effort` ana oturuma
bağlanır; `initialPrompt` ilk kullanıcı turu olarak kendiliğinden gönderilir. Ayarlar seçimde
bir kez uygulanır: sonradan `/model` ile yaptığın seçim ezilmez.

Yerleşik ajanlar Claude Code'daki adlarla: **`Explore`** (salt okur hızlı keşif; Write/Edit
yok, Bash izin kurallarına tabi; görevde derinlik `quick`, `medium` ya da `very thorough`
yazılır), **`Plan`** (salt okur plan araştırması), **`general-purpose`** ve **`claude`** (alt
ajanlara açık tüm araçlar), **`statusline-setup`** (Sonnet) ve **`claude-code-guide`** (Haiku).
Claude ailesi yapılandırılmamış sağlayıcıda son ikisi ana modelle koşar. Eski küçük harfli `explore`/`plan` ve Türkçe
roller (`kodcu`, `mimar`...) takma ad olarak çalışmaya devam eder. Kendi
`.claude/agents/<ad>.md` tanımların da kullanılabilir; aynı adlı (ör. `Explore`) tanım
yerleşiği ezer. `CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS=1` yalnız yerleşik `Explore` ve
`Plan`'ı kaldırır. Etkileşimsiz kipte (`fusion agent "…"`) `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`
bütün yerleşik ajanları kaldırır, yalnız kendi tanımların kalır; etkileşimli oturum bu
değişkeni Claude Code'daki gibi okumaz.

- `fusion --agent Explore` → REPL o ajanla açılır (ad yoksa açılmaz, hata verir) ·
  `fusion agent "şunu bul" --agent Explore` → tek atış.
- Proje varsayılanı: `.claude/settings.json` içinde `{"agent": "kod-denetci"}`; `--agent`
  bayrağı ayarı ezer.
- Seçilen ajan sohbete bağlanır (`<bellek>/oturum-ajan/<sohbet>.json`): `fusion --resume` /
  `/resume` sohbeti araç kısıtları ve modeliyle aynı ajanla açar; ajan artık yoksa uyarı verip
  varsayılan araçlarla devam eder. Karşılama kutusunda ajan `@<ad>` olarak görünür. Masaüstünde
  sohbet değiştirince o sohbetin ajanı geri gelir; kaydı olmayan sohbet `agent` ayarıyla açılır.
- Oturumluk tanım: `fusion --agents '{"denetci": {"description": "Kodu inceler", "prompt": "..."}}'`
  (dosya yazılmaz, en fazla 128 KiB). Aynı ad için öncelik: yönetilen (`agent_launch.managed_agent_roots`)
  > `--agents` > proje `.claude/agents` (çalışma dizinine en yakın) > `~/.claude/agents` > eklenti;
  dizinler alt klasörleriyle taranır.
- `/persona` → durum · `/persona Plan` → seç · `/persona off` → kapat (`/kisilik` eş anlamlı).
  **Kullanımdan kalkıyor:** Claude Code'da oturum ortasında ajan değiştiren komut yoktur;
  `/persona` bu sürüm boyunca çalışır, oturumda ilk kullanımda bir kez uyarır. Ajanı oturum
  başında `--agent` ya da `agent` ayarıyla seç. Masaüstündeki ajan seçicisi de yalnız boş
  sohbette değişir; konuşma başlayınca kilitlenir, başka ajan için yeni sohbet açılır.
- Masaüstü: mesaj kutusunun altındaki **Kişilik** seçici (etkin ajanlar listelenir);
  RPC: `oturum.baslat {kisilik: "<ad>" | ""}`, `oturum.durum.kisilik → {ad, unvan} | null`.

### Alt ajan aracı: `Agent` ve `SendMessage`

Model alt ajanı tek bir **`Agent`** aracıyla açar (`subagent_type`, `prompt`, `description`,
`model`, `name`, `isolation`, `effort`, `run_in_background`); çağrıdaki `effort` tanımdaki
`effort` alanını o koşu için ezer. Eski Türkçe alanlar (`uzman`, `salt_okunur`, `yazma_alani`,
`baglam_miras`, `izolasyon`, `arka_plan`) şemada gösterilmez, gelen çağrıda okunmaya devam eder. Ana konuşmadan açılan alt ajan, ayar yoksa
ARKA PLANDA başlar; sonucu bittiğinde sonraki tura bildirim olarak gelir. Biten alt ajanın
kimliği (`agentId`) döner ve `SendMessage(to=<kimlik|ad>)` ile bilinen geçmişiyle sürdürülür;
`Explore` ve `Plan` tek atışlıktır, kimlik dönmez. `ListAgents` ve `TaskStop` arka plan
ajanlarını listeler/durdurur. Eski `Task`, `spawn_agent`, `spawn_agents` ve `invoke_subagent`
adları kullanımdan kalktı: adıyla çağrılırsa çalışır, modele sunulmaz.

- `permissions.deny` içine `Agent(Explore)` yazmak o tipi kapatır (eski adlara da uygulanır).
- `@agent-<ad>` ya da `@"<ad> (agent)"` yazmak o alt ajanın o turda kesin çalışmasını ister
  (görev metnini model yazar); eklenti ajanında `@agent-<eklenti>:<ad>`. Terminal REPL ve
  masaüstü mesajında çalışır. `@` yazınca Claude Code'daki gibi etkin ajanlar `@agent-<ad>`
  olarak önerilir (REPL/TUI Tab tamamlaması ve masaüstü `@` listesi).
- `SendMessage`'i olan fork olmayan alt ajanın başlangıç bağlamına `main` ve oturumdaki adlı
  (`name` verilmiş) ajanların listesi girer; başlangıç anının görüntüsüdür.
- İç içe alt ajan: varsayılan ana konuşmanın altında 3 kat (`runtime.max_agent_depth`,
  `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; `1` iç içeyi kapatır). Aynı anda en çok 20 alt ajan
  çalışır (`runtime.max_parallel_agents`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`); sınırda yeni
  çağrı `Concurrent subagent limit reached` döner. Derinlik adım bütçesini yarılamaz, turda
  toplam alt ajan sınırı yoktur (`runtime.max_subagents_per_turn: 0`; iş akışları kendi
  tavanını kullanır).
- Ön planda beklenen bir alt ajan varken tam ekranda **Ctrl+B** Claude Code'daki gibi o alt
  ajanı kesmeden arka plana alır: tur beklemeden sürer, sonuç bitince bildirim olarak gelir.
  Bekleyen alt ajan yoksa Ctrl+B eskisi gibi süren turu arka plan görevine taşır.
- `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` arka planı kapatır (Ctrl+B de hiçbir şeyi taşımaz); `CLAUDE_CODE_FORK_SUBAGENT=0`
  fork kipini kapatır (varsayılan açık).

### Fork alt ajan: `/subtask`, `baglam_miras`, `context: fork`

Olağan alt ajan temiz bağlamla başlar. **Fork** alt ajan bu konuşmanın o ana kadarki
mesajlarının TAMAMINI devralır (Claude Code'daki gibi kırpma yok; ana oturumun sistem istemi
aynen kullanılır, yalnız o an cevapsız araç çağrısı düşer), kendi bütçesiyle izole koşar ve sohbete yalnız özeti eklenir — uzun bir
ara işi ana bağlamı şişirmeden yürütmek için.

- `/subtask testleri koştur ve raporla` → tur fork alt ajanda koşar (`/altgorev` eş anlamlı);
  masaüstünde de aynı komut (slash menüsü) çalışır; ayrıca yazı kutusunda bir istem varken
  gönder düğmesinin yanındaki **Alt görev** düğmesi taslağı `/subtask` ile gönderir.
- Model kendi kararıyla: `Agent(subagent_type="fork", prompt=…)` (eski `baglam_miras=true` da okunur).
- Beceri tanımında `context: fork` varsa (`SKILL.md` frontmatter) o beceri seçilen tur
  otomatik fork alt ajanda koşar; masaüstü katalogda seçince bildirim "tur bağlamı devralan
  alt ajanda koşacak" der (RPC `yetenek.kullan` yanıtında `fork: true`).
- Fork turuna oturum kişiliğinin notu ve araç kısıtı (yalnız daraltır), seçilen becerinin
  metni, kip istemi, görsel ekler ve adım tavanı aynen geçer; alt ajan bunların üstüne kendi
  `FORK_BRIEF` açıklamasını alır. Plan kipinde fork salt-okur koşar. Canlı geçmişin sonundaki
  cevapsız araç çağrısı (o an çalışan `Agent`) devredilmez.

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

**Hangi rotalar var?** Santral üç API ailesini konuşur; hepsi aynı profil/model çözümünü,
önbelleği, sır maskesini ve telemetriyi paylaşır:

| Rota | Kim kullanır | Not |
|------|--------------|-----|
| `POST /v1/chat/completions` | OpenAI-uyumlu araçlar (Cursor, Cline, Kits) | akış ve araç çağrısı |
| `POST /v1/responses` | Codex CLI, yeni OpenAI SDK'ları (`OPENAI_BASE_URL`) | `input`/`instructions`, `response.*` akış olayları |
| `POST /v1/messages` | Claude SDK'ları, Claude Code (`ANTHROPIC_BASE_URL=http://127.0.0.1:8787`) | `system`, `tools[].input_schema`, Anthropic SSE olayları |
| `POST /v1/messages/count_tokens` | Claude Code bağlam ölçümü | kaba tahmin (~4 karakter = 1 token) |
| `POST /v1/embeddings` | gömme isteyen araçlar | `embedding.provider` (nim ya da yerel ONNX); kurulu değilse 501 |
| `GET /v1/models` | model listesi | profiller + yapılandırılmış modeller |

Ağdan (loopback dışı) gelen istemci `fusion serve --token` belirtecini `Authorization: Bearer`
**ya da** `x-api-key` başlığıyla verir; Anthropic SDK'larında `ANTHROPIC_API_KEY=<belirteç>`
yeter. Başarısız sağlayıcı her rotada 502 ve maskeli hata metniyle döner; `/v1/responses`
yalnız `function` araçlarını çevirir, `developer` rolü sistem mesajı sayılır.

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
fusion mcp tools          # eski ad: fusion mcp-tools
```
Bundan sonra ajan turlarında bu dış aletler otomatik kullanılabilir (onayınla).

**Komut satırından yönetmek** (`fusion mcp …`, Claude Code `claude mcp …` ile aynı kalıp):
```
fusion mcp add github npx -- -y @modelcontextprotocol/server-github     # stdio, kullanıcı kapsamı
fusion mcp add linear --transport http --url https://mcp.linear.app/mcp  # uzak sunucu (OAuth)
fusion mcp add postgres --scope project npx -- -y server-postgres        # projeye (.mcp.json)
fusion mcp add-json fetch '{"command":"uvx","args":["mcp-server-fetch"]}'
fusion mcp list                      # kapsam ve taşımayla; sırlar maskeli
fusion mcp remove <ad>               # kayıtlı olduğu dosyadan siler
fusion mcp login <ad>                # OAuth girişi (tarayıcı açılır), token şifreli depoda
fusion mcp reconnect <ad>|all        # bağlantıyı düşür ve yeniden kur
```
- `--scope user` (varsayılan) kaydı `config.yaml`'a, `--scope project` kök dizindeki
  `.mcp.json` dosyasına yazar. `.mcp.json` **Claude Code ile aynı biçimdir**: depoda zaten
  varsa Fusion onu okur. Proje dosyası süreç başlatabildiği için yalnız `fusion trust` ile
  güvenilen (ya da Fusion'ın kendi yazdığı) `.mcp.json` yüklenir; aynı adda proje kaydı
  kullanıcı kaydını geçer (kullanıcı kaydı `config.yaml`'da durur, silinmez). Güvenilmeyen bir
  `.mcp.json` üzerine `--scope project` ile yazılmaz: önce `fusion trust`. Ekleme/silme
  dosyada yalnız ilgili adı değiştirir; takımın diğer girdileri korunur. `--token-env` proje
  kapsamında yoktur (dosya biçimi taşımaz); kullanıcı kapsamına yaz.
- Komut, argüman, adres ve `env` değerlerinde `${DEĞİŞKEN}` ve `${DEĞİŞKEN:-varsayılan}`
  başvuruları tanınır; bağlantı kurulurken ortamdan çözülür, dosyaya çözülmüş hâli yazılmaz.
- `--env AD` sır adıdır (değer şifreli depodan/ortamdan gelir), `--env AD=değer` sır olmayan
  düz değerdir.
- Sohbet içinde: `/mcp`, `/mcp add …`, `/mcp remove <ad>`, `/mcp reconnect <ad>|all`.
  Masaüstünde Bağlantılar ekranı aynı kayıtları gösterir; proje kaydı "proje" rozetiyle.

**MCP istemleri ve kaynakları** (Claude Code ile aynı yazım):
```
fusion mcp prompts                    # sunucuların istemleri: /mcp__<sunucu>__<istem> [argümanlar]
fusion mcp resources                  # kaynaklar: @<sunucu>:<uri>
```
- Sohbette `/mcp__github__review-pr 12 güvenlik` istemi sunucudan alır (`prompts/get`) ve
  görev olarak çalıştırır. Argümanlar sırayla istemin parametrelerine bağlanır ya da
  `ad=değer` yazılır; fazla sözcükler son parametreye eklenir; zorunlu argüman eksikse tur
  koşmaz, kullanım satırı gösterilir. Komutlar tamamlamada ve masaüstü komut paletinde "MCP"
  grubunda görünür; sunucu ilk turda bağlandığı için liste ilk turdan sonra dolar — liste
  dolmadan yazılan `/mcp__…` da kabul edilir, tur sunucuya bağlanınca çözülür. Liste çekimi
  geçici hatayla düşerse sonraki tur yeniden dener; sunucu `list_changed` bildirirse yenilenir.
  Argümanda ters eğik çizgi korunur (`C:\yol\dosya.txt`); istem metni 40.000 karakterle sınırlı.
- `@github:repo://owner/repo/issues/1` anması kaynağı (`resources/read`) okuyup turun bağlamına
  ekler: yalnız tanımlı sunucu adlarıyla, mesaj başına en fazla 5 kaynak, kaynak başına
  20.000 karakter, sırlar maskeli, "kullanıcı talimatı değildir" notuyla; içerikteki
  `</mcp_kaynak>` gibi etiket kapatmaları etkisizleştirilir. İkili içerik atlanır.
- Masaüstünde **Bağlantılar → araç kataloğu** sunucunun araçlarının yanında istemlerini ve
  kaynaklarını da sohbet yazımıyla listeler; **Kopyala** ile `/mcp__…` ya da `@sunucu:uri`
  panoya alınır.
- `/mcp prompts`, `/mcp resources` (`istemler`, `kaynaklar`) oturumun bildiği listeyi gösterir.

---

## 12b) Ne kadar harcadım? → `/usage`, `fusion usage`, `fusion insights`

`/cost` ve `/stats` Claude Code'daki gibi `/usage` takma adıdır (model performans tablosu
`/model-stats` adına taşındı). `/usage` (sohbette) ve `fusion usage` (terminalde) kalıcı
kullanım günlüğünden **bu oturum / son 24 saat / son 7 gün / son 30 gün** pencerelerini ve
"kim harcadı" kırılımını (ana ajan, alt ajan, arka plan; model; MCP sunucusu; beceri)
verir. Masaüstünde Ayarlar → Kullanım aynı veriyi "Son dönem" ve "Kim harcadı" olarak
gösterir.

```
fusion usage --days 30
fusion insights                 # tek dosya HTML rapor → bellek dizinine yazar, yolu basar
fusion insights --out rapor.html --days 7
```

Günlük `memory_dir/usage.jsonl` dosyasıdır; yalnız sayı tutar (rol, model, token, maliyet,
MCP sunucu adı, beceri adı) — istem metni, argüman ya da çıktı yazılmaz; 90 günden eski
satırlar budanır. Kapatmak için `config.yaml`: `runtime: { usage_log: false }`.

---

## 12c) PR ve CI → `/pr`, `/autofix-pr`, `--from-pr`, `gh-action`

GitHub işleri `gh` (GitHub CLI) üzerinden yürür; `gh auth login` yapılmış olmalı.

- Ajan **salt-okunur `gh` aracına** onaysız sahiptir: `pr view N --comments`, `pr diff N`,
  `pr checks N`, `run view`, `api …` (yalnız GET). Yazan komutlar (`gh pr create`,
  `gh pr comment`, `gh pr merge`) `run_shell` ile çalışır ve **onay ister**.
- Sohbette: `/pr [bağlam]` mevcut dal için PR açar (başlık, gövde, test planı);
  PR yorumları için komut yoktur (Claude Code v2.1.91'de `/pr-comments` kaldırıldı):
  "42 numaralı PR'ın yorumlarını özetle" diye doğrudan sorulur;
  `/autofix-pr [no]` başarısız CI ve yorumları düzeltip push eder ve PR'a bildirir.
- Terminalde: `fusion --from-pr 42` (ya da GitHub/GitLab/Bitbucket PR adresi) Claude Code'daki
  gibi oturum seçicisini o PR'a bağlı sohbetlerle süzerek açar; sohbet, PR açtığında ya da PR
  adresi geçtiğinde PR'a bağlanır. `fusion agent --from-pr 42 "yorumları uygula"` (Fusion eki,
  headless alt komut) görevin başına PR özetini (başlık, dallar, açıklama, adres) ekler.
- CI: `fusion gh-action kur` depoya `.github/workflows/fusion.yml` yazar; bir issue ya da
  PR yorumuna `@fusion <görev>` yazıldığında Fusion headless çalışır (`--bare`, bütçe ve tur
  tavanlı) ve sonucu yoruma yazar. Depo sırrı: `FUSION_PROVIDER_KEY`.
- **Oturumun PR'a bağlanması:** turda başarılı bir `gh pr create` (yoksa `gh pr view/checks`)
  çıktısındaki PR adresi oturumun PR künyesi olur: REPL durum satırında `PR #42`, masaüstünde
  sohbet şeridinde **PR #42 · sahip/depo** rozeti (tıklayınca tarayıcıda açılır;
  `oturum.durum.pr`). Sonraki PR'sız turlar bağı silmez.
- **Kanıt kapısı:** cevap "PR'ı açtım / pull request oluşturuldu / opened a PR" diyorsa turda
  başarılı bir `gh pr create` çıktısı (PR adresi) olmalı; yoksa cevabın sonuna "PR açılmamış
  olabilir, `gh pr status` ile doğrula" notu eklenir. "PR'a yorum yazdım" beyanı da
  `gh pr comment` kanıtı ister. Başlık/gövde model işidir, bu yüzden PR açma ayrı bir
  deterministik iş akışı değil `run_shell` + onay yoludur; kapı yalnız beyanı doğrular.

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

## 15) Önizleme paneli: launch.json, konsol/ağ günlüğü, cihaz boyutları

Masaüstünde sağ paneldeki **Önizleme › Web** sekmesi yerel (localhost) sitenizi gömer.
Ajan `start_preview` ile projeyi çalıştırınca panel kendiliğinden açılır; aşağıdakiler
onun üstüne gelir.

**Dev sunucuyu uygulamadan başlatma** — proje köküne `.fusion/launch.json` koyun
(Claude Code'un `.claude/launch.json` dosyası da aynı alanlarla okunur, yazılmaz):

```json
{
  "version": "0.0.1",
  "configurations": [
    { "name": "web", "runtimeExecutable": "npm", "runtimeArgs": ["run", "dev"], "port": 5173 },
    { "name": "api", "url": "http://localhost:8000" }
  ]
}
```

- `runtimeExecutable` + `runtimeArgs`: komut kabuksuz çalıştırılır, `PORT` ortam değişkeni verilir.
- **`autoPort`:** port başka bir süreçte açıksa alan yoksa ya da `true` ise sıradaki boş port
  seçilir (panelde ve ajan sonucunda "5173 portu doluydu; 5174 portunda başlatıldı" notu);
  `false` ise sunucu başlatılmaz, hata söylenir. Seçilen port `PORT` ile verilir ve
  `runtimeArgs` içindeki `${port}` onunla değişir — `PORT` okumayan sunucular için
  (Vite): `"runtimeArgs": ["run", "dev", "--", "--port", "${port}"]`.
- Yalnız `url`: hiçbir şey başlatılmaz, çalışan sunucuya bağlanılır. Adresler yerel olmalıdır
  (`http://` ya da `https://` + localhost/127.0.0.1/[::1]).
- İsteğe bağlı `cwd` (köke göreli, kök dışına çözülemez) ve `env` (`{"AD": "değer"}`).
  Sunucular uygulama kapanınca kapatılır.
- **Güven:** komutlu yapılandırma yalnız dosya güvenilirse çalışır — indirilmiş bir deponun
  `launch.json`'u onaysız komut çalıştıramaz. Onay: terminalde `fusion trust` (config.yaml,
  `.fusion/tools` ve `.claude/settings.local.json` ile aynı kayıt) ya da panelde komut metnini
  görüp **Güven ve başlat**. Dosya değişirse güven düşer. Yalnız `url` ile bağlanma onay istemez.
- Komuta giden ortamdan sağlayıcı anahtarları ve sırlar (`*_API_KEY`, `*_TOKEN`, `*PASSWORD*`…)
  çıkarılır; sunucunun gerçekten gerektirdiği değeri `env` ile açıkça verin.
- Geçersiz tek kayıt dosyayı düşürmez: atlanır ve uyarı olarak görünür (panel, `/onizleme`,
  ajan ipucu). Desteklenmeyen alanlar (`program` vb.) yok sayılır ve uyarı verir. Adlarda iç
  boşluk serbesttir (`"Web Server"`).
- Panelde adres çubuğunun altında yapılandırma seçici ve **Başlat / Durdur** görünür.
- Ajan: `start_preview(name="web", page="/shop/")` (`page` yalnız yol olabilir). CLI: `/onizleme`
  listeler, `/onizleme web` ajana başlattırır, `/onizleme durdur web` anında durdurur.
- Aynı yapılandırmanın eşzamanlı iki başlatması (panel + ajan) tek süreç açar; ikincisi
  birincinin adresini alır.

**Konsol ve ağ günlüğü** — araç çubuğundaki `≡` düğmesi sayfayı çekirdeğin başsız
tarayıcısında (Playwright) açıp konsol mesajlarını (seviye, metin, betik:satır) ve ağ
isteklerini (durum, yöntem, adres, tür; başarısızlar başta) listeler. Canlı akış değil, o
anın fotoğrafıdır; **↻** yeniden ölçer, "Yalnız sorunlar" süzer. Ajan için aynı veri
`preview_console` ve `preview_network` araçlarında (`url` verilmezse son önizleme).

**Ekran görüntüsü** — `◧` düğmesi seçili cihaz boyutunda görüntü alır, sistem/açık/koyu tema
taklidi seçilebilir; dosya `.fusion/onizleme-ekran.png` olarak proje içine yazılır (sembolik
bağ ya da kök dışı hedefe yazılmaz). Aynı anda tek yakalama yapılır; hızlı boyut geçişleri
kısa beklemeyle birleştirilir. Ajan için aynı şey `preview_screenshot(url?, width, height,
color_scheme, full_page)` aracıdır: görüntü modele döner ve aynı dosyaya yazılır.

Günlük ve ekran görüntüsü tarayıcısı yalnız yerel adreslere çıkar: sayfanın dış adrese
yönlendirmesi ve dış alt istekleri engellenir, engellenen adres hata metninde söylenir.
Chromium indirilmemişse mesaj `playwright install chromium` adımını gösterir.

**Cihaz boyutları** — Masaüstü, 1440, 1024, Tablet (768), Mobil (375), Mobil (320).
Seçim iframe genişliğini ve ekran görüntüsü ölçüsünü birlikte belirler.

**Yerel https** — `https://localhost:8443` gibi yerel https adresleri de gömülür (mkcert, Vite
`basicSsl`); `launch.json`'daki `https://localhost` sunucusu da "ayakta" sayılır. Doğrulama,
başlatma beklemesi ve başsız günlük yalnız loopback için sertifikayı sorgulamaz; panelin
kendisi (WebView) kendinden imzalı sertifikayı reddedebilir. Sertifika sistemce doğrulanamazsa
önizlemenin üstünde uyarı ve **Tarayıcı panelinde aç** çıkar; kalıcı çözüm sertifikayı sisteme
güvenilir eklemektir (mkcert) ya da **Dışarıda aç**. Uzak adresler önizlemeye gömülmez; hata
satırındaki **Tarayıcı panelinde aç** onları uygulama içi tarayıcıya (§15b) yollar. Araç
çubuğundaki `⌖` (**Öğe seç**) önizlenen sayfayı Tarayıcı panelinde öğe seçici açık olarak açar.

Gereksinim: günlük ve ekran görüntüsü için `pip install 'fusion-cli[web]'` ve
`playwright install chromium`.

## 15b) Tarayıcı paneli: ajanın tarayıcısını canlı izle, devral, öğe seç

Masaüstünde sağ paneldeki **Tarayıcı** sekmesi, ajanın `browser_*` araçlarıyla **aynı**
tarayıcıyı gösterir (Claude Code masaüstündeki Browser pane karşılığı). Ajan bir site açınca
sekme kendiliğinden öne gelir; tıkladığı, yazdığı her şey canlı görüntüde görünür. Tarayıcı
turlar arasında açık kalır (sekmeler, giriş yapılmış oturum korunur).

- **Gezinme:** adres çubuğu (şemasız adres `https://`, localhost `http://` alır; `about:`,
  `data:`, `chrome://` gibi http dışı şemalar açılmaz), ‹ › ↻,
  sekme şeridi (+ yeni sekme, × kapat), sayfa boyutu (1280 / 1440 / 768 / 375).
- **Kendin kullan:** görüntüye tıkla, tekerlekle kaydır, klavyeyle yaz; Cmd+V metni yapıştırır.
  Tab ve Esc de sayfaya gider; görüntüden klavyeyle çıkmak için **Esc'ye iki kez** bas.
  İç ağ ve bulut metadata adresleri ajandakiyle aynı kapıdan geçer, açılmaz; panelde yazdığın
  localhost adresi ajan için de izinli olur.
- **Devral / Ajana bırak:** ajan çalışırken tıklaman, yazman ya da gezinmen denetimi sana
  geçirir (ya da **Devral**); izlemek için kaydırmak geçirmez. O sırada ajanın tarayıcı
  eylemleri **bekler** (en çok 5 dk; bant "Ajan seni bekliyor" der): girişi, iki adımlı
  doğrulamayı ya da CAPTCHA'yı sen yap, **Ajana bırak** de, ajan aynı adımdan sürer. Girdiyle
  kendiliğinden alınan denetim tur bitince ajana döner; **Devral** ile aldığını sen bırakırsın. Ajan
  paylaşılan tarayıcıyı kapatamaz (`browser_close` "açık bırakıldı" der).
- **Öğe seç (`⌖`):** imlecin altındaki öğe vurgulanır; tıkladığında öğenin CSS seçicisi
  (`#id`, `data-testid`, `name`… yoksa `etiket:nth-of-type` zinciri), etiketi ve metni
  sohbet taslağına, kırpılmış görüntüsü ek olarak düşer (`.fusion/secimler/`, en çok 30 dosya,
  sembolik bağ ya da kök dışına yazılmaz). Ajan seçiciyi doğrudan `browser_click` ile kullanabilir.
  Form alanlarının **değeri** (parola, kart, kimlik) sohbete gitmez; alan `placeholder` ya da
  `aria-label` ile tanıtılır. `◧` görünür sayfanın görüntüsünü sohbete ekler, `≡` konsol ve ağ
  isteklerini gösterir (son 200 konsol mesajı ve 300 istek; `⌫` biriktirileni temizler).
- **Oturum:** **Temiz** (varsayılan; çıkınca silinir), **Panel oturumu** (Claude Code'daki
  "Keep cookies": çerezler `tarayici-paneli` profiline şifreli saklanır, sonraki açılışta
  girişli kalırsın) ya da `fusion browser` ile kurulan bir profil. Girişli bir oturumu sen
  seçtiysen ajan onu **yalnız "Ajan girişli oturumu kullanabilir" işaretliyken** görür; aksi
  hâlde tur kendi temiz tarayıcısını açar. Girişli oturumda tıklama/form gönderme yine onay ister.
  **Tarayıcıyı kapat** seçtiğin profili de bırakır: sonraki tur yapılandırmadaki varsayılan
  profille (onay sorarak) başlar.
- **Kapatmak:** **Ajan bu tarayıcıyı kullanır** kutusu kaldırılınca ajan eski davranışa döner
  (her tur ayrı tarayıcı; Tarayıcı sekmesi de kendiliğinden öne gelmez). Seçim kalıcıdır
  (`browser.panel_agent`); aynı ayar **Ayarlar → Web oturumları**'nda ve terminalde
  `fusion browser set panel-agent off` ile de değişir. **Tarayıcıyı kapat** Chromium'u kapatır.
- **Davranış değişikliği:** masaüstünde `panel_agent` varsayılan olarak açıktır; ajan
  `browser.headless: false` olsa da ayrı pencere açmaz, tarayıcı panelde görünür (ajanın
  `headed=true` isteği paylaşılan oturumda yok sayılır ve sonuçta not düşer). Eski görünür
  pencereyi isteyen `panel_agent`'ı kapatır.
- **Yerel adres izinleri:** panelde açtığın ya da bir turda yazdığın `localhost:port` paylaşılan
  tarayıcının izin kümesine girer ve tarayıcı kapanana kadar sonraki turlarda da izinli kalır
  (tur başına tarayıcıda her tur boş başlardı). Kümeyi sıfırlamak için **Tarayıcıyı kapat**.
- **Sınırlar:** panel tarayıcısı her zaman başsız çalışır (görüntü panelde; `browser.headless`
  tur başına tarayıcı içindir). Plan adımları ve alt ajanlar kendi ayrı tarayıcılarını kullanır,
  panelde görünmez. Açık panel oturumunda ajan başka profil yükleyemez; profili panelden seç.

RPC'ler `tarayici_panel.*` (`durum`, `ac`, `kare`, `git`, `geri`, `ileri`, `yenile`,
`sekme_ac/sec/kapat`, `tikla`, `kaydir`, `yaz`, `tus`, `boyut`, `devral`, `birak`, `oge`,
`oge_sec`, `ekran`, `konsol`, `ayar`, `profil`, `kapat`). Görüntü Chromium'un ekran yayınıdır;
panel kapalıyken kare üretilmez. Gereksinim: `pip install 'fusion-cli[web]'` ve
`playwright install chromium`.

**CLI'de:** `/tarayici ac` ajanla paylaşılan **görünür** bir Chromium penceresine geçer (ilk
tarayıcı eyleminde açılır, turlar arasında açık kalır; pencerede sen de gezinebilirsin).
`/tarayici` durumu ve sekmeleri, `/tarayici devral` / `/tarayici birak` denetimi, `/tarayici
kapat` pencereyi kapatıp tur başına tarayıcıya dönüşü yapar. Masaüstünden farkı: CLI
pencerede yaptığın girdiyi algılamaz, denetim **yalnız** `/tarayici devral` ile geçer ve
`/tarayici birak` ile döner; tur bitince kendiliğinden geri verilmez.

## 16) `fusion://` bağlantıları (masaüstü)

Tarayıcıdan ya da bir belgeden Fusion'ı hedefe açar (Claude Code masaüstündeki `claude://`
gibi): `fusion://sohbet/<id>` kayıtlı sohbeti, `fusion://ayarlar/bildirimler` ayarların bir
bölümünü, `fusion://yeni` yeni sohbeti açar. `fusion://yeni?kok=<yüzde-kodlu yol>` ile
gelen klasör **onaysız uygulanmaz**: `/`, `/Users/<ad>`, `C:\`, `C:\Users\<ad>`, `C:\Windows`,
`C:\Program Files` gibi çok geniş ya da sistem klasörleri reddedilir, kalanı bir onay penceresiyle
sorulur (Windows sürücü yolu da kabul edilir). `fusion://ayarlar/<bölüm>` her Ayarlar bölümünü
açar (`kisayollar`, `izinler`, `uzak`…); tanınmayan ad Genel'e düşer.

Uygulama kapalıyken tıklanan bağlantı açılıştan sonra yerine ulaşır: macOS'ta Launch Services
(`RunEvent::Opened`), Windows/Linux'ta ilk sürecin argümanı okunur; uygulama açıkken gelen bağlantı
tek örnek eklentisiyle çalışan pencereye iletilir. Şema kaydı: macOS `Info.plist`, Windows NSIS
kurulumu ve Linux paketleri `tauri.conf.json` › `plugins.deep-link.desktop.schemes` alanından
üretilir (kurulumda `HKCU\Software\Classes\fusion`, kaldırmada silinir).

## 17) Komut paleti ve uygulama kısayolları (masaüstü)

**⌘K** (Windows/Linux: Ctrl+K) her yerden komut paletini açar: eylemler, ekranlar, sohbetler,
slash komutları, ayarlar ve proje dosyaları tek listede aranır. Önekle daralt: `>` eylem/ekran,
`/` komut, `@` dosya, `#` sohbet, `?` ayar. Boş paletin başında son kullanılanlar durur. **⌘P**
paleti doğrudan dosya aramasıyla açar; dosya seçilince önizleme panelinde görünür. Komut seçmek
görev kutusuna `/ad ` yazar.

| Tuş (varsayılan) | Ne yapar |
|---|---|
| ⌘K · ⌘P | Komut paleti · dosyaya git |
| ⌘N | Yeni sohbet |
| ⌘, | Ayarlar |
| ⌘B · ⌘⌥B | Kenar çubuğu · çalışma paneli |
| ⌘J · ⌘⇧B | Terminal · önizleme |
| ⌘1 … ⌘9 | Açık sohbetler arasında geç |
| ⌘[ · ⌘] | Geri · ileri |
| ⌘/ | Ayarlar › Kısayollar |

Kısayollar **Ayarlar › Kısayollar**'da değiştirilir (Değiştir → tuşa bas; dolu tuş sorulmadan
devralınmaz), kaldırılır ya da varsayılana döndürülür. Kayıt terminalle aynı
`~/.fusion/keybindings.json` dosyasının `masaustu` bölümündedir; elle de yazılabilir ve pencereye
dönünce uygulanır:

```json
{ "masaustu": { "mod+j": null, "mod+shift+t": "terminal", "f5": "komut:status" } }
```

Yazım: `mod` macOS'ta ⌘, diğerlerinde Ctrl; değiştiriciler `mod+ctrl+alt+shift` sırasıyla.
En az bir değiştirici gerekir (yalnız F1-F12 tek başına bağlanır); ⌘C/⌘V/⌘X/⌘Z/⌘A/⌘Q/⌘W/⌘H/⌘M
gibi sistem kısayolları bağlanamaz. `komut:<ad>` bir slash komutunu çalıştırır. Eylem adları:
`palet`, `dosya_ara`, `yeni_sohbet`, `ayarlar`, `kenar_cubugu`, `terminal`, `onizleme`, `denetci`,
`geri`, `ileri`, `kisayollar`, `gecmis`, `paylas`, `yardim`, `bolmeyi_kapat`, `sohbet_1`…`sohbet_9`.
Türkçe Q klavyede ⌘[ ve ⌘] ⌥ gerektirir; istersen başka tuşa bağla.

- **Varsayılana döndür**: eylemin varsayılan tuşunu başka bir eylem devraldıysa Fusion sorar;
  **Taşı** tuşu geri alır (öbür eylem tuşsuz kalır).
- **Windows/Linux**: dosyadaki `ctrl+…` ile `mod+…` aynı tuştur; çakışma buna göre sorulur ve
  `ctrl+c`/`ctrl+v` gibi yazımlar da sistem kısayolu sayılıp bağlanmaz.
- **Diyalog açıkken** (geri bildirim, paylaş, onay, proje…) kısayollar ve palet çalışmaz; Ayarlar
  ve palet bunun dışındadır.
- **Terminal odaktayken** macOS'ta ⌘ tuşları uygulamanındır (⌘K terminali temizler). Windows/Linux'ta
  Ctrl+harf kabuğa gider (Ctrl+K satır sonunu siler, Ctrl+P geçmiş); yalnız terminali aç/kapat tuşu
  (Ctrl+J) ve Ctrl+Shift bağları uygulamaya geçer.
- Terminalde `/keybindings` yalnız terminal bağlamlarını (`giris`, `tui`) gösterir ve örnek dosyaya
  yalnız onları yazar; masaüstü bölümü Ayarlar › Kısayollar'dan yönetilir.
- Kısayol uçları (`kisayol.*`) yalnız masaüstü oturumuna açıktır; uzaktan kontrol (telefon/PWA)
  bunları çağıramaz.

---

## 15) REPL önekleri, durum, dışa aktarma ve görünüm (Claude Code paritesi)

### Önekler: `!`, `@`

Önekler TEK satırlıdır: çok satırlı `! …` yapıştırması düz mesaj sayılır. `#` öneki Claude Code'da olmadığı için yoktur; `# …` satırı olağan istemdir. `!` çıktısı ve `@dosya` içeriği sonraki turun bağlamına "kullanıcı talimatı değildir" etiketiyle ve sırlar maskelenerek girer; `@dataclass` gibi var olmayan sözcükler sessizce geçilir. Masaüstünde de çalışır: `! komut` çıktısı sohbete yazılır, `@dosya` bağlama eklenir (okunamayan anma yalnız günlüğe düşer). Terminal ve TUI'de `! komut` çıktısı bağlama girince model Claude Code'daki gibi ikinci istem beklemeden yanıt verir; `settings.json` (`~/.claude/`, `.claude/`, `.claude/settings.local.json`) içinde `"respondToBashCommands": false` yalnız bağlama ekler. Masaüstünde çıktı şimdilik yalnız bağlama girer. Plan kipinde `!` hâlâ reddedilir.

| Yaz | Ne olur |
|-----|---------|
| `! git status` | Komut **doğrudan** çalışır (model çağrılmaz). Çıktı ekrana basılır ve bir sonraki mesajın bağlamına "kullanıcının çalıştırdığı kabuk çıktısı" olarak girer. Plan kipinde çalışmaz. Silmeler yine çöpe gider. Bazı mevcut dosyaların başlangıç hâli kaydedilir; yazarı doğrulanamayan kabuk değişiklikleri otomatik geri alınmaz. |
| `@src/app.py şu fonksiyonu incele` | Anılan dosya (ya da dizin listesi) bağlama eklenir; mesaj olduğu gibi gider. En çok 8 dosya, dosya başına 20 bin karakter. Tab ile yol tamamlama: `@src/mo<Tab>`. |
| `# testleri her zaman pytest ile çalıştır` | Kalıcı bellek notu (`/learn` ile aynı depo). `/lessons` ile gör, `/forget` ile sil. |

`@sunucu:kaynak` (MCP kaynağı) anması tur başında sunucudan okunup bağlama eklenir (bkz. "MCP istemleri ve kaynakları").

### Durum ve bağlam

- `/status` — sürüm, motor, izin kipi, model/kademe, düşünme, etkin çıktı stili, dizin(ler), MCP sunucuları, hesap, Claude Code'daki `Session kind` (`interactive`) ve bağlantı (sağlayıcı kurulumunun hazırlığı; ağ çağrısı yapmaz), sohbet kimliği, yapılandırma dosyası. Tur sürerken de hemen çalışır. Claude Code'dan fark: sekmeli Settings arayüzü yok, metin olarak basılır.
- `/context [all]` — Claude Code'daki gibi bağlam kullanımını renkli ızgara olarak gösterir (her hücre model penceresinin %1'i; kategori başına renk ve boş alan). Yüzde MODEL PENCERESİNE göredir; token sayısı son API çağrısında ölçülen girdi token'ından, ölçüm yoksa tahminden (karakter/3) gelir ve hangisi olduğu yazılır. Araç çıktısı ağırlığı, büyük bellek dosyaları ve kapasite için öneriler; pencere aşılınca ne kadar aşıldığı ve `/compact`/`/clear` önerisi. Altında kalem kırılımı (sistem istemi / özet / kullanıcı / asistan / araç sonuçları, araç tanımları, bekleyen `!`/`@` bağlamı, sıkıştırma eşiği); `all` en büyük kalemleri de listeler. Durum çubuğundaki `bağlam %N` hâlâ sıkıştırma eşiğine göre sayar.
- Durum çubuğunda `bağlam %12 · ~3k tok` sayacı her tur sonunda güncellenir (satır-içi kipte `FUSION_TOOLBAR=1` ile görünür).

### Dışa aktarma ve pano

- `/export [dosya]` Claude Code'daki gibi konuşmayı **düz metin** aktarır (kullanıcı `> `, asistan ve araç çağrısı `⏺ `, araç çıktısı `⎿` girintili). Dosya adı verilirse doğrudan yazar (uzantısızsa `.txt`); argümansız çağrı **Panoya kopyala / Dosyaya kaydet** seçicisini açar (terminal, tam ekran TUI, masaüstü). Fusion ekleri: `md`/`json` bayrağı ya da `.md`/`.json` uzantısı biçimi seçer, `pano` doğrudan panoya, `dosya` varsayılan adla (`fusion-sohbet-<tarih>.txt`) yazar. Sistem istemi dışarıda, uzun araç çıktıları kırpılır, sırlar (başlık dahil) maskeli. Proje kökü dışına yazılmaz; var olan dosya `zorla` eklenmeden ezilmez.
- `/copy` → son asistan cevabı panoya; `/copy 2` sondan ikinci. Claude Code'daki gibi cevapta kod bloğu ya da alıntı varsa önce seçici açılır: tam yanıt ya da tek bir blok (satır içi, TUI ve masaüstünde). Seçicide `w` seçimi panoya değil proje kökünde `fusion-copy-<zaman>.<uzantı>` dosyasına yazar (SSH üzerinde işe yarar; kod bloğunda uzantı dilden gelir, tam yanıt `.md`). (pbcopy / wl-copy / xclip / xsel / clip) Masaüstü seçicisinde `w` tuşunun yerine her satırın "Dosyaya yaz: …" eşi vardır.
- `/diff` → çalışma ağacının `git diff HEAD --stat` özeti ve bu oturumda dosya değiştiren turlar (tur numarası, görev, dosyalar); `/diff tam` farkın kendisini de basar. Claude Code bunu etkileşimli görüntüleyicide gösterir; Fusion metin basar.
- `/recap` → Claude Code'daki gibi oturumun tek satırlık özeti (en çok 400 karakter), yalnız istenince; agent modeline araçsız tek çağrıdır, özet konuşma geçmişine eklenmez (`/compact`'tan farkı). Henüz yok: uzaklaşıp dönünce otomatik özet (Session recap ayarı).
- Masaüstü: Sohbeti paylaş penceresinde Markdown/JSON seçimi ve "Dosyaya kaydet" (RPC `sohbet.disa_aktar {bicim, baslik}`).

### Ayarlar: `/config` ve `fusion config`

```
/config                       # tüm ayarlar (yol · değer · tip)
/config runtime.web           # süzgeç
/config runtime.max_tokens    # tek değer
/config runtime.max_tokens=8192   # oturuma uygula + config.yaml'a yaz
/config theme=dark editorMode=vim model=sonnet   # Claude adları, birden çok çift
/settings · /config --help        # takma ad · kullanım
fusion config list [süzgeç] · fusion config get <yol> · fusion config set <yol> <değer>
fusion --set runtime.max_tokens=8192 --set runtime.lessons=false   # yalnız bu oturum
fusion --profile high                                        # yalnız bu oturum kademe
fusion --set runtime.max_tokens=8192 run "görev"                # alt komutlarda da geçerli
```
Claude Code ayar adları: `model` (`/model <model>` ile aynı, kaydeder), `theme` (`dark`/`light`/`dark-ansi`/`light-ansi`/`dark-daltonized`/`light-daltonized` → terminal paleti), `outputStyle`, `editorMode` (`vim`/`normal`), `tui` (`default`/`fullscreen`). Adlar Claude'daki gibi büyük/küçük harf duyarlıdır. Etkileşimli Settings paneli henüz yok; argümansız `/config` listeyi basar.

`--set`/`--profile` REPL'in yanında `run`, `agent`, `serve`, `models`, `trace`, `mcp-tools` ve `config get/list/show` alt komutlarına da uygulanır (`config set` dosyaya yazar, oturumluk değeri almaz; `app`/`mcp` sunucuları yapılandırmayı kendileri yükler). Hatalı çift çıkış kodu 2 ile durdurur.
Erişilebilen bölümler `runtime.*`, `embedding.*` ve `capabilities.*`; tip dataclass alanından doğrulanır (boolean: true/false/açık/kapalı, liste: `a,b,c`, sözlük: `ad=değer, ad2=değer`, `null` anahtarı siler). Beceri görünürlüğü tek anahtarla: `/config capabilities.overrides.deploy=user-invocable-only` (`fusion config set capabilities.overrides.deploy kapali`); `capabilities.disabled=a,b` kalıcı kapatma. REPL'de değişiklik beceri kataloğuna hemen yansır. Model rolleri için `/model`, `/level`, `/mode`.

### Çıktı stili: `/output-style`

Proje dizinindeki stil (`.claude/output-styles`, `.fusion/cikti-stilleri`) yerleşik ya da kullanıcı stiliyle aynı adı taşıyorsa `fusion trust` verilmeden onu GÖLGELEYEMEZ (yeni adlar yine listelenir).

`default` · `Proactive` (sıradan kararlarda sormadan uygular) · `Concise` (sonuçla başlar) · `Explanatory` (`★ Insight` blokları) · `Learning` (Insight + `TODO(human)` ve "Learn by Doing" isteği, kullanıcıyı bekler); ad büyük/küçük harf duyarsız. Eski `varsayilan`/`ozlu`/`aciklayici`/`ogretici` adları kullanımdan kalkmış takma addır (bir kez uyarılır). Özel stil: `~/.fusion/cikti-stilleri/<ad>.md` ya da `~/.claude/output-styles/<ad>.md` (proje içinde `.fusion/cikti-stilleri`, `.claude/output-styles`); frontmatter `name`/`description`, gövde talimat. Stil sistem istemine en sona eklenir. Claude Code'daki gibi özel stil `keep-coding-instructions: true` demedikçe sistem isteminin yazılım mühendisliği bölümleri (Kod değişiklikleri, Doğrulama) çıkarılır; yerleşik stiller bu bölümleri korur. Eklenti stili `force-for-plugin: true` taşıyorsa eklenti etkinken kullanıcı seçimini ezer (ilk yüklenen kazanır). Proje stilleri çalışma dizini ile depo kökü arasındaki her `.claude/output-styles`'tan yüklenir; aynı adda en yakın dizin kazanır.

Seçim Claude Code'daki gibi projenin `.claude/settings.local.json` dosyasına `outputStyle` olarak (özgün adla, ör. `"outputStyle": "Explanatory"`) yazılır; `/config outputStyle=<ad>` aynı yoldan geçer. Elle yazılan değer büyük/küçük harf duyarlıdır ve katmanlardan okunur (`~/.claude/settings.json` < `.claude/settings.json` < `.claude/settings.local.json`); tam eşleşmeyen değer `default` olur. Eski `runtime.output_style` yalnız hiçbir katmanda `outputStyle` yokken okunur.

### Durum satırı betiği: `/statusline`

Ayar Claude Code ile aynıdır: `settings.json` içinde
`"statusLine": {"type": "command", "command": "~/.claude/statusline.sh", "padding": 0, "refreshInterval": 5, "hideVimModeIndicator": false}`.
Okuma sırası: `~/.claude/settings.json` → Fusion'ın eski `runtime.status_line_command` dizesi (kullanımdan kalkmış takma ad) → proje `.claude/settings.json` → `.claude/settings.local.json`; proje dosyaları kabuk komutu çalıştırdığı için yalnız `fusion trust` sonrası okunur.

```
/statusline model adını, bağlam yüzdesini ve git dalını göster
/statusline
```
`/statusline <istek>` betiği Claude Code'daki gibi `statusline-setup` ajanına yazdırır; argümansız hâli durum satırını kabuk isteminden (PS1) kurdurur.

Betik oturum başında (sürdürmede de), her asistan cevabından sonra, `/compact` bitince, izin kipi ya da vim kipi değişince ve `refreshInterval` saniyede bir çalışır; tetikler 300 ms birleştirilir, yeni tetik süren betiği iptal eder, komut değişince beklemeden çalışır. stdin'den Claude Code statusline şemasında JSON alır (`cwd`, `session_id`, `session_name`, `transcript_path`, `model.{id,display_name}`, `workspace.{current_dir,project_dir,added_dirs,git_worktree}`, `version`, `output_style.name`, `cost.*` (`/clear` yeni oturumla $0'dan ve süre baştan başlar), `context_window.*` ve `exceeds_200k_tokens` (Claude Code'daki gibi en son API yanıtından; `/compact` sonrası `current_usage` sonraki çağrıya dek `null`), `effort.level`, `thinking.enabled`, `vim`, `agent`, `pr`, `worktree`; Fusion'a özgü motor/izin kipi/kademe `fusion` altında). Betiğe `COLUMNS`/`LINES` verilir. TUI'de bütün satırlar ANSI renk ve OSC 8 bağlantılarıyla yerleşik çubuğun üstünde gösterilir. Satır içi (`/tui default`) REPL'de betik oturum başında ve her tur sonunda çalışır, bütün satırlar ANSI/OSC 8 korunarak istemin üstüne basılır (`FUSION_TOOLBAR=1` ile alt çubuk açıksa orada yalnız ilk satır görünür); kip değişimi ve `refreshInterval` tetikleri yalnız TUI'dedir.

Claude Code'dan farklar: Fusion'ın ölçmediği `cost.total_api_duration_ms`, `total_lines_added/removed` 0 gelir; `prompt_cache`, `rate_limits`, `prompt_id`, `workspace.repo` yazılmaz. Satır içi (düz) REPL yalnız ilk satırı tur sonunda gösterir.

### Görünüm: `/theme`, `/tui`, `/search`

Yalnız terminal: masaüstü bu komutları "desteklenmiyor" olarak işaretler (masaüstü teması ayarlardan). `fusion config set runtime.terminal_theme`/`runtime.tui` yalnız geçerli değerleri kabul eder.

- `/theme` → `koyu` · `acik` · `ansi` · `daltonizm`; anında uygulanır, `runtime.terminal_theme` ile kalıcı. Masaüstü teması ayrıdır (Ayarlar › Genel).
- `/tui default` / `/tui fullscreen` (Claude Code adları; `inline` eski takma ad) → `runtime.tui`; yeni `fusion` açılışında geçerli (`FUSION_INLINE=1` ile aynı). Claude Code oluşturucuyu konuşmayı koruyarak hemen yeniden açar; Fusion'da geçiş sonraki açılışta olur.
- `/search <metin>` → tam ekran konuşmasında son eşleşmeye kaydırır; `End` canlı akışa döner.

### Tam ekran girdi: çok satır, geçmiş, Ctrl+C/Ctrl+D (Claude Code ile aynı)

- **Çok satır:** `\` + Enter, Option+Enter, Shift+Enter (CSI-u ya da modifyOtherKeys gönderen terminallerde), Ctrl+J; yapıştırma. Enter gönderir. Kutu en çok 10 satıra uzar.
- **Geçmiş:** Up/Down (Ctrl+P/Ctrl+N) çok satırda imleci, ilk/son satırda geçmişi gezer. Geçmiş çalışma dizini başınadır (`<bellek>/girdi-gecmisi/`, 0600), art arda aynı satır bir kez yazılır. **Ctrl+R** satır içi tersine arama (Ctrl+R sonraki, Enter kabul, Ctrl+C/Esc iptal).
- **Ctrl+C** tur sürerken keser; boştayken ilk basış girdiyi temizler (silinen taslak Claude Code'daki gibi Up ile geri gelir: hemen ya da sonraki mesajlardan sonra, oturumda son 10 taslak tutulur, dosyaya yazılmaz), 800 ms içindeki ikinci basış çıkar. **Ctrl+D** girdi doluysa sonraki karakteri siler, boşken 800 ms içinde iki basış çıkar. **Ctrl+U** satır başına kadar siler.
- Konuşma kaydırma: PageUp/PageDown, Home/End, Ctrl+Home/Ctrl+End, Shift+Up/Down.
- **Kuyruk:** tur sürerken Enter mesajı kuyruğa alır. Düz mesaj Claude Code'daki gibi araç çağrıları bitince AYNI tura verilir; tur mesaj okunmadan biterse kendiliğinden sıradaki tur olarak gider. Komutlar, `!` kabuk satırları ve `@` anması tur sonunu bekler. İlk satırda Up kuyruktakileri (`!` satırları hariç) taslağın önüne geri alır. Ctrl+X Ctrl+S (`chat:sendNow`) kuyruğu hemen yollar: bekleyen varsa tur kesilir, taslak arkasına kuyruklanır. Esc turu keser, kuyruktakiler korunur ve hemen gönderilir. `/status`, `/tasks`, `/usage` (`/cost`), `/model`, `/effort`, `/add-dir` ve `/permissions` Claude Code'daki gibi kuyruğa girmez, tur sürerken hemen çalışır (tam ekran TUI).
- **Düzenleme:** Ctrl+G ya da Ctrl+X Ctrl+E girdiyi dış editörde açar, Ctrl+_ son düzenlemeyi geri alır, Ctrl+S dolu taslağı saklar (boş girdide geri getirir), Ctrl+L girdi ve konuşmayı koruyarak ekranı yeniden çizer.

Claude Code'dan farklar: Ctrl+R araması prompt_toolkit'in arama çubuğuyla yapılır (Tab kabul tuşu değil); Ctrl+Enter terminalden ayrı bir tuş olarak okunmadığı için `chat:sendNow` yalnız Ctrl+X Ctrl+S'de; `chat:sendNow` süren kabuk komutunu arka plana almak yerine turu keser; motor yönlendirme gelince aynı yanıttaki henüz başlamamış araç çağrılarını başlatmaz.

### Terminal kurulumu: `/terminal-setup`

Claude Code'daki gibi terminali tanır ve tek seferlik ayarı yazar: VS Code, Cursor ve Devin Desktop'ta kullanıcı `keybindings.json`'una Shift+Enter → ESC CR bağı (ve `terminal.integrated.gpuAcceleration: "off"`), Zed'de `keymap.json`'a Terminal bağı (önce `keymap.json.<karma>.bak` yedeği; okunamayan dosya değiştirilmez, blok yazdırılır), Alacritty'de `alacritty.toml`'a Shift+Return bağı, Apple Terminal'de varsayılan profilde "Use Option as Meta Key" ve sesli zili kapatma, iTerm2'de uygulamaların panoya erişimi (`/copy` için). Var olan bağa dokunulmaz ("already configured"). Claude Code'dan fark: VS Code'da `mouseWheelScrollSensitivity` ayarlanmaz; ekran okuyucu kipine göre zil ayrımı yok.

### Tuş bağları ve vim: `/keybindings`, `editorMode`

Vim kipi Claude Code'daki gibi `/config editorMode=vim` (kapatmak: `editorMode=normal`) ile açılır; `/vim` Claude'da v2.1.92'de kaldırıldı, Fusion'da bir sürüm boyunca kullanımdan kalkmış takma ad olarak çalışır ve bir kez uyarır. Vim kipi yalnız terminaldir. Vim kipinde Esc INSERT'ten NORMAL'e geçer; NORMAL kipte Esc ve her kipte Ctrl-C çalışan turu keser. Claude Code'daki gibi `~/.claude/settings.json` içinde `"vimInsertModeRemaps": {"jj": "<Esc>"}` iki tuşluk diziyi Escape'e eşler (tam ekran TUI): ikinci tuş bir saniye içinde gelirse iki karakter de yazılmaz ve NORMAL kipe geçilir; ayar yalnız kullanıcı dosyasından okunur. Durum satırı betiğine giden JSON'daki `vim.mode` gerçek kipi (`INSERT`/`NORMAL`/`VISUAL`) taşır. Aynı dosyanın `masaustu` bölümü masaüstü uygulamasının kısayollarıdır (bkz. §17); masaüstünde `/keybindings` Ayarlar › Kısayollar'ı açar.

`/keybindings` Claude Code'daki gibi `~/.claude/keybindings.json` dosyasını gösterir (yoksa `$schema`/`$docs` iskeletiyle yazar; `CLAUDE_CONFIG_DIR` verilmişse orada):
```json
{ "$schema": "https://www.schemastore.org/claude-code-keybindings.json",
  "bindings": [
    { "context": "Chat", "bindings": { "ctrl+e": "chat:externalEditor", "ctrl+s": null,
                                        "meta+g": "command:compact" } },
    { "context": "Task", "bindings": { "ctrl+x ctrl+b": null } } ] }
```
Tuş yazımı Claude Code ile aynıdır: `ctrl`/`shift`/`alt`/`meta`/`opt` ile `+`, büyük/küçük harf duyarsız, chord'lar boşlukla (`ctrl+x ctrl+e`), `escape`, `enter`, `space`, `pageup`, `wheelup`… `null` varsayılan bağı kaldırır, `command:<ad>` `/ad` komutunu çalıştırır. Ayrılmış kısayollar (Ctrl+C, Ctrl+D, Ctrl+M, Ctrl+[, Ctrl+I, Ctrl+H) bağlanamaz. Bağlamlar: `Global` ve `Chat` satır içi istem ile tam ekran TUI'ye, `Task` ve `Scroll` tam ekran TUI'ye uygulanır; belgelenen öteki bağlamlar geçerlidir ama Fusion'da ayrı yüzeyleri olmadığından yok sayılır. Karşılığı olan eylemler: `chat:cycleMode`, `chat:sendNow`, `chat:externalEditor`, `chat:undo`, `chat:stash`, `chat:clearInput`, `chat:clearScreen`, `app:redraw`, `chat:modelPicker`, `app:interrupt`, `app:exit`, `task:background`, `scroll:*`. Karşılığı olmayan eylem (`chat:fastMode` gibi) dosyayı bozmaz, `/keybindings` uyarı olarak gösterir. Dosya kaydedilince yeniden başlatmadan uygulanır.

Eski `~/.fusion/keybindings.json` (`giris`/`tui` bağlamları, `c-x` yazımı, `komut:<ad>`) bir sürüm boyunca kullanımdan kalkmış takma ad olarak okunur ve `/keybindings` uyarır; Claude dosyası onun üstüne uygulanır. Aynı eski dosyanın `masaustu` bölümü masaüstü kısayollarının yeri olarak kalır.

---

## 16) Bilgisayarı kullanma (computer use, yalnız macOS)

Fusion ekranını görüp fare ve klavyeyle uygulamaları yönetebilir. Her eylem yine onay
kartından geçer; Claude Code / Codex'teki gibi iki macOS izni gerekir.

**İzinler (Ayarlar › İzinler › Bu bilgisayar).** Erişilebilirlik (tıklama/yazma/kaydırma) ve
Ekran Kaydı (ekran görüntüsü). Kart durumu çekirdekten okur (`izin.masaustu_durum`), **İzin iste**
sistem penceresini açar (`izin.masaustu_iste {tur}`), **Sistem Ayarlarını Aç** ilgili Gizlilik
bölümüne gider. Bir masaüstü aracı izin yüzünden düşerse araç `izin_gerekli` döner, çekirdek
`MasaustuIzinGerekli` olayı yollar ve izin kartı kendiliğinden açılır. Ekran Kaydı izninden sonra
Fusion'ı yeniden açmak gerekebilir. TCC istemi Fusion.app adına açılır (sidecar bu uygulamanın
çocuğudur).

**Ekran görüntüsü ve koordinatlar.** `desktop_screenshot` görüntüyü
`runtime.desktop_screenshot_max_width` (1568 px) genişliğe küçültür ve çerçeveyi bildirir:
"Görüntü 1568x980 px; ekran 1: 1440x900 nokta … 1 görüntü pikseli = 0.92 nokta". Fare
araçlarına verilen `x,y` HER ZAMAN bu görüntünün pikselidir; Fusion ekran noktasına çevirir
(Retina 2x sorunu yok). Çerçeve tur ile yaşar: yeni turda tıklamadan önce yeni görüntü gerekir,
yoksa araç "önce desktop_screenshot al" der (önceki turun pikseliyle kayık tıklama yerine). `region="x,y,w,h"` bölgeyi büyütür (kırpık; tıklama tam görüntü
koordinatıyla), `display=N` ekran seçer, `desktop_displays` ekranları listeler.
`runtime.desktop_exclude_fusion_window: true` ile Fusion'ın kendi penceresi (CLI'de terminal ya
da gömülü terminalin IDE'si: süreç ağacındaki atalar) görüntüden çıkarılır (macOS 14+
ScreenCaptureKit; yoksa tam ekran). Bölge (`region`) görüntüsü `screencapture -R` ile ham ekran
pikselinde alınır: büyütme yoktur ve Fusion penceresi dışlanmaz; `display` verilirse son
görüntünün ekranıyla uyuşmalıdır.

**Fare.** `desktop_mouse action=click|right_click|double_click|triple_click|middle_click|
hover|down|up|drag` (`drag` için `to_x,to_y`), `button=left|right|middle`, `modifiers="cmd+shift"`.
`desktop_click` eski sol tık adı. `desktop_scroll lines=-5` (dikey, pozitif yukarı),
`delta_x=3` (yatay, pozitif sola), `x,y` ile imleç önce oraya gider.

**Klavye.** `desktop_key key="cmd+shift+4 enter"`: `+` ile değiştirici (cmd/ctrl/alt/shift),
boşlukla sıra; `repeat=3` tekrar, `hold_ms=500` basılı tutma (toplam `repeat × tuş × hold_ms`
en çok 30 sn; aşarsa araç parçalamanı ister). Chrome `key` eylemiyle aynı sözdizimi.
`desktop_type` Unicode metin yazar.

**Tek oturum.** Aynı anda yalnız bir Fusion TURU fare/klavye gönderir (aynı uygulamadaki iki
sohbet de birbirini bekler); kilit `$TMPDIR/fusion-desktop-<uid>/oturum.lock` dosyasındadır
(`flock` ile atomik), tur bitince bırakılır; süreç çıkınca ya da 5 dk eylem yapılmazsa da düşer.
Başka tur tutuyorsa araç "Başka bir Fusion oturumu … kullanıyor" der. Onay kartı fare eylemini
ve noktayı söyler: "sağ tık (784, 490)", "sürükle (10, 20) → (300, 400)".

Henüz yok: küresel Esc ile durdurma, diğer uygulamaları gizleyip tur sonunda geri gösterme,
uygulama bazlı güven listesi; Windows/Linux masaüstü kontrolü.

---

## Komut kopya kâğıdı

| Yaz | Ne yapar |
|-----|----------|
| `fusion` | Fusion'ı aç (REPL) |
| `/agent` · `/fusion` | Motor değiştir |
| `/mode` · `/mode high` | Model gücü profili |
| `/effort high` | Düşünme yoğunluğu |
| `/model [model]` | `/model <model>` agent modelini değiştirir ve varsayılan olarak kaydeder (tam kimlik, `claude-…`, aday adı ya da yapılandırılmış aileden `sonnet`/`opus`/`haiku`); Fusion alt komutları `agent`/`judge`/`cand`/`add`/`rm` yalnız oturum içindir |
| `/plan` · `/plan goster` · `/plan ac` | Plan kipine geç · kayıtlı planı yaz · planı editörde aç |
| `/persona explore` · `/persona off` | Oturumu bir ajan kişiliğiyle sür |
| `/subtask <görev>` | Görevi bağlamı devralan izole alt ajanda koştur |
| `/memory` · `/memory ajan <ad>` | Düz metin bellek / alt ajan belleği |
| `/undo` | Son değişikliği geri al |
| `/rewind` · Esc Esc | Bir turun başına dön (kod/konuşma/ikisi) |
| `/btw [soru]` | Konuşma hakkında yan soru (Claude Code): model konuşmayı görür ama araç kullanmaz; soru ve cevap konuşma geçmişine ve transcript'e girmez. Son 20 yan soru tutulur; argümansız `/btw` en sonuncusunu gösterir |
| `/fork [istem]` | Konuşmayı arka plan kopyasına ver, burada devam et (bkz. ARKA_PLAN_GOREVLERI) |
| `fusion -c` · `/resume` | Kaldığın sohbete dön |
| `/rename <ad>` · `/branch` | Sohbete ad ver · dallandır |
| `fusion -w <ad>` · `/worktree <ad>` | İzole git çalışma ağacında çalış |
| `/cd <yol>` | Oturumu başka klasöre taşı (konuşma sürer) |
| `/goal <koşul>` · `/goal durum` · `/goal devam` · `/goal clear` | Koşul karşılanana kadar turları kendiliğinden sürdür |
| `/voice` · `/voice gonder` · `/voice durum` | Terminalde yerel dikte (cihaz üstü) |
| `/verify` | Test/lint çalıştır |
| `/onizleme [ad]` · `/tarayici ac` | launch.json sunucuları · ajanla paylaşılan görünür tarayıcı (`devral`/`birak`) |
| `/code-review` (`/review`) `[low\|medium\|high\|xhigh\|max] [--fix] [--comment] [--max-findings n\|all\|default] [pr#\|dal\|yol]` | Claude Code'daki gibi dalın değişikliklerini (ya da PR/dal/yol/git aralığı) doğruluk hataları için fork alt ajanda inceler; `--fix` bulguları uygular, `--comment` PR/MR'a yazar; seviye yazılmazsa son yazılan seviye, `--max-findings` `default` verilene dek hatırlanır. `ultra` (bulut incelemesi) Fusion'da yok |
| `/simplify` | Değişen kodu sadeleştir (hata avı değil) |
| `/security-review [yol]` | Değişiklikleri OWASP başlıklarıyla tara; kod değiştirmez |
| `/debug [belirti]` | Fusion'ın kendi sorununu teşhis et (doctor + son eylemler) |
| `/batch <talimat>` | Talimatı bağımsız parçalara bölüp paralel alt ajanlarla uygula |
| `/doctor` | Kurulum denetimi (`fusion doctor` ile aynı çıktı) |
| `/loop 5m <görev>` · `/loop list` · `/loop stop [id]` | Görevi aralıkla yinele (oturum boyunca) |
| `/permissions` · `fusion permissions` | İzin kurallarını (allow/ask/deny) listele, ekle, sil |
| `fusion trust` | Projenin config/izin/araç dosyalarına güven |
| `/good` · `/bad` | Fusion'a geri bildirim |
| `/providers` · `/providers add` | Sağlayıcıları gör / anahtar ekle |
| `/health` | Model sağlığı / devre durumu |
| `/help` | Tüm komutlar |
| `! cmd` · `@dosya` | Kabuk · dosya anma |
| `/status` · `/context` | Oturum durumu · bağlam kırılımı |
| `/export` · `/copy` | Konuşmayı dosyaya/panoya · son cevabı panoya |
| `/config [key=value ...]` · `/settings` | Ayar değiştir; Claude adları ve `bölüm.alan` yolları (`fusion config get/set/list`) |
| `/output-style` · `/theme` · `/tui` | Çıktı stili · terminal teması · görünüm |
| `/statusline` · `/keybindings` | Durum satırı betiği · tuş bağları (vim: `/config editorMode=vim`) |
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
- `/loop <görev>` → **kendi tempolu**: görev hemen (boşta) çalışır; sıradaki çalışmayı ajan
  `schedule_wakeup(in, loop_id)` ile 1 dk–1 sa arasında kendisi seçer, seçmezse 10 dk sonra
  yine çalışır; gerek kalmayınca `cron_delete` ile döngüyü kendisi kapatabilir. Aralıksız
  `/loop /verify` gibi komut görevleri sabit 10 dk'dır. Argümansız `/loop` → `.claude/loop.md`
  (proje ya da ev), yoksa yerleşik bakım görevi (o da kendi tempolu).
- `/loop list`, `/loop stop <id>`, `/loop stop all`.
- Zamanlanamayan komutlar (takma adlarıyla birlikte): onay kipi (`/auto`, `/bypass`, `/mode`…),
  model/sağlayıcı, `/clear`, `/exit`, `/loop`, `/cd`, `/voice` (`/dikte`) ve `/rc`
  (`/remote-control`): kök, mikrofon ve uzaktan erişim yalnız kullanıcının elinden açılır.
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
  kayıt dosyaları yüklemede süpürülür.
- Masaüstü **Zamanlananlar** kenar çubuğundaki "Bu sohbetin döngüleri" bölümü etkin sohbetin
  `/loop`/`cron_*` görevlerini (zamanlama, sıradaki vade, ajan kurduysa işareti) gösterir;
  "Durdur" `/loop stop <id>` ile aynıdır. Kalıcı **Zamanlananlar** ekranına "Cron ifadesi" türü eklendi
  (en sık 15 dakikada bir; denetim ifadenin iki eşleşmesi arasındaki en kısa farka bakar,
  `* 9 * * *` kayıtta reddedilir). Oturum zamanlayıcısı (`/loop`, `cron_create`) 1 dakikaya
  kadar iner. Cron saatleri yerel duvar saatidir; yaz saati geçişinde 09:00 görevi 09:00'da kalır.
- Kalıcı **Zamanlananlar** görevi bitince sonucu bildirilir (uygulama içi şerit + işletim sistemi
  bildirimi) ve çalışma geçmişine yazılır (`zamanlama.calisma_kaydet`; görev başına son 10:
  zaman, sohbet, tamam/hata, cevap özeti). Kartta son üç çalışma görünür.

## Çalışma dizini: `/cd`

Claude Code / Codex `/cd` karşılığı. `/cd ../diger-proje` oturumun proje kökünü değiştirir;
konuşma, `/rewind` noktaları ve `/loop` görevleri aynı sohbette kalır, araçlar sonraki turdan
itibaren yeni kökte çalışır. Argümansız `/cd` mevcut dizini yazar. Masaüstünde de aynı komut
sekmenin kökünü taşır (tur sürerken reddedilir).

- Göreli yol mevcut köke göredir, `~` ev dizinidir. Disk kökü ve ev dizininin tamamı reddedilir.
- Eski projenin `/add-dir` klasörleri ve "oturum boyunca izin ver" kararları yeni köke taşınmaz;
  yeni kökün becerileri, düz belleği ve `.claude/settings.local.json` onaysız komutları yüklenir.
  İzin dosyası güvenilmiyorsa uyarı çıkar (`fusion trust`).
- İzin kuralı: `"deny": ["Cd(//etc/**)"]` o dizinlere geçişi engeller (glob kuralı `Edit` ile aynı).
- Model sonraki turda "çalışma dizini değişti" notunu görür. Proje `config.yaml` ve `.mcp.json`
  açılıştaki dizinden okunmuştu, `/cd` bunları yeniden yüklemez. `/loop` ile `/cd` zamanlanamaz.

## Turlar arası hedef: `/goal`

Claude Code / Codex `/goal` karşılığı. `/goal tüm testler geçiyor ve lint temiz` hedefi kurar
ve ilk turu hedef kipinde (pes etmeyen istem, 100 adım) başlatır. Her tur bitince hakem rolünün
modeli (`judge`, ucuz rol) son konuşmaya bakıp karar verir:

- **Henüz değil** → gerekçesiyle yeni bir devam turu kendiliğinden başlar.
- **Tamam** → `✓ Hedef karşılandı` yazılır, hedef kapanır.
- **İmkânsız** → `✗ Hedef karşılanamıyor: <neden>` yazılır, hedef kapanır.

Duraklama ve sınırlar (`/goal devam` sürdürür, `/goal clear` bırakır):

- **Danışma**: koşu `runtime.goal_checkin_minutes` (varsayılan 30) dakikayı aşınca durur ve
  durumu söyler; her `/goal devam` aralığı ikiye katlar (30 → 60 → 120). `0` danışmayı kapatır.
- **Tur tavanı**: kullanıcı yazmadan en çok `runtime.goal_max_turns` (varsayılan 20) devam turu.
- **Belirsiz karar**: değerlendirici yanıt vermezse otomatik devam durur (kota yakmaz).
- Ctrl-C / Esc / masaüstünde Durdur turu ya da değerlendirmeyi keser; hedef etkin kalır.
  Kullanıcının sırada mesajı varsa (TUI) devam turu ona yol verir; kullanıcı turları da
  değerlendirilir.
- **Yalnız agent motoru**: `/fusion` motorunda hedef kurulmaz ve değerlendirilmez (Fusion turu
  sohbet geçmişine yazılmaz, değerlendirici sonucu göremez). Etkin hedef `/agent` ile dönülünce
  sonraki turda yeniden değerlendirilir.
- Masaüstü yan paneli (Chrome) turları ayrı geçmişle koşar; hedefi değerlendirmez ve devam
  zincirini bozmaz. Zamanlananlar'dan başlayan tur hedef zincirinin tamamı bitince "bitti" sayılır.

Argümansız `/goal` durumu (değerlendirme, otomatik tur, son karar) yazar. Hedef sohbete bağlı
kaydedilir (`memory_dir/oturum-hedef/<sohbet>.json`): `fusion --resume` ve masaüstü sekmesi
yeniden açılınca geri gelir. Masaüstünde karar sohbete ara not olarak düşer ve devam turu kendi
cevabıyla görünür; sırada yazdığın mesaj varsa önce o koşar, hedef onun sonunda yeniden
değerlendirilir. Değerlendirme sürerken sekme meşguldür (yeni tur ve `/cd` bekler). Hedef kipi
yalnız devam turuna uygulanır. Uzaktan (PWA/Telegram) gönderilen görev, hedefi etkin bir
sohbette koşarsa devam turları aynı uzak görevin içinde sürer (ara durum olarak karar metni,
sonunda özetle birlikte son karar); uzaktan iptal zinciri keser. `/goal` uzaktan kurulmaz
(Telegram yalnız kendi komutlarını tanır): hedefi masaüstünde ya da terminalde kur.

## Terminalde dikte: `/voice`

Claude Code `/voice` karşılığı; tanıma **cihaz üstüdür**, ses buluta gitmez ve token harcamaz.

- `/voice` dinler; bir konuşma bölümü bitince (yaklaşık 2 sn sessizlik) metin bir sonraki
  isteme yazılır, düzenleyip Enter'a basarsın. Tam ekran TUI'de kısmi metin giriş kutusunda
  canlı görünür. `/voice gonder` metni doğrudan tur olarak gönderir. Ctrl-C/Esc dinlemeyi keser.
- Tanıyıcı: Fusion masaüstüyle gelen `fusion-listen` (`/Applications/Fusion.app/Contents/Resources/`,
  macOS `SFSpeechRecognizer`, Türkçe destekli). Bulunamazsa açık hata verilir; başka bir
  tanıyıcıyı (whisper.cpp, sherpa-onnx sarmalayıcısı) aynı JSON satır sözleşmesiyle
  `runtime.voice_listener` ayarına yazabilirsin (bkz. `desktop_build/listen/README.md`).
  Dil: `runtime.voice_language` (varsayılan `tr-TR`). Güvenilmeyen proje `config.yaml`'ı
  `voice_listener` taşıyamaz.
- `/voice durum` hangi tanıyıcının kullanılacağını yazar. Bir tuşa bağlamak için
  `keybindings.json` içinde eylem olarak `"komut:voice"` ver. Basılı tutarak konuşma (Space)
  yoktur: terminal tuş bırakma olayı vermez; tek dokunuş kipi kullanılır.
- Terminalden başlatılan yardımcının mikrofon/konuşma tanıma izni macOS'ta terminal
  uygulamana (Terminal, iTerm…) bağlanır; izin yoksa yardımcı hata ya da sessizlik döner ve
  `/voice` bunu "ses algılanmadı" diye bildirir. Masaüstünde `/voice` sohbet kutusunun
  mikrofonunu açar (yeniden yazmak kapatır); `/voice gonder` kesin metin gelince taslağı
  kendiliğinden gönderir; `/voice durum` tanıyıcı ipucunu yazar.
- Yardımcı bir bölümü kesinleştirip ("son") "ses-bitti" göndermezse dikte 2 sn sonra biter;
  90 sn üst sınır dolarsa o ana kadar tanınan metin korunur. Zamanlanmış görev (`/loop`)
  mikrofonu açamaz (`/voice`, `/dikte`).

## Arka plan görevleri ve oturumlar arası mesaj (`/bg`, `/tasks`, `/list-agents`)

```text
/bg tüm testleri koştur ve kırılanları düzelt   # arka planda başlar, terminal serbest
/tasks                                          # girdi bekleyen → çalışan → biten
/tasks answer gorev-1a2b evet                   # onay bekleyen göreve cevap
@gorev-1a2b CHANGELOG'u da güncelle             # devam mesajı (bitmişse yeniden başlar)
/list-agents                                    # açık öteki Fusion oturumları
@backend-oturumu API şeması değişti, testleri koştur
```

Tam ekranda tur sürerken **Ctrl+B** turu keser ve görevi arka planda baştan başlatır
(değişen dosyalar devredilir). Terminalden: `fusion agent --bg
"görev"`, izlemek için `fusion agents --izle`. Ayrıntı ve ayarlar:
[ARKA_PLAN_GOREVLERI.md](ARKA_PLAN_GOREVLERI.md).
