# Fusion — Yetenekler

Fusion iki şeyi tek üründe birleştirir:

1. **Kodlama ustası (agent):** terminalde kod okuyan, düzenleyen, test eden, git kullanan,
   plan yapan, kendi kendini denetleyen, hatalardan ders çıkaran bir asistan.
2. **Yerel model geçidi (gateway):** birçok sağlayıcıya bağlanan, biri tükenince ötekine
   geçen, tek bir yerel adres açan bir "santral" — böylece başka araçlar da Fusion'a bağlanır.

## Sende olan yetenekler

| Yetenek | Ne işe yarar |
|---|---|
| Yerel geçit (`fusion serve`) | Bu bilgisayardaki her araç Fusion'a bağlanır (yalnız 127.0.0.1) |
| Yerel web paneli (`/dashboard`) | Tarayıcıda sağlayıcı/sağlık/model gösterir, senin makinenden |
| 48 gerçek sağlayıcı | OpenAI, Gemini, Anthropic, Groq, Mistral, DeepSeek… hepsi LiteLLM ile |
| Otomatik yedekleme + sağlık | Bir model bozulursa/yavaşsa otomatik atlanır, güvenilirlik öğrenilir |
| Çok-hesap havuzu | Aynı sağlayıcıya birkaç ücretsiz hesap; biri dolunca öteki devreye girer |
| Yönlendirme stratejileri | Sıra / ücretsiz-önce / en-sağlıklı / rastgele… |
| Profiller (`/mode`) + effort (`/effort`) | "Ne kadar güçlü model" ve "ne kadar düşünsün" ayrı ayrı |
| Şifreli anahtar deposu | Anahtarlar şifreli saklanır, log'a/git'e girmez |
| Tarayıcı oturumu profilleri (`fusion browser`, Ayarlar › Web oturumları) | cookies.txt/JSON ya da Chrome'dan oturum aktar; ajanın tarayıcısı onaylı sitelerde girişli açılır — bkz. `TARAYICI_OTURUMLARI.md` |
| Bilgisayar kullanımı (`desktop_*`, Ayarlar › Bu bilgisayar, `fusion config set desktop.<alan>`) | Ekranı görür, tıklar, yazar; açma/kapama anahtarı, kademe tavanı (yalnız bak / tıkla / tam kontrol), reddedilen uygulamalar — bkz. `BILGISAYAR_KULLANIMI.md` |
| MCP köprüsü | Fusion araçlarını dışa aç (sunucu) + dış MCP araçlarını kullan (istemci) |
| MCP kurulumu (`/mcp`, `fusion mcp-add`, panel) | Sohbette `/mcp add <ad> <komut>`, terminalden `fusion mcp-add`, ya da Control Panel'in "MCP sunucusu bağla" kartından — üçü de aynı config.yaml'a yazar, elle düzenleme gerekmez |
| Öz-öğrenen bellek | Her görevden ders çıkarır, benzer işlerde hatırlar |
| Düz metin bellek (`/memory`) | `~/.claude/projects/<proje>/memory/MEMORY.md` + konu dosyaları her turun istemine girer; masaüstünde Ayarlar › Otomatik bellek |
| Alt ajan tanımları (`.claude/agents/*.md`) | `model`, `permissionMode`, `maxTurns`, `tools`/`disallowedTools`, `skills`, `memory`, `mcpServers` (ad ve satır içi tanım), `background`, `isolation`, `hooks`, `initialPrompt` Claude Code kurallarıyla uygulanır |
| Oturum ajanı (`fusion --agent`, `agent` ayarı; `/persona` kullanımdan kalkıyor) | Bütün oturumu bir ajan tanımıyla sürer (yerleşik `Explore`, `Plan`...); sürdürmede geri yüklenir; masaüstünde Kişilik seçici |
| Fork alt görev (`/subtask`, `context: fork`) | Bağlamı devralan izole alt ajan; sohbete yalnız özet döner; masaüstünde Alt görev düğmesi |
| Arka plan ajan görevleri (`fusion agent --bg`, `fusion agents`, `/bg`, `/tasks`, Ctrl+B) | Turdan bağımsız, ayrı süreçte koşan görev; girdi/bitiş bildirimi, devam mesajı, sonucun sıradaki tura teslimi; masaüstünde Ajanlar sekmesi — bkz. `ARKA_PLAN_GOREVLERI.md` |
| Oturumlar arası mesaj (`/list-agents`, `@oturum`, `list_agents`/`send_message`) | Açık REPL/masaüstü oturumları birbirine mesaj atar; gelen mesaj etiketli güvenilmez girdi, `runtime.cross_session_inbound` accept/hold/refuse |
| Uzak MCP OAuth | HTTP MCP sunucularında tarayıcı girişi, PKCE ve macOS Keychain token deposu |
| Uzaktan kontrol (`fusion remote-control`, `/rc`) | Terminal oturumunu masaüstü uygulaması olmadan telefondan/Telegram'dan sür; QR + eşleştirme kodu, onaylar telefona gider (bkz. docs/uzaktan) |
| Hesap ve kota göstergesi | Hesabım › Sağlayıcı hesapları (web sağlayıcısıyla giriş durumu), Ayarlar › Gelişmiş › "Hız sınırları ve kota" (`kullanim.durum.limitler`: ayarlı dakikalık sınır + sağlayıcının o an bekletmesi), Güncellemeler'de kurulu sürüm ve sürüm notları |
| Kanıta bağlı yeniden planlama | Aynı başarısız hedefte dönmek yerine doğrulanmış işi koruyup dalı bir kez yeniler |
| Gerçek asset kapısı | PNG/JPEG başlığı, boyut, kaynak URL'si ve lisans manifestini doğrular |
| Fusion ↔ Kits köprüsü (`fusion kit`, `kit_send`, `fusion_browser`) | Bir Kit'e mesaj/görev bırak, durumunu oku; Kit kullanıcının Chrome'unu onaylı kullanır (bkz. `docs/KITS_KOPRUSU.md`) |
| Yerel production smoke değerlendirmesi | Godot asset, gerçek MCP stdio listeleme/çağırma, replan, büyük dosya koruması ve JSON dosya ayrımını ölçer; OAuth/uygulama sohbet izolasyonu değildir |
| REPL paritesi (Claude Code) | `!` kabuk, `@dosya` anma + Tab tamamlama; `/status`, `/context`; `/export`, `/copy`; `/config` + `fusion config get/set/list`, `--set`, `--profile`; `/output-style`; `/statusline`; `/theme`, `/tui`, `/search`; `keybindings.json`, `/config editorMode=vim` (bkz. NASIL_KULLANILIR §15) |
| Komut paleti ve kısayollar (masaüstü) | Claude Desktop varsayılan tablosu (⌘/, ⌘N, ⌘W, Ctrl+Tab, ⌘⇧D, ⌘⇧B, Ctrl+`, ⌘\\, ⌘⇧M); komut paleti (eylem/ekran/sohbet/komut/ayar/dosya) tuşsuz, istenen tuşa bağlanır; Ayarlar › Kısayollar ile yeniden bağlama; `keybindings.json` `masaustu` bölümü (bkz. NASIL_KULLANILIR §17) |

Canlı smoke ölçümü isteğe bağlı olarak
`python -m evals run evals/suite/production.yaml --profile production --repeat 3 --out production-report.json`
komutuyla çalıştırılır; bu çağrı mevcut CI yayın zincirinde zorunlu değildir.
Her görev en fazla 30 model çağrısı ve 180 saniye ile sınırlıdır. Rapor, bütün tekil koşuların başarı oranını ve yalnız üç tekrarın
üçünü de geçen görevlerin katı güvenilirlik oranını ayrı gösterir. Canlı Meta OAuth
girişi kullanıcı hesabı ve tarayıcı onayı gerektirdiği için son smoke kontroldür;
token hiçbir değerlendirme fikstüründe tutulmaz. Yayın manifesti canlı kanıt yoksa
`liveAcceptance.status=not_measured` yazar; ayrıntılar `release/README.md` içindedir.

## Hâlâ eksik olanlar (dürüst)

- Ücretsiz-katman bütçe paneli (hangi hesapta ne kadar kota kaldı).
- Agresif token sıkıştırma (kodu bozmadan yapmak gerekir, dikkatli gidilmeli).
- Çok dilli arayüz (şu an Türkçe/İngilizce).
- Alt ajan / oturum ajanı (geçiş): `/persona` ve eklentisiz yalın Türkçe ekip rol adları
  (`kodcu`, `mimar`...; artık `fusion-ekip` eklentisi) bu sürüm boyunca kullanımdan kalkmış
  takma ad olarak çalışır, sonraki sürümde kalkar.

## Bilerek yapılmayanlar

- Başka uygulamaların trafiğini gizlice yakalama (MITM) — senin de istemediğin şey.
- ChatGPT/Gemini gibi tüketici web arayüzlerini kazıyan canlı bağlantı — bu sağlayıcıların
  şartlarına aykırı. Framework hazır; böyle bir bağlantıyı kullanıcı kendi yetkisiyle sağlar.

> Fikir, bir yerel model-geçidi ile kodlama asistanını birleştirmekti. Fusion bunu kendi
> bağımsız uygulaması olarak, tamamen senin bilgisayarında çalışacak biçimde yapar.

Adım adım kullanım için: [NASIL_KULLANILIR.md](NASIL_KULLANILIR.md).
