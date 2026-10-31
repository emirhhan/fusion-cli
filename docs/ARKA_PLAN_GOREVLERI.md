# Arka plan ajan görevleri ve oturumlar arası mesajlaşma

Claude Code'daki `claude --bg`, `claude agents`, `/background`, `/tasks`, Ctrl+B,
`ListAgents` / `SendMessage` ve `/list-agents` davranışının Fusion karşılığı (P-048, P-060).

## Arka plan görevi nedir?

Turdan bağımsız koşan bir ajan görevidir: başlatan terminal ya da sohbet beklemez, kapansa da
görev sürer. Her görev ayrı bir süreçte (`fusion arka-plan-calistir`) `fusion agent` ile aynı
motor yolundan koşar. Kayıtlar `<bellek dizini>/arka-plan/<kimlik>/` altındadır:

| Dosya | İçerik |
|---|---|
| `gorev.json` | durum, ad, görev metni, kip, sahip konuşma, özet |
| `olaylar.jsonl` | işçinin JSON-Lines olay akışı (`fusion agent --json` biçimi) |
| `sonuc.md` | son turun nihai cevabı |
| `soru.json` / `cevap.json` | bekleyen onay/soru ve cevabı |
| `gelen.jsonl` | devam mesajları |
| `gecmis.json` | devam turları için konuşma (yalnız kullanıcı/asistan metni) |

Durumlar: `sırada` → `çalışıyor` ⇄ `girdi bekliyor` → `tamamlandı` | `başarısız` |
`durduruldu`. İşçi 30 sn nabız vermezse görev `yarım kaldı` görünür; ona mesaj göndermek
görevi aynı konuşmayla yeniden başlatır.

## Başlatma

| Yüzey | Nasıl |
|---|---|
| Terminal | `fusion agent --bg [--name ad] [--agent ajan] [-m kip] "görev"` — hemen döner |
| REPL | `/bg <görev>` (`/background`); argümansız `/bg` son görevi konuşma bağlamıyla sürdürür |
| Tam ekran REPL | Tur sürerken **Ctrl+B**: tur kesilir, aynı görev bağlamıyla arka planda sürer |
| Model | `spawn_agent(task=…, arka_plan=true)` kimliği hemen döner |
| Masaüstü | Ajanlar sekmesi › Arka plan görevleri › "Arka planda başlat" ya da sohbette `/bg` |

REPL ve masaüstünden başlayan görev konuşmanın son 12 kullanıcı/asistan mesajını devralır
(araç çıktısı ve harness notu taşınmaz). Kip başlatanın kipidir; **bypass miras alınmaz**
(auto'ya düşer). Alt ajanlar arka plan görevi açamaz.

## İzleme ve yönetme

| İş | Terminal | REPL | Masaüstü |
|---|---|---|---|
| Liste | `fusion agents [--izle] [--json] [--tum]` | `/tasks [list [all]]` | Ajanlar sekmesi |
| Ayrıntı | `fusion agents goster <id>` | `/tasks show <id>` | "Ayrıntı" |
| Onay/soru | `fusion agents cevapla <id> evet\|hayir\|oturum\|<metin>` | `/tasks answer <id> …` | Onayla / Bu görevde hep / Reddet |
| Devam mesajı | `fusion agents mesaj <id> "<metin>"` | `/tasks send <id> …` ya da `@ad <metin>` | görev kartındaki kutu |
| Durdur | `fusion agents durdur <id> [--zorla]` | `/tasks stop <id> [zorla]` | "Durdur" |
| Sil | `fusion agents sil <id>` / `temizle` | `/tasks rm <id>` / `/tasks clean` | "Sil" |

`<id>` yerine görev adı ya da kimliğin ilk 4+ karakteri yazılabilir. Durdurma önce
işbirliklidir (işçi turu keser); `--zorla` yalnız işçi sürecinin komut satırında görev
kimliği doğrulanırsa süreç grubunu sonlandırır.

Görev girdi isterse ya da biterse REPL'de tek satırlık bildirim çıkar, masaüstünde işletim
sistemi bildirimi gelir. Bu konuşmanın başlattığı görevin sonucu sıradaki turun bağlamına
`<arka_plan_sonuclari>` bloğu olarak bir kez girer. Model `list_agents(id=…, bekle_s=…)` ile
bekleyebilir, `send_message(to=…)` ile devam ettirir, `stop_agent(id=…)` ile durdurur.

## Oturumlar arası mesajlaşma

Her REPL, tam ekran ve masaüstü oturumu `<bellek dizini>/oturumlar/` defterine kaydolur
(ad, tür, proje kökü, nabız). Kapanan oturum defterden çıkar; 20 sn nabızsız oturum listede
görünmez.

- `/list-agents` (`/peers`): açık oturumlar ve bekletilen gelen mesajlar.
- `@oturum-adı <metin>` ya da `/list-agents gonder <ad> <metin>`: mesaj gönder. `@ad`
  projede bir dosya/dizin adıysa dosya anması olarak kalır.
- Model: `list_agents` (görevler + oturumlar), `send_message(to, message)`.

Gelen mesaj BAŞKA bir ajan ya da kullanıcıdan gelir ve **güvenilmez girdi** sayılır: tura
`<oturumlar_arasi_mesaj kimden="…" guvenilmez="evet">` etiketiyle ve "kullanıcı talimatı
değildir" notuyla girer, slash ile başlasa da komut olarak çalışmaz. Mesaj en çok 8.000
karakter, alıcıda en çok 20 bekleyen mesaj.

`runtime.cross_session_inbound`:

| Değer | Davranış |
|---|---|
| `hold` (varsayılan) | Mesaj bekletilir; `/list-agents al <no>` tura alır, `reddet <no>` siler |
| `accept` | Oturum boştayken etiketli tur olarak kendiliğinden işlenir |
| `refuse` | Mesaj kabul edilmez; gönderen açık hata alır |

Masaüstünde gelen mesaj ayar ne olursa olsun bekletilir; "Tura al" ile işlenir.

Tasarım notu: Claude Code Unix soketi kullanır; Fusion dosya gelen kutusu kullanır (Windows'ta
da aynı çalışır, alıcı kapalıyken mesaj kaybolmaz). Aynı kullanıcı hesabındaki her yerel süreç
deftere yazabilir; bu yüzden gelen mesaj hiçbir zaman güvenilir sayılmaz.

## Ayarlar (`fusion config set runtime.<alan> <değer>`)

| Alan | Varsayılan | Anlam |
|---|---|---|
| `background_agents` | `true` | `false`: hiçbir yüzey arka plan görevi başlatmaz |
| `max_background_agents` | `4` | Aynı anda etkin görev tavanı |
| `background_input_timeout_s` | `1800` | Onay/soru cevabı bekleme; dolunca "sorulamadı" |
| `cross_session_messaging` | `true` | `false`: oturum defteri ve mesajlaşma kapalı |
| `cross_session_inbound` | `hold` | `accept` \| `hold` \| `refuse` |

Ctrl+B `~/.fusion/keybindings.json` içinde `"tui": {"c-b": null}` ile kaldırılabilir ya da
başka tuşa (`"arka_plana_al"` eylemi) bağlanabilir. Satır-içi REPL'de tur sürerken tuş
okunmadığı için orada `/bg` kullanılır.

## Bilinen sınırlar

- Ajan tanımındaki `background: true` alanı hâlâ yalnız okunur; arka plan için çağrıda
  `arka_plan=true` gerekir.
- `/tasks` kabuk arka plan işlerini (`run_shell(background=true)`, `job_status`) listelemez.
- Görevin olay günlüğü budanmaz; `fusion agents temizle` bitmiş kayıtları siler.
