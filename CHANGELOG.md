# Değişiklik günlüğü

Biçim [Keep a Changelog](https://keepachangelog.com/tr/1.1.0/) esaslıdır.
Sürümleme [SemVer](https://semver.org/lang/tr/) uyarınca yapılır.

## Yayımlanmamış

## 0.7.19 — 2026-11-01

### Claude Code / Codex paritesi (31 Ekim 2026)

- İzinler: Claude Code `permissions.allow/ask/deny` kalıpları (Bash, Read, Edit, WebFetch, Agent, mcp__…) dört katmandan okunur ve okuma/web araçlarında da uygulanır; kabuk sarmalayıcıları (`sh -c`, `eval`, `sudo`) kuralı aşamaz. `/permissions`, `fusion permissions` ve Ayarlar › İzinler kural tablosu.
- Korumalı yollar (`.git/`, `.claude/`, `.fusion/tools/`…) her kipte sorulur; `runtime.block_reads_outside_root` / `block_writes_outside_root` klasör dışını sorulmadan kapatır.
- Onay kartı: "Evet, bir daha sorma (kalıcı)" ve "Not ekle" (ret gerekçesi modele gider, tur durmaz); masaüstünde güvenilmeyen proje şeridi.
- Oturum: `fusion --continue` (`-c`), `--resume`, `--fork-session`, `--name`; `/resume`, `/rename`, `/branch`; `/rewind` (Esc Esc) kod ve konuşma checkpoint'i; `--worktree`/`/worktree` git çalışma ağacı izolasyonu ve `.worktreeinclude`.
- Talimat ve beceriler: `~/.claude/CLAUDE.md`, `CLAUDE.local.md`, `@yol` içe aktarma, `.claude/rules` (`paths:` kapsamı); `/ad` ve `$ad` ile beceri/komut çağırma, SKILL.md frontmatter (`allowed-tools`, `disable-model-invocation`, `context: fork`), beceri dizini enjeksiyonu, `/init`, `/doctor prompt`.
- REPL: `!` kabuk, `@dosya` (Tab tamamlama), `#` bellek notu; `/status`, `/context`, `/export`, `/copy`, `/config` + `fusion config get/set/list`, `--set bölüm.alan=değer` ve `--profile`; `/output-style`, `/statusline`, `/theme`, `/tui`, `/search`, `keybindings.json`, `/vim`.
- Bilgisayar kullanımı: Erişilebilirlik ve Ekran Kaydı izin akışı (Ayarlar › İzinler › Bu bilgisayar); ekran görüntüsü 1568 px çerçeveli (Retina kayması giderildi), bölge büyütme ve ekran seçimi; `desktop_mouse` (sağ/çift/üçlü tık, sürükle, hover), yatay kaydırma, tuş dizgisi; tek oturum kilidi; Fusion penceresi görüntüden çıkarılır.
- Tarayıcı oturumu içe aktarma: `fusion browser import-cookies` / `import-chrome` / `login`, şifreli profil deposu, alan adı onayı; `browser_open profile=`; Ayarlar › Web oturumları.
- Fusion Browser eklentisi 0.4.0: konsol ve ağ okuma (debugger izni olmadan), erişilebilirlik ağacı ve doğal dilli arama, `network_idle` bekleme, GIF kaydı, kısayollar, pencere/sekme grubu, Windows/Linux'ta Chrome açma.
- Masaüstü: `.fusion/launch.json` (ve `.claude/launch.json`) ile önizleme sunucusu, konsol/ağ çekmecesi, cihaz boyutlu ekran görüntüsü; tur bitişi/onay için OS bildirimi, okunmamış işareti, Dock rozeti; bölünmüş görünüm, sistem tepsisi, `fusion://` derin bağlantılar; yazı ölçeği, yüksek kontrast, hareketi azalt.
- Alt ajanlar ve bellek: düz metin `BELLEK.md` + `/memory`; ajan tanımı alanları (model, permissionMode, maxTurns, skills, mcpServers, disallowedTools, memory) uygulanır; derinlik/eşzamanlılık ayarı ve ağaç görünümü; `fusion --agent explore|plan`, `/persona`, `/subtask` (bağlamı devralan alt ajan). Alt ajan artık kök dışı okuma/yazma engelini de devralır.
- Uzaktan: `fusion remote-control` ve `/rc` (masaüstü olmadan telefondan sürme, QR), cihaz başına süreli uzaktan onay ve Telegram onay düğmeleri, başlıkta "Uzaktan kontrol" anahtarı.
- Betik ve MCP: `fusion agent --output-format json|stream-json`, stdin görev, `--max-turns`, `--max-budget-usd`, `--allowed/--disallowed-tools`, `--json-schema`, `--bare`; `fusion mcp add|remove|list|login|reconnect`, `.mcp.json` ve `${VAR:-varsayılan}`; `/usage`, `fusion usage`, `fusion insights`; salt-okur `gh` aracı, `/pr`, `/pr-comments`, `/autofix-pr`, `--from-pr`; santralde `/v1/responses`, `/v1/messages`, `/v1/embeddings`.
- Plan ve makrolar: plan kipi `plans/<sohbet>.md` dosyasına yazar ve kabul kartı sunar (`/plan goster`, `/plan ac`); `/simplify`, `/security-review`, `/debug`, `/batch`, `/code-review`; `/loop` ve ajan araçları `cron_create/list/delete`, `schedule_wakeup`.
- Kits: `fusion kit gonder|gelen|liste|durum`, `kit_send` aracı ve `kit.*` RPC'leri; Kit'ler kullanıcının Chrome'unu Fusion onayıyla kullanabilir (`docs/KITS_KOPRUSU.md`).

#### 2. dalga

- Bilgisayar kullanımı: Ayarlar › Bu bilgisayar (aç/kapat, kademe tavanı yalnız bak / tıkla / tam kontrol, reddedilen uygulamalar, uygulama başına kademe; `fusion config set desktop.<alan>`). Uygulama başına oturum onayı ("Bu oturumda Mail için izin ver", "Her zaman reddet"); tarayıcılar yalnız bak, terminal ve IDE'ler tıkla kademesinde; yatırım/kripto ve parola yöneticisi uygulamaları ile Fusion'ın kendi penceresi kapalı.
- Gönder/sil/öde düğmeleri, Terminal'de ve sohbet uygulamalarında Enter, Sistem Ayarları her seferinde sorulur. Fiziksel Esc turu durdurur; "Fusion bilgisayarı kullanıyor" şeridi; isteğe bağlı olarak tur süresince diğer uygulamaları gizleme.
- Kancalar (hooks): PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionStart, SessionEnd, Notification, PreCompact; Claude Code `settings.json` `hooks` bloğu çalışır, çıkış 2 engeller, kancalar izin kurallarını gevşetemez; `fusion hooks list|test`, `/hooks`; güvenilmeyen projede kapalı.
- Kabuk sandbox'ı: okuma engeli (~/.ssh, ~/.aws…), alan adı allowlist'li ağ proxy'si, ek yazma dizinleri, Linux bubblewrap, `fail_if_unavailable`; sandbox dışı çalıştırma her seferinde sorulur; `/sandbox`, `fusion sandbox`, Ayarlar › İzinler kartı. `.git/config`, `.git/hooks`, `.mcp.json` sandbox içinden yazılamaz.
- Otomatik kip denetçisi (varsayılan kapalı, `/auto-mode ac`): sorulacak işlemi küçük model kullanıcının isteğine göre değerlendirir; üst üste 3 / toplam 20 riskli kararda oturum Manuel'e düşer; uzak silme komutları her zaman sorulur.
- Masaüstü: Tarayıcı paneli (ajanın tarayıcısını canlı izle, Devral / Ajana bırak, öğe seçici); önizlemede https://localhost ve `autoPort`; CLI'de `/tarayici ac`.
- Masaüstü: ⌘K komut paleti, ⌘P dosyaya git, ⌘N, ⌘,, ⌘B, ⌘J, ⌘1-9 kısayolları ve Ayarlar › Kısayollar (keybindings.json `masaustu` bölümü); `fusion://` Windows/Linux'ta da çalışır.
- Arka plan ajanları: `fusion agent --bg`, `fusion agents`, `/bg`, `/tasks`, tam ekranda Ctrl+B; `spawn_agent(arka_plan=true)`, `list_agents`, `send_message`, `stop_agent`. Oturumlar arası mesaj: `/list-agents`, `@oturum mesaj` (gelen mesaj güvenilmez girdi, varsayılan bekletilir).
- Ajan ekipleri (`team_run`, `/team`, `fusion ekip`: lider + üyeler, ortak görev listesi, posta kutusu) ve dinamik iş akışları (`workflow_run`, `/workflows`: JSON tanımla paralel/sıralı alt ajanlar, bütçe ve iptal).
- Eklentiler: `fusion eklenti` / `/plugin` ile Claude Code biçimli eklenti paketleri ve pazar yerleri (beceri, komut, ajan, çıktı stili, kanca, MCP); değişen eklenti yüklenmez. `/import` ve `fusion import` ile Claude Code, Codex, Gemini CLI ve Cursor'dan MCP, izin, komut ve kural taşıma; `/release-notes`.
- `/goal <koşul>`: koşul karşılanana kadar turlar kendiliğinden sürer (hakem modeli değerlendirir); `/cd <yol>` çalışma dizinini değiştirir (`Cd(...)` izin kuralı); `/voice` cihaz üstü dikte; aralıksız `/loop` kendi temposunu seçer.
- Beceriler: `capabilities.overrides` ile görünürlük, becerinin `model`/`effort` alanı o turda uygulanır, monorepo alt klasör becerileri; MCP istemleri `/mcp__sunucu__istem` ve kaynakları `@sunucu:uri`; oturum PR'a bağlanır ve durum satırında görünür.
- Kits: bilgisayar panelinde canlı izleme ve GIF kaydı.

#### 3. tur (1 Kasım)

- Web model oturumunun (ChatGPT/Claude/Gemini/Copilot) seçilen siteleri ajan tarayıcı profiline tek yönlü ve onaylı kopyalanır: `fusion browser import-web-session`, `/oturum-aktar`, Ayarlar › Web oturumları › Model oturumundan aktar; otomatik paylaşım yok, iç ağ adları reddedilir.
- Kit'ler bir Fusion tarayıcı profilini yalnız istenen siteler için, her seferinde onayla ve bellek içi kendi tarayıcılarına yükler (`fusion_profile`).
- Sandbox: `sandbox.deny_read` artık varsayılan okuma engeline eklenir (varsayılandan yol açmak için `sandbox.allow_read`); Fusion'ın web profil Chrome'unun hata ayıklama (CDP) portu sandbox'taki komutlara kapalı; ağ proxy'si komut başına açılır ve komut/iş bitince kapanır.
- Kancalar: `/cd` CwdChanged olayını tetikler; ekip görevleri TaskCreated/TaskCompleted/TeammateIdle ile denetlenir; `http` türü kanca (iç ağ korumalı), boşta bekleme bildirimi (`idle_prompt`), özetleme sonrası SessionStart(compact); kanca dökümünde araç çağrıları; `/reset` yeni oturum kimliği verir.
- `team_run(arka_plan=true)`: ekip arka plan görevinde koşar, lider sohbete devam eder.

- "web push bildirimi", "pushState" gibi isim olarak geçen push artık modeli atlayan git push akışını başlatmaz.
- Gateway bu bilgisayar dışından gelen isteği yalnız belirteçle kabul eder; belirteçsiz ağ bind'i başlamaz (`fusion serve --token`).
- Güvenilmeyen projenin `config.yaml` ve `.fusion/tools` dosyaları MCP süreci, doğrulama komutu veya araç çalıştıramaz; yeni komut `fusion trust`.
- Geri alma kullanıcının commit'lenmemiş işini silmez: yalnız Fusion'ın değişikliği geri alınır, sonradan değişen dosyada çatışma bildirilir.
- Kesilmiş önizleme tam dosya olarak kaydedilemez.
- Kod çalıştıran awk, dosya yazan sed ve dal silen git komutları salt-okur sayılmaz; `git stash drop`, `npm run deploy` ve `curl --json` sorulur.
- Sohbetteki uzak görseller kullanıcı yükleyince istenir; güvensiz bağlantı şemaları çizilmez.
- Telefondan hesapla giriş yapan cihaz o hesaba bağlanır; başka hesabın telefonu masaüstündeki görevleri göremez, iptal edemez, onaylarını cevaplayamaz ve görev başlatamaz.
- Telefon görevleri kalıcıdır: bilgisayar yeniden başlayınca yarım iş "Sonuç belirsiz" görünür ve kendiliğinden tekrar çalıştırılmaz; aynı istek anahtarı farklı içerikle reddedilir; iptal "Durduruluyor" ile başlar, tur gerçekten bitince "İptal" olur.
- `FUSION_WORKSPACE_ISOLATION=1` ile bellek, sır deposu ve tarayıcı oturumları hesaba göre ayrılır; eski ortak veri `fusion adopt-data <hesap>` ile tek bir hesaba kopyalanır.
- Arayüz istekleri son süre ve iptal alabilir; çalışma alanı okumaları 30 sn'de zaman aşımına uğrar.
- Test geçtikten sonra kabukla yapılan dosya değişikliği (`sed -i`, `> dosya`, `cp`) eski başarıyı geçersiz kılar; görev yeniden doğrulama bekler.
- Uzun oturumda bağlam özetlenirken kullanıcının koyduğu kurallar ("asla main'e push etme") özete birebir taşınır.
- Ajanın dosya düzenlemesi CRLF satır sonlarını korur.
- Telefondan ekran izleme masaüstü onayıyla açılır; "hatırla" 7 günlük güven verir. Telefon, işlemin gerektirdiği yetki (ör. `project.write`) olmadan yazma/komut onayı veremez, yalnız reddedebilir.
- Önizleme sunucusu, başka bir sürecin tuttuğu portu boş sanıp açılamamazlık etmez.
- Telefon eşleştirmesinde yanıt ağda kaybolursa telefon aynı cihazı yeniden alır; sırrı hiçbir telefona ulaşmamış "hayalet" cihaz kendiliğinden iptal edilir.
- Chrome yerel bağlantısı yalnız gerçek Fusion Browser eklentisine açılır; aynı adı taşıyan başka bir eklenti kabul edilmez.
- Tarayıcıda tıklama/yazma sonucu gelmezse ajan "sonuç bilinmiyor" görür ve işlemi körlemesine tekrarlamaz; alana yazılan anahtar/belirteç adım günlüğünde gizlenir.
- Tarayıcıda sayfa değiştikten sonra eski öğe referansı yeni sayfada başka bir öğeye tıklamaz; ajan sayfayı yeniden okumaya yönlendirilir (Fusion Browser 0.3.12).
- Web modelinin düzgün kapattığı araç çağrısı bloğu "kapanmamış" sayılıp yeniden istenmez.
- Masaüstü sürümü lint/tip/test kapısı geçmeden yayımlanmaz.
- Masaüstü uygulaması sıkı içerik güvenlik politikasıyla çalışır; arayüz dosya içeriğini ağ isteğiyle okuyamaz, `.ssh`, `.aws`, tarayıcı profilleri ve `.env` gibi hassas dosyalar uygulama içi görüntülemeye kapalıdır.
- Uzak MCP sunucusu giriş ayarlarıyla Fusion'ı iç ağdaki adreslere (bulut metadata, yerel cihazlar) istek atmaya yönlendiremez; eklenen sunucunun kendi adresi dışındaki her hedef genel bir HTTPS adresi olmalıdır.
- Finder'dan açılan uygulamada Homebrew'la kurulu `npx`/`uvx` MCP sunucuları bulunur; "kurulu değil" hatası verilmez.
- MCP sunucusunun "çok fazla istek" (429) ve "zaman aşımı" (408) yanıtları geçici sayılır; bağlantı oturum boyunca kapatılmaz.
- Web sayfası okuma, site tarama ve dosya indirme denetlenen adrese bağlanır: alan adı denetimden sonra iç ağa çözülse de (DNS rebinding) istek gitmez; Tailscale/CGNAT (`100.64.0.0/10`) ve IPv6'ya gömülü iç adresler de engellenir.
- Model kimliksiz ya da aynı kimlikli birden çok araç çağrısı gönderdiğinde her çağrı çakışmayan bir kimlik alır; sonraki tur sağlayıcı tarafından reddedilmez.
- NIM gömme modeli değiştirilince vektörler eski modelin koleksiyonuna eklenmez; her model kendi koleksiyonunu kullanır, varsayılan modelin mevcut dersleri ve kod indeksi korunur.
- Kod indeksi parça sınırına takılınca "İndeks kısmi" uyarısı verir; dışarıda kalan dosyalar sessizce kaybolmaz.
- Kitaplıkta yüklenemeyen dosyanın hatası, ardından gelen liste yenilemesiyle silinmez.
- Telefonun ekran izleme ekranındaki eski "bu telefonda onay ver" metni düzeltildi; izin masaüstünden istenir.
- Günlük ve haftalık zamanlanmış görevler yaz saati geçişinde yerel saatinde kalır (önceden geçişten sonraki gün bir saat kayıyordu).
- Görsel işlerinin yerel kaydında tek bir bozuk kayıt artık sohbetteki bütün bekleyen işleri ve yeni üretimi kilitlemez; bozuk kayıt karantinaya alınır.
- Komut iptali, kendini ayrı oturuma alan (`setsid`) ve çıktıyı açık tutan torun süreçleri de kapatır; geride çalışan süreç kalmaz.
- Güvenlik: `rm --recursive --force`, `sh -c 'git push'`, `eval`, `curl | zsh`, `git restore .`, `git checkout .` ve uzaktan `npx`/`pnpm dlx` paketleri artık onaysız çalışmaz; agent'ın yazdığı betik riskli içerik taşıyorsa çalıştırılmadan önce sorulur.
- Güvenlik: tarayıcı araçları yönlendirme ve alt kaynak isteklerinde de iç ağ adreslerini engeller; dosya yazan araçlar alt ajan yazma alanını aşamaz; önizleme sunucusu gizli dosyaları ve yabancı Host'u reddeder.
- Güvenlik: tehlikeli işlemlerde boş Enter onaylamaz; güvenilmeyen projenin `.claude/settings.local.json` izinleri `fusion trust` olmadan uygulanmaz (eski güven kayıtları için yeniden `fusion trust` gerekir).
- Güvenlik: git push sırlı origin adreslerini ve anahtar dosyalarını kayda/commit'e almaz; dış bellek dosyaları maskelenir; sır deposu atomik yazılır.
- Güvenlik: web öğretmenine sır dosyaları ve proje dışı dosyalar gönderilmez, gönderilenler gösterilir; proje dışına dosya yazma otomatik kipte sorulur.
- Güvenlik: MCP sırları terminal ve `run_shell` çocuklarına geçmez; hata raporu ve denetim günlüğü GitHub belirteçlerini, Basic kimliği ve adreslerdeki parolaları da gizler.
- Onay kartı yazarken beliriyorsa ilk 600 ms'deki rakam/Enter karar vermez; Escape yalnız en üst pencereyi kapatır; seçeneksiz onay kartı kilitli kalmaz.
- İzin modu sohbet başına tutulur; çekirdek reddederse eski mod ve hata görünür. Zaman aşımı, iptal ve bilinmeyen araç sonuçları başarılı görünmez.
- Doğrulama kapısı son düzeltmeyi de ölçer; modelin art arda boş yanıtı başarı sayılmaz; paralel araç sonuçları bağlam temizliğinde korunur.
- Doğrulama komutu zaman aşımında, iptalde ve arka plan çocuğu varken takılmaz; torun süreçler de kapatılır. `git add && git commit`, `cd x && git commit` ve `pytest 2>&1` kanıt sayılır.
- Uzak görevler takılı kalmaz: zaman aşımı ve kök/model hatası görevi başarısız yapar; Telegram köprüsü beklenmeyen hatada kopmaz.
- Büyük dosya okuma ve git sorguları arayüzü dondurmaz; proje kökü doğrulanır, kök değişince ek klasör izinleri sıfırlanır.
- Esc ile kesilen turun geçmişi ve `/undo` kaydı korunur; borulu kullanımda TUI açılmaz.
- Talk: kesilen konuşmanın eski sesi yeni konuşmayı ezmez; sesli onay Fusion'ın kendi sesinden gelen yankıya, kimliksiz ve 2 dakikadan eski sorulara karşı korunur.
- Görsel üretimi sürerken yazılan yeni istem silinmez; akışta dosyası silinmiş üst düğüm yeniden üretilir, eksik referans arayüzü kilitlemez.
- Geçerli Godot 4 `project.godot` (config_version, uid ana sahne) reddedilmez; bozuk Remotion kiti kabuğu kilitlemez; favicon 404'ü ve WebGL canvas yanlış hata üretmez; Remotion videosu gerçek dosya, süre ve çözünürlük kanıtıyla doğrulanır, videoya sabit "Fusion" adı eklenmez.
- Zamanlanmış görevde tek teslim hatası sıradakileri durdurmaz; etkin sohbet kapansa da açık başka oturum üzerinden alınır.
- Zaman aşımıyla iptal edilen model çağrıları maliyet özetinde "en az" diye işaretlenir, sıfır sayılmaz.
- Masaüstü kabuğu: bozuk `active-runtime.json` açılışı ve "Onar"ı engellemez (`.corrupt` olarak yedeklenir); çekirdek ya da ses çıktısındaki geçersiz bayt sonraki satırları susturmaz; takılan terminali kapatmak ve yoğun yazım uygulamayı dondurmaz; çekirdek durdurulurken alt süreçleri de sonlanır (macOS/Linux).
- Çekirdek makbuzu gelmese ya da reddedilse de tur çıktısı görünür; açılışta bağlanamayan kayıtlı sekmeler silinmez, uyarıyla gösterilir; dosya okuma hatası dosya ağacını gizlemez; artık cevap beklemeyen soru kartı kapanır.
- Sesli konuşmada araya girildikten sonra mikrofon sağır kalmaz; Esc menüyü kapatırken ya da turu durdururken sağ paneli kapatmaz; talimat kaydı hataları görünür, okunamayan talimatın üzerine yazılamaz.
- Hesap kurtarma kodu her koşulda gösterilir, pano çalışmasa da devam edilebilir; bağlantı araması GitHub, Notion ve Shopify'ı bulur; beceri listesi tek bozuk öğede boşalmaz; sunucuda kaybolan görsel işi panelden unutulabilir.
- Bellek bir koleksiyon takılınca tamamen kapanmaz, yazılamayan kayıt "eklendi" denmez; akışlı gateway yanıtlarında ve uzak olaylarda sırlar maskelenir; MCP araç hata mesajları modele iletilir; Gemini tarayıcı oturumunda görseller eklenir.
- Sistem istemlerindeki dil ve ilerleme anlatımı çelişkileri giderildi; plan şeması tek geçerli örnek ve `c1`/`c2` kimlikleriyle zayıf modellerde daha az reddedilir; Remotion kart başlıkları uzun Türkçe sözcüklerde bölünmez.
- Sürüm Release'i yüklenen bütün dosyalar için SHA256SUMS, SBOM ve manifest içerir; terminal (PTY) testleri CI'da ayrı işte koşar.
- Görev kutusu: sohbet kipinde Shift+Tab izin modunu değiştirmez; gönderim sırasında yazılan metin korunur, reddedilen gönderim hata gösterir; panodan görsel ek olarak eklenir; açık `@` listesi Esc ile önce kendini kapatır; "/Users/x/main.py incele" gibi yolla başlayan mesaj komut sayılmaz.
- Sohbet arayüzü: sabit sohbetler proje taşınınca kaybolmaz; bozuk proje tercihi ya da tema okuma hatası boş pencere bırakmaz ("yeniden yükle" ekranı); araç/kaynak/önizleme adresleri yalnız http(s) açılır; kritik bağlam doluluğu ayrı renkte; iş sürerken bağlam kartından `/compact` gönderilmez.
- Terminal sekmeleri başka sekmeye geçince kapanmaz; kabuk ve araç çıktısındaki API anahtarı/Authorization değerleri maskelenir; kayıtlı API anahtarı yalnız göz düğmesiyle görünür.
- Sohbet açılırken geç gelen geçmiş ve iptal edilen turun yarım yanıtı kaybolmaz; saklı sohbetler tüm açık projelerden listelenir; 200'den fazla dosyalı klasörler tam listelenir.
- Zamanlama: günsüz haftalık, geçmiş tarihli ve çok kısa aralıklı görevler reddedilir; silme onay ister.
- Talk: tek komut modunda düşünme ipucu çalar, yanıt gelmezse 90 sn sonra hata gösterir, kalıcı tanıma hatasında mikrofon döngüye girmez; sesli "evet" onay kartındaki "İzin ver"i onaylar; eski macOS WebView'lerinde modül kırılmaz.
- Ayarlar: Esc kaydedilmemiş talimatı silmez, arama Ses/İzin/Model bölümlerini bulur, port 1-65535 doğrulanır, "İzinleri atla" onay ister, Chrome eşleştirme anahtarı varsayılan gizli; çalışan görev varken uygulama güncellemesi kurulamaz.
- Görsel oluştur: sayfa değişince istem korunur, üretimde Durdur düğmesi var, bozuk kayıtlı akış arayüzü çökertmez; Bağlantılar'da "Yeniden dene", hata nedeni ve "Vazgeç" var.
- Onay kartı `multi_edit` ve silme düzenlemelerinde de fark gösterir; uzun/sırlı argümanlar kısaltılıp maskelenir; ayar kaydı diske yazılamazsa uyarı döner.
- Chrome eklentisi: kapalı eklenti "yüklendi" sayılmaz, kesilen kopyalama mevcut eklentiyi bozmaz, tuş vuruşları yalnız Chrome öndeyken gönderilir; kod kipindeki panel görevi kod araması yapabilir.
- Uzun boşluksuz metinde sır maskeleme artık dakikalarca sürmez; hata raporu Stripe, Groq, Hugging Face, Google OAuth ve JWT anahtarlarını da gizler; Langfuse'e giden veriler sırlardan arındırılır.
- Ajan: büyük harfli Türkçe istekler ("İNCELE", "SİL") doğru tanınır; zayıf modellerin tip kaymaları (`"true"`, `"1920"`, boş/çitli JSON argüman) ve Claude/Cursor/Windsurf araç adları araçları düşürmez; `council` tur başına 3 çağrıyla sınırlı.
- Öğretmen ulaşılamayınca "Öğretmen devre dışı" bildirimi gelir; öğretmene kimlik dosyalarının (`.env.local`, `id_rsa`, `*.pem`) adı ve farkı gitmez; depo talimatı etiketi kapatılıp sahte talimat eklenemez.
- Doğrulama: çöken tek kapı tüm doğrulamayı düşürmez, atlanan tarayıcı/PHP/görsel denetimi uyarıda görünür; Playwright yoksa "ölçülemedi" denir; keşif `.venv` araçlarını, `cargo check`/`go vet`'i ve uv/poetry/tox/npm `test:*` koşucularını kullanır; zaman aşımına uğrayan komut başarı iddiasını engeller.
- Plan ayrıştırıcı "bağımlılık yok" için `""`/`null`/`"yok"` yazan planı düşürmez; plan modunda ödeme ve silme adımları onaysız planlanamaz.
- Dosya araçları FIFO/aygıtta kilitlenmez; `list_dir` kırpmayı bildirir; görsel dönüşümü saydamlığı korur; arşiv açma şifreli/kesik arşivde çökmez; `tsconfig.json`, yorumlu JSON ve çok belgeli YAML yazımı reddedilmez; büyük dosyada fark özeti verilir.
- Komut politikası: `grep -r x .*`, `tail -f`, `top`, `git rebase`, `DROP TABLE` ve `osascript` tuş otomasyonu sorulur; `npm --version` ve `git commit -m "fix reboot"` sorulmaz.
- `web_fetch` ikili içeriği metne çevirmez, `web_search` boş sonucu hata sayar; önizleme sunucusu çökünce 45 sn beklemez, hata çıktısını gösterir; site kopyalamada "199,90 TL" fiyatları ve Türkçe kategori adresleri desteklenir.
- MCP: uzak araç adları sağlayıcı kuralına uydurulur; giriş akışı yabancı istekte düşmez, tarayıcı açılamazsa adres gösterilir; takılı oturum 3 zaman aşımından sonra yeniden bağlanır; listedeki gömülü anahtarlar maskelenir.
- Sağlayıcılar: kesik araç argümanı ve çöken akış sessizce kaybolmaz; anahtarsız sağlayıcı ve girişsiz Codex yedek zincirinden ayıklanır, Codex iptalde süreci öldürür; web sağlayıcıda iptal sonrası mesaj iki kez yazılmaz; Ollama adresi `OLLAMA_HOST`'tan okunur.
- Bellek: kod indeksi sırları maskeler ve `build/` adlı üst klasörde boş kalmaz; Türkçe İ/I aramada eşleşir; ders metni istem bloğunu bozamaz; tur günlüğü argümanları geçerli JSON bırakarak maskeler.
- Uzak erişim: Tailscale adresine doğrudan bağlanılabilir; cevaplanmayan onay 30 dakika sonra reddedilir; yüksek yetkili kapsamla eşleştirme her zaman masaüstü onayı ister; telefonda gönderim hatasında metin kaybolmaz.
- Masaüstü kabuğu: gömülü terminal giriş kabuğu olarak açılır (Homebrew/nvm araçları görünür); Kits kapanışta donmaz, gizliyken yoklama yapmaz; Windows çalışma zamanı `%LOCALAPPDATA%`'ya uyar; çalışma zamanı kurulumu zaman aşımlı.
- CLI: uzun yol ve komutlar araç kartında ortadan kısaltılır; `fusion uninstall --purge` onay ister (`--yes`); `--quiet` önemli uyarıları yutmaz; `fusion agent` başarısızlıkta sıfırdan farklı çıkış kodu verir; hata satırları stderr'e yazılır; `/providers add` anahtarı aynı oturumda etkin olur.
- Hesaplar: kurtarma kodu 80 bit oldu (eski kodlar çalışır), giriş ve sıfırlamada hesabın varlığı süre farkından anlaşılmaz; avatar yeniden seçimi mevcut avatarı silmez.
- Gateway paneli iframe'e gömülemez; kaydedilmemiş zincir/hakem değişikliği otomatik yenilemede silinmez; web oturumu kartı model ve sağlayıcı adlarını kaçışlar; "Araç yeteneğini ölç" kota harcadığı için onay ister.
- Kitaplıkta arama gecikmeli ve son istek kazanır; Woo aktarımı kök dışı görseli kopyalamaz, fiyatsız ürünü taslak bırakır; web iskelesi `style.css` ve `script.js` taslaklarını yazar; Claude geçmişi boşluklu/noktalı klasör adlarında da bulunur.
- Onaylar: sohbet silme, Kits'in mikrofonu ilk kez açması, doğrulanmamış ya da hazır olmayan model seçimi, Chrome panelinden "İzinleri atla" ve proje test komutunun ilk çalıştırılması onay ister; hesap silme parola ya da kurtarma kodu ister; cevapsız onay kartı 30 dakikada reddedilir.
- "İzinleri atla" kipinde uzakta geri alınamaz araçlar (silme, yayın, harcama) yine her seferinde sorulur; `cp`/`mv`/yönlendirme ile ezilen proje dosyası geri alınabilir; MCP sunucusunun araç tanımı değişince yeniden onay istenir.
- Zamanlanmış görevler kök ya da ev klasöründe çalışmaz, "İzinleri atla" kipinde başlamaz; onay bekleyen tur askıda bekler ve sistem bildirimi gelir; hiç sohbet açık değilken de uygulama açıkken vadesi gelen görev alınır, birden çok pencerede çift teslim olmaz.
- Telefon ve masaüstü yalnız Fusion klasörlerindeki ve proje klasörlerindeki görselleri görebilir; telefon eşleştirme verisi `~/remote` yerine Fusion veri klasöründe tutulur (eski dosyalar otomatik taşınır).
- Sır deposu scrypt ile şifrelenir ve macOS'ta ana anahtar Keychain'de saklanır; eski depo ilk açılışta yedeklenip yükseltilir (eski anahtar `master.key.migrated` olarak kalır). Hesap girişi, silme ve kurtarmada art arda hatalı denemeden sonra artan bekleme uygulanır.
- Yeni isteğe bağlı ayar `runtime.shell_sandbox: write_root` (macOS) komutların yazmasını proje klasörü ve geçici dizinlerle sınırlar; varsayılan kapalı.
- Varsayılanlar: hakem 20 sn, model yeniden deneme 4 (hız sınırında paylaşılan soğuma beklenir), tur başına 400 model çağrısı, otomatik web yedeği kapalı, öğretmen için ayrı 300 sn zaman aşımı ve tek yeniden deneme; 30 günden eski iz, artifact ve tamamlanmış checkpoint'ler temizlenir.
- Plan: bütçeyi aşan adımın doğru işi geri alınmaz, doğrulanıp duraklatılır ("sürdür" ek bütçe verir); yeniden planlama teslimat düşüremez; playbook onay kipine uyar; salt-okuma adımı doğrulama kapısını yeniden koşmaz; README/tek satır düzenlemeler öğretmen planı beklemez.
- Doğrulama: Playwright yoksa HTML oyun teslimi "doğrulanamadı" uyarısıyla geçer; kanıtsız eylem uyarısı cevabı silmez; akordeon/ilerleme çubuğu boyut geçişleri engel değil uyarı; kapsanmayan alt proje (ör. `app/`) uyarıda görünür; Manuel/Plan kipinde dev sunucusu otomatik başlamaz.
- Masaüstü: Fusion ikinci kez açılınca mevcut pencere öne gelir; Cmd+Q da kapatma sorusu açar, arayüz yanıt vermezse 10 sn sonra kapanır; terminal ham bayt kanalıyla daha akıcı; HTML önizlemede sayfanın kendi betikleri paketli uygulamada da çalışır (ayrı kökenli `fusion-preview://`).
- Model seçimi yapısal istekle yapılır; API anahtarı komut metnine katılmaz, `/providers add` ile yazılan anahtar sohbet kaydında gizlenir; görsel "İndir" var olan dosyanın üzerine yalnız kayıt penceresinde onaylanınca yazar; Ayarlar'a "Kurulumu yeniden aç" eklendi.
- Küçük bağlamlı modelde masaüstü/Chrome araçları gizlenir; MCP sunucusuna `allowed_tools` ve `max_tools` eklendi; araç sonuçlarındaki sahte araç çağrısı işaretleri çalıştırılmaz; ana ve alt ajan web oturumunda birbirinin sohbetini düşürmez; panelde her web hesabı ayrı kart.
- `<thinking>`/`<reasoning>` düşünme etiketleri gizlenir, kapanışsız etiketten sonraki cevap kaybolmaz; Godot kapısı `GODOT_BIN` ve uygulama paketinden de çalışır; site kopyalama telif/izin uyarısı verir.
- `edit_file`/`multi_edit` eski metin dosyada satır sonu boşluğu, girinti ya da CRLF farkıyla duruyorsa, tek ve belirsiz olmayan eşleşmede düzenlemeyi uygular ve bunu modele bildirir; onay kartı gerçek farkı gösterir (`runtime.edit_fuzzy_match`). JS/TS/PHP dosyası kaydedilince sözdizimi hatası aynı turda bildirilir (`runtime.post_edit_syntax_check`).
- Eski araç sonuçları eşik beklenmeden modele kısa yer tutucu olarak gider, son 8 sonuç ve hatalar tam kalır, geçmiş kaydı değişmez; yer tutucudaki okuma yeniden istenince tekrar kapısı engellemez (`runtime.tool_output_window`, 0 = kapalı). Küçük modellerde bağlam sıkıştırması pencerenin %20'sinde başlar (`runtime.weak_model_compaction_ratio`).
- Zayıf/küçük modele görev türüne göre (soru, kod, web, medya, masaüstü) daha küçük bir araç listesi gösterilir (soru görevinde 37 yerine 12 araç); liste konuşma boyunca yalnız genişler, gizli araç çağrılırsa o tur açılır (`runtime.weak_model_tool_profiles`). Her model çağrısında sunulan araç sayısı ve şema boyutu iz kaydına yazılır.
- Ajan var olan bir testi zayıflatırsa (skip/xfail ekleme, assert ya da test silme, CI/test komutunu değiştirme) rapor "şüpheli test değişikliği" uyarısı verir ve "testler geçti" kanıtı tek başına doğrulama sayılmaz (`runtime.test_tamper_check`); test ya da şartname hatalı görünüyorsa ajan durup bildirir.
- Web, tarayıcı, MCP ya da klonlanan site okunan turdan çıkan dersler düşük güvenle "dış kaynaklı" kaydedilir ve dış içeriksiz başarılı bir turda doğrulanana kadar güven kazanmaz (`runtime.external_lesson_confidence`).
- Doğrulama iki düzeltmeden sonra da başarısızsa ve yapılandırmada daha güçlü bir model varsa (varsayılan kurulumda Nemotron 3 Ultra) o modelle tek bir ek düzeltme turu yapılır; durum satırı ve rapor notu görünür (`runtime.escalate_on_gate_failure`, `runtime.escalation_model`).
- Depo haritası içe aktarma grafıyla sıralanır: çok kullanılan dosyalar öne, test dosyaları geriye; bütçesi `runtime.repo_map_chars` ile ayarlanır (varsayılan 3.000 karakter, küçük pencereli modelde daha az). Model alt klasördeki bir dosyaya eriştiğinde o klasörün `AGENTS.md`/`CLAUDE.md` talimatı bir kez bağlama eklenir (`runtime.nested_instructions`).
- Yeni komutlar `fusion eval taslak-uret | taslaklar | kabul | sil`: konuşmalardaki düzeltme, geri alma ve başarısız turlardan sırları maskelenmiş eval görevi taslağı üretir; kümeye ekleme kullanıcı onayıyla.
- Gemini web: menüdeki mod pasifse tıklama beklenmez; "strict" seçimde yedek modele geçilir ("'3.1 Pro' modu şu an kullanılamıyor"), diğer seçimlerde mevcut kiple devam edilir. Web oturumu hatasında devre hemen açılır ve birkaç dakika boyunca her çağrıda yeniden denenmez; öğretmen de aynı turda ikinci kez denenmez. Ekrana ham Playwright günlüğü basılmaz. Uzun görev metni Gemini'ye `fusion-gorev-metni.txt` ekiyle gider ve proje dosyası sanılmaz.
- Tur sonu: geçen doğrulama ekranda görünür (`✓ doğrulandı: tarayıcı … · testler 4/4`, ölçülemeyenler nedeniyle); değişen satırların gerçek özeti gösterilir; tur sonu bağlam özeti asılırsa en geç 120 sn'de bırakılır (tur artık sonsuza dek beklemez); test sonrası çalışan komut kanıtı eskitirse rapor nedeni ve yeniden test gerektiğini söyler.
- Öğretmen çağrı bütçesi sayacı proje klasörü yerine kullanıcı veri dizininde tutulur (eski `.fusion/ogretmen-butce.json` taşınır). MCP bağlantı hatası sunucu adı ve kısa nedenle bir kez gösterilir. Boş `⏺` satırları, web modelinde "0 token · $0.0000", anlamsız "18 → 18 mesaj" ve salt-okur görevdeki anlamsız öneriler kaldırıldı.
- Yeni komutlar `fusion prompt-opt calistir | oneriler | uygula | geri-al`: istemlere küçük, eklemeli öneri üretir, ayrı tutulmuş kümede gerilemiyorsa önerir; istem dosyası yalnız `uygula` ile değişir ve geri alınabilir. Örtüşen ya da çok küçük kümeler model çağrılmadan reddedilir.

## 0.7.18 — 2026-10-21

- Araç çağırmadan "yapıyorum" diyen model, turu başarısız kapatmadan önce üç kez kademeli ve somut uyarıyla araca yönlendirilir.
- Platformlar arası test ve denetim farkları giderildi.

## 0.7.17 — 2026-10-21

- Codex sohbeti devralınırken oturumun çalıştığı klasörler bulunur, erişime açılır ve proje köküyle uyuşmazlık modele bildirilir.
- Proje kökünde bulunamayan dosya Belgeler, Masaüstü ve İndirilenler'de aranır; çoklu eşleşmede kullanıcıya sorulur.
- Dosya hiçbir yerde yoksa gizli ve bağımlılık klasörlerinde aramadan önce her onay kipinde kullanıcıya sorulur.
- Soru kartı kompakt hale getirildi.
- Windows'ta bellek deposu kilidi ve çok platformlu tip denetimi düzeltildi.

## 0.7.16 — 2026-10-20

- Devralınan sohbetlerde devam isteği asıl görevin araç kanıtıyla değerlendirilir.
- Araç kullanmadan iş yapıldığını söyleyen yanıtlar doğrulanır; kanıtsız başarı kaydedilmez.
- Aynı başarısız araç çağrısının sınırsız tekrarı durdurulur; düzeltilen önkoşullar yeniden denemeye izin verir.
- Boşluk içeren proje dizinlerindeki kabuk hataları, doğru tırnaklı yolu ve göreli yol kullanımını gösterir.
- Sohbet geçmişi, çalışma adımları, pencere kontrolleri ve panel düzeni güncellendi.
- Kaynak dağıtımı, kurulum belgeleri ve geliştirme ortamı temizlendi.

## Yayımlanmamış — Chrome eklentisi kurulumu ve paneli

- Ayarlar → Tarayıcı'ya **Eklentiyi kur** eklendi (`fusion chrome-kur`): eklentiyi kalıcı klasöre
  kopyalar, yerel mesajlaşmayı kaydeder (macOS ve Windows), Chrome'u açar; yüklü/eşleşti
  durumunu doğrular. Eklenti kimliği `manifest.json` anahtarıyla yoldan bağımsız sabitlendi.
- Yan panel Kits dilinde yenilendi (sistem yazı tipi, nötr vurgu, açık/koyu tema); ekran, fare ve
  klavye adımları için denetim şeridi ve izin kipi özeti eklendi.

## Yayımlanmamış — ses motoru: EMA Lightning

- Sesli yanıt motoru Piper yerine EMA Lightning (Türkçe, Apache-2.0, ~34 MB) oldu.
  Model ONNX'e çevrilip uygulamaya gömüldü: PyTorch ve ilk kullanımda indirme gerekmez,
  çevrimdışı çalışır. Resmî PyTorch motoruyla çıktı örnek örnek eşleşir (en büyük fark 9e-5).
- EMA tek sesli ve tek parametrelidir: "Robotik" sürgüsü ve "Piper ses modeli seç" düğmesi
  kaldırıldı; eski ayar dosyasındaki `robotik` ve `model` alanları yok sayılır.
- Model dosyaları eksikse macOS sistem sesine düşülür ve sebebi söylenir.
- Yeni bağımlılık: `normalizer-tr==0.8.0` (sayı/tarih okuma); `piper-tts` kaldırıldı.

## Yayımlanmamış — onay ve soru güvenilirliği

- MCP araç ipuçları çeliştiğinde Fusion açık `destructiveHint=true` değerini
  `readOnlyHint=true` değerinden önce değerlendirir. Bu, Fusion'ın ihtiyatlı
  ürün politikasıdır; farklı bir öncelik kullanan istemcinin MCP standardını
  ihlal ettiği anlamına gelmez. İpucu yoksa araç uzak yazma olarak değerlendirilir;
  incelenmemiş veya kaynağı değişmiş sunucunun salt okuma iddiası onayı atlayamaz.
- Uzak işlemlerde oturum izni yalnız doğrulanmış sunucu, hesap, eylem ve hedef
  kapsamında saklanır. Masaüstü ve terminal bu kapsamı seçimden önce gösterir;
  kapsam doğrulanamıyorsa yalnız tek işlem için izin istenir.
- Terminal giriş hatası veya Ctrl+C onaya dönüşmez. İsteğe bağlı soru kanalının
  kapanması bağımsız çalışmayı iptal etmez ve kullanıcı cevabı sayılmaz.
- Geç gelen soru cevapları yeniden açılan oturumdaki sorulara uygulanmaz.
  Yakın cevapların aynı makbuzla tekrarı işlemi ikinci kez başlatmaz.
- Büyük dosyalarda `read_file` ilk bayt penceresinin ötesindeki satırlara ulaşır;
  dosyanın tamamını belleğe almaz ve kısmi okuma tam okuma sayılmaz.
- Terminal konuşma günlüğü ve checkpoint aynı sohbet kimliğini kullanır.
  Eski ortak `repl`/`cli` kayıtları korunur; yeni oturumlara otomatik taşınmaz.
  Geçmiş sohbeti içe alma, eski işlem izinlerini veya workflow'u yeniden başlatmaz.

## [Desktop 0.3.0-alpha.11] — 2026-09-10

- Gerçek macOS uygulamasında saptanan panel genişliği düzeltildi; kontrol paneli
  çalışma alanına yayılır ve içerik ortalanır. Güncelleme düğmeleri ortak ölçülere uyar.
- Terminal/çalışma zamanı sürümü 0.3.0a10 olarak korunur; bu yalnız arayüz güncellemesidir.

## [0.3.0a10] — 2026-09-10

- Paketli uygulamada web girişinin Chrome açılmadan kapanmasına neden olan
  hesap parametresi düzeltildi; gerçek CLI ayrıştırıcısıyla regresyon testi eklendi.
- Yeni Fusion tarayıcı profillerinde Chrome ilk kurulum ve varsayılan tarayıcı
  ekranları atlanır; normal Chrome profili kullanılmaz.
- Kontrol paneli kategorilere ayrıldı; sağlayıcı ayrıntılarının yanlışlıkla
  yan yana çizilmesi düzeltildi ve kenar çubuğu daha kompakt hale getirildi.
- MCP ekleme ve yapılandırma formları odak yönetimi ve Escape desteği olan
  ayrı bir bağlantı penceresinde açılır.

## [0.3.0a9] — 2026-09-10

- Masaüstü kontrol paneline imzalı uygulama içi güncelleme eklendi; GitHub
  Releases için macOS güncelleme arşivi ve manifest üretimi sağlandı.
- macOS'ta Fusion API kasası tekrarlayan Keychain izin isteği olmadan açılır.
  Eski kasa korunur; sessiz geçiş mümkün değilse anahtar yeniden girilir.
- Web bağlantısı yalnız doğrulama sonrası bağlı gösterilir. Kapanmış giriş
  süreçlerinin açık sayılması, hata durumunda takılı kalan düğmeler ve Chrome
  süreç temizliği düzeltildi.
- Etkin Chrome profilinin kilidi korunur; yeni görünür giriş eski elle
  aktarılmış çerezlerle ezilmez.
- API kaydı ve doğrulaması ayrıldı; OpenRouter, OpenAI, Anthropic ve Gemini
  için kimlik doğrulamalı anahtar sınaması eklendi.
- Sol alttaki sabit örnek profil kaldırıldı; bağlantı bilgisi gerçek oturumdan okunur.
- Masaüstü ve terminal kurulumları README'de ayrı açıklandı.

## [0.3.0a8] — 2026-08-30

- Windows çalışma zamanı paketi başarıyla üretildikten sonra CP1252 konsoluna
  Türkçe günlük etiketi yazarken yayın işinin çökmesi engellendi.
- Büyük konuşma performans kapısına paylaşımlı Intel CI çalıştırıcısının
  zamanlayıcı yükünü kapsayan, gerileme yakalama özelliğini koruyan pay eklendi.

## [0.3.0a7] — 2026-08-30

- Windows Rust kalite kapısında hedefe göre kullanılmayan test yardımcı
  parametresinin uyarı-as-error üretmesi düzeltildi.

## [0.3.0a6] — 2026-08-30

- Rust çalışma zamanı testleri Windows hedefi, `.exe` giriş noktası ve Windows
  izin modeliyle derlenebilir hâle getirildi.
- POSIX çalıştırma izni ve kabuk protokolü testleri yalnız Unix hedeflerinde
  derlenecek biçimde sınırlandı.

## [0.3.0a5] — 2026-08-30

- Windows paket ayarı normal Cargo kalite kapısından ayrıldı; temiz makinede
  henüz üretilmemiş runtime arşivini araması engellendi.
- macOS paket komutu, ses tanıma yardımcı ikilisini Swift kaynağından kendisi
  derleyecek hâle getirildi.
- Dosya seçildikten hemen sonra Düzenle'ye basıldığında geciken seçme efektinin
  editörü kapatabilmesi düzeltildi.

## [0.3.0a4] — 2026-08-30

- Ses ayarları ilk açıldığında geciken bir eşitlemenin kullanıcının hızlı sürgü
  hareketini eski değerle ezebilmesi düzeltildi.
- Sürgü kaydetme yarışı tekrarlı regresyon koşusuyla doğrulandı.

## [0.3.0a3] — 2026-08-30

- macOS ve Windows masaüstü paketleme ortamlarına Piper ses motoru bağımlılığı
  eklendi; temiz CI makinesinde çalışma zamanı üretimi artık eksik paket bilgisiyle
  durmuyor.
- Ses sürgüsü testi gerçek tarayıcı `input` olayına geçirildi; macOS Intel ve
  Windows ortamlarındaki sahte olay zamanlaması farkı giderildi.
- Masaüstü CI bağımlılık sözleşmesi regresyon testine alındı.

## [0.3.0a2] — 2026-08-30

- Masaüstü Ayarlar ekranına oturumluk token, tahmini maliyet ve ölçülmüş model
  sağlığı özeti eklendi.
- Ses hızı, tını, özel Piper modeli ve çevrimdışı Türkçe model indirme Ayarlar'a
  taşındı.
- Windows WebView'da sürgü bırakılırken eski değerin kaydedilebildiği olay
  sıralaması düzeltildi.
- Ayarlar'ın kaydırma altındaki kullanım ve ses kartları geniş/dar görsel
  regresyon testlerine alındı.

## [0.3.0a1] — 2026-07-26

İlk kamuya açık alfa. Bu sürümün ağırlığı yeni özelliklerde değil, **sessizce
çalışmayan şeylerin bulunmasında**: aşağıdaki hataların çoğu kod "başarılı"
görünürken arka planda hiçbir iş yapmıyordu.

### Eklenenler

- **`/verify`** — projeyi tanıyıp doğrulama planı çıkarır (pytest, ruff, mypy,
  npm/pnpm/yarn scriptleri, cargo, go, make), planı gösterir ve onaylanırsa
  `config.yaml`'a yazar. Otomatik açılmaz: keşif tahmindir, yanlış tahmin kapıyı
  her turda düşürür.
- **`/undo`** — son agent turunun dosya değişikliklerini geri alır. Yalnızca
  agent'ın dokunduğu dosyalar; kullanıcının elle yazdıklarına dokunulmaz.
- **`--add-dir`** — proje kökünün yanında erişime açılacak dizin.
- **`/provider`** — hangi sağlayıcının kullanılacağını seç (`auto` | `nvidia` |
  `openrouter`). Tek sağlayıcıya kilitlenince ötekine hiç istek gitmez: bir
  sağlayıcının tükenmesi ötekini de tüketiyordu.
- **Kurulum sihirbazı anahtar sorar.** OpenRouter zorunlu, NVIDIA NIM opsiyonel.
  83 küratörlü ders otomatik yüklenir: indiren herkes eğitilmiş başlar.
- **Model zincirleri kurulu anahtarlara göre budanır.** İki sağlayıcıdan biri
  yeterlidir; olmayanın modelleri zincirden düşer.
- **Doğrulanmış sentez** (`verified_synthesis`) — hakem önce çalışır, kararı
  senteze taşınır. Paralel kipte sentez kazananı bilmiyordu.
- **Eval: tekrarlı koşu** (`--repeat N`) ve geçme oranı. Kararsız görevler adıyla
  raporlanır.
- **Eval: tur transkripti.** Her koşu `_transkript.jsonl` bırakır (araç çağrıları,
  sonuçları, model hataları). "Agent neden hiçbir şey yapmadı" sorusu artık
  sonradan cevaplanabiliyor.
- **Eval: kota tükenmesi görev başarısızlığından ayrılır.** Sağlayıcı 429 verdiğinde
  koşu durur ve rapor YAZILMAZ; yarım ölçümü geçerli sanmak yanlış sonuçlara yol
  açıyordu.
- **Eval: `setup`** ile göreve başlangıç dosyası verilebilir; bug fix ölçmenin
  ön koşuluydu. On yeni görev — üçü agent’ın YAPMAMASI gerekeni ölçüyor
  (kök dışına yazma, prompt injection, kullanıcı içeriğini silme).
- **Ders belleği projeye kapsanır.** A projesinde öğrenilen B'de hatırlanmaz;
  genel yordamsal dersler her projede kalır. Göç gerekmez.

### Değişenler

- **Kademe merdiveni NVIDIA NIM omurgasına taşındı.** OpenRouter'ın ücretsiz
  kotası günde 50 istek (≈12 fusion turu); NIM'inki çok daha geniş. Modeller
  katalogdan değil **yoklanarak** seçildi — katalogdaki birçok model `NotFound`
  dönüyor ya da zaman aşımına uğruyor.
- **Dosya erişimi varsayılan olarak proje köküyle sınırlı.** Kısıtlama opt-in
  bırakıldığı sürece kimse açmıyordu.
- **Gözetimsiz kabuk çalıştırma kara listeden beyaz listeye geçti.** Tanınmayan
  her komut sorulur. Kara listeye kalıp eklemek bir sonraki kaçış yolunu kapatmaz.
- **Dersler talimat değil ÖNERİ olarak enjekte edilir** ve güvenlik kararlarını,
  kullanıcı talimatını, araç izin akışını geçersiz kılamaz.
- **Kota hatası gerçekten işe yarayan yönlendirme verir.** Eski mesaj "farklı bir
  model dene" diyordu; sınır hesap başına olduğu için bu yanlış tavsiyeydi.

### Düzeltilenler

- **Doğrulama kapısı hiç düzeltme turu açmıyordu.** Komut çıktısı `DEVNULL`'a
  gidiyor, bulgu üretilmiyor, motor da bulgu yoksa döngüyü kırıyordu: `pytest`
  kırmızıyken agent düzeltmeye hiç başlamıyordu.
- **REPL'de doğrulama kapılarının hiçbiri kurulmuyordu.** `tool_context`
  geçirilmediği için web, tarayıcı ve görsel kapılar sessizce kapalıydı.
- **Boş `.env` satırı gerçek anahtarı gölgeliyordu.** Kurulum "tamam" diyor,
  hiçbir model çağrılamıyordu.
- **`/type` agent turunda uygulanmıyordu**; `task_model_map` REPL'de etkisizdi.
- **Seçim ekranı REPL'in event loop'unda çöküyordu.**
- **`defaults.yaml`'da `tiers` iki kez tanımlıydı**; 166 satır ölü koddu ve
  çalışan merdiven bozuktu (`medium` en büyük modeli, `premium` daha küçüğünü
  kullanıyordu).
- **Uzun model listeleri ekranı taşırıyordu** (327 model); artık sayfalanır.
- **Dosya yazımı atomik değildi**; yarıda kesilme çalışan dosyayı bozabiliyordu.
- **Alt-ajan değişiklikleri doğrulama kapısından kaçıyordu.**
- **Hakem ve sentez aday metnini talimat sayabiliyordu** (prompt injection).

### Bilinen sınırlar

- **MCP yok.**
- **`run_shell` kök kısıtlamasına tabi değil.** Onay katmanı savunmadır, kum
  havuzu değil: sınır aşılabilir ama sessizce aşılamaz. Ayrıntı `docs/BACKLOG.md`.
- **Eval seti dar.** 18 görev. Kolay blok tavana vurmuş (12 görev 3/3); ayırt
  etme gücü beş zor görevde. Tek sağlayıcıya kilitlenmiş ölçümde **14/15 ve 13/15**.
- **Gürültü tabanı ~1-2 koşu (15'te), görev bazında ±2.** Aynı yapılandırmanın iki
  koşusu arasındaki fark bu kadar; daha küçük A/B farkları yorumlanamaz.
- **`workflow_mode` ve `playbooks` varsayılan kapalı.** workflow ölçüldü: kaliteyi
  artırmıyor (8/15 → 9/15, gürültü sınırında), model çağrısını yarıya indiriyor
  ama süreyi ikiye katlıyor. `playbooks` hiç ölçülmedi.
