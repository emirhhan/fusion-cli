# Kabuk sandbox'ı (`run_shell`)

Fusion'ın `run_shell` aracıyla çalıştırdığı komutlar isteğe bağlı olarak işletim sisteminin
sandbox'ında koşar (Claude Code `sandbox.*`, Codex `workspace-write` karşılığı). Sandbox
onay akışının yerine geçmez; ikisi birlikte çalışır: sandbox teknik sınırı çizer, onay ve
izin kuralları neyin sorulacağına karar verir.

| Platform | Mekanizma | Not |
|----------|-----------|-----|
| macOS | `/usr/bin/sandbox-exec` (Seatbelt) | Ek kurulum gerekmez |
| Linux / WSL2 | bubblewrap (`bwrap`) | `apt install bubblewrap`; ağ allowlist'i için `socat` |
| Windows | yok | Kip açıksa uyarılır (ya da `fail_if_unavailable` ile çalıştırılmaz) |

## Açma ve durum

```text
/sandbox                  # durum: platform, kurulabilirlik, yazma/okuma/ağ kuralları
/sandbox on | off         # runtime.shell_sandbox = write_root | off
fusion sandbox durum      # aynı durum, terminalden
fusion doctor             # "Kabuk sandbox'ı" satırı
```

Masaüstünde: **Ayarlar › İzinler › Kabuk sandbox'ı**. Değişiklik bir sonraki görevde geçerli olur.

Varsayılan `runtime.shell_sandbox: off`: davranış değişmez. Eski `write_root` yapılandırması
olduğu gibi çalışır; `sandbox:` bölümü yoksa aşağıdaki varsayılanlar uygulanır.

## Ne sınırlanır?

- **Yazma:** proje kökü, `--add-dir` dizinleri, geçici dizinler ve `sandbox.allow_write`.
  `echo x > ../y` reddedilir. Sade `rm` (Fusion çöpüne taşınan) da köklerin dışını silmez.
- **Zorunlu yazma engeli (kök altında da):** `.git/config`, `.git/config.worktree`,
  `.git/hooks`, `.claude/settings.json`, `.claude/settings.local.json`, `.claude/launch.json`,
  `.fusion/launch.json`, `.fusion/tools` ve `.mcp.json` sandbox içinden yazılamaz; `.git`,
  `.claude`, `.fusion` taşınamaz/silinemez (Claude Code'un zorunlu deny-write listesi gibi).
  Neden: Fusion'ın `git` aracı sandbox dışında çalışır ve `core.fsmonitor`'u ya da hook'ları
  yürütür. `git add/commit/checkout/fetch` çalışır; `git init`, `git remote add`,
  `git push -u`, `git config` bu dosyalara yazdığı için sandbox içinde düşer — gerekirse
  `unsandboxed=true` (onaylı) ya da kullanıcı kendisi çalıştırır.
- **Okuma:** varsayılan okuma engeli her zaman uygulanır: `~/.ssh`, `~/.aws`, `~/.gnupg`,
  `~/.azure`, `~/.kube`, `~/.config/gcloud`, `~/.docker/config.json`, `~/.netrc`,
  `~/.git-credentials`, `~/.password-store`, `~/Library/Keychains`, `~/.config/gh`,
  `~/.config/git/credentials`, `~/.pypirc`. Fusion'ın yüklediği her `.env` (`FUSION_HOME/.env`,
  hesap ve temel yapılandırma dizini), şifreli kasası ve tarayıcı/web oturum profilleri de her
  zaman engellidir. `sandbox.deny_read` bu listeye **eklenir**; varsayılandan bir yolu bilerek
  açmak için `sandbox.allow_read` yazılır (ör. `["~/.kube"]`). `allow_read`'de okuma engelinde
  olmayan bir yol yapılandırma hatasıdır; Fusion'ın sır dosyaları bu yolla açılamaz. `~/.npmrc`
  bilinçli olarak listede yok (npm her kurulumda okur).

  ```yaml
  sandbox:
    deny_read: ["~/ozel-anahtarlar"]   # varsayılana eklenir
    allow_read: ["~/.kube"]            # kubectl sandbox içinde çalışsın
  ```

  **Eski davranış (1 Kasım öncesi):** `sandbox.deny_read` yazılınca liste varsayılanın YERİNE
  geçiyordu; tek yol ekleyen kullanıcı `~/.ssh` gibi korumaları kaybediyordu. Varsayılanı
  da kopyalayan eski yapılandırmalar aynı sonucu verir (yinelenenler birleşir). Bir varsayılanı
  listeden silerek açan eski yapılandırma artık o yolu yeniden engeller; açık kalması için
  `allow_read`'e yazın.
- **Ağ:** `sandbox.network: open` (varsayılan, kısıtsız) ya da `allowlist`. Allowlist'te komut
  yalnız Fusion'ın yerel proxy'sine bağlanabilir (`HTTP_PROXY`/`HTTPS_PROXY` ortamı verilir);
  proxy yalnız `allowed_domains`'e bağlanır, `denied_domains` her zaman önce gelir. İzinli bir
  ad iç ağ adresine (127.0.0.1, 10.x, 169.254.x…) çözülürse bağlanılmaz; iç adrese gitmek için
  IP'yi ya da `localhost`'u listeye açıkça yazın. `allow_localhost: true` dev sunucularına ve yerel
  veritabanına doğrudan erişimi açık tutar (Linux'ta yalnız sandbox içinde başlatılanlara).
- **Sır ortamı:** `hide_secret_env: true` iken sandbox içindeki komutun ortamından adı sır gibi
  görünen değişkenler (`*_API_KEY`, `*_KEY`, `*_TOKEN`, `*_SECRET`, `*PASSWORD*`, `*ACCESS_KEY*`,
  `*CREDENTIAL*`, `API_KEY`, `TOKEN`, `DATABASE_URL`) çıkarılır. Komut başarısız olursa gizlenen
  ADLAR nota yazılır (`/sandbox sir off` ile kapatılır). Bu macOS'ta **kaza önleyicidir,
  güvenlik sınırı değildir** (aşağıya bakın); sırrı kabukta `export` etmek yerine Fusion
  kasasında ya da `.env`'de tutun.
- **Başka süreçlerin ortamı:** Linux'ta komut kendi PID ad alanında ve taze `/proc` ile çalışır;
  başka süreçlerin `/proc/<pid>/environ`'ı görünmez. macOS'ta aynı kullanıcının Apple imzalı
  olmayan süreçlerinin (Fusion'ın Python'u, node, VS Code/iTerm gibi uygulamalar) **başlangıç**
  ortamı `sysctl(KERN_PROCARGS2)` ile okunabilir (`ps eww` sandbox içinde hiç çalışmaz, ama aynı
  çağrı ctypes ile yapılır). Ölçüldü (1 Kasım, macOS 27, gerçek `sandbox-exec`): Seatbelt'te bunu
  kesen işlem yok — `(deny process-info*)` (`target self`/`same-sandbox` ile), `(deny sysctl-read)`,
  `(deny sysctl*)`, `sysctl-name "kern.procargs2"` ve yalnız `process-exec`+`file-read*` izinli
  `(deny default)` profili de okumayı engellemedi; `process-info*` reddi yalnız `proc_pidpath`
  türü bilgileri keser ve araçları bozacağı için eklenmedi. Fusion'ın süreç başladıktan sonra
  yüklediği sırlar (`.env`, kasa) bu yolla görünmez; görünen, Fusion'ı başlatan kabuğun `export`
  ettikleridir. Masaüstü uygulaması Finder'dan açıldığında kabuk ortamını taşımaz.
  Kanarya testi: `tests/test_sandbox_sinirlar.py::test_macos_seatbelt_baska_surecin_baslangic_ortamini_kesemez_olcum`
  (Apple bir kanca eklerse düşer).

```text
/sandbox ag allowlist
/sandbox izin github.com          # alan adı ekler (ağı allowlist'e alır)
/sandbox izin *.npmjs.org         # alt alan adları
/sandbox engelle gist.github.com
/sandbox kaldir github.com
fusion sandbox izin pypi.org
/sandbox oto on | zorunlu on | disari off | sir off | localhost off
fusion sandbox oto on             # aynı bayraklar terminalden
```

`/sandbox izin` ağ açıkken kipi allowlist'e geçirir ve bunu sonuç metninde söyler: o andan
sonra yalnız listedeki adlar erişilebilir (npm, pip dahil diğer trafik kapanır).

Engellenen bağlantıdan sonra modele `Sandbox ağı engelledi: <alan>` notu gider; izin vermek
kullanıcının kararıdır. Her komutun kendi proxy'si vardır: eşzamanlı komutların (arka plan
işi, alt ajan) retleri birbirine karışmaz. Ön plan komutunun proxy'si komut bitince, arka plan
işininki iş süreci bitince kapanır; işin ret notu günlüğün sonuna (`job_status` çıktısı)
eklenir. İşin kendi içinde arka plana attığı ve işten uzun yaşayan süreçler (`npm run dev &`)
iş bitince ağ erişimini kaybeder. `/sandbox izin` sonrası yeni politika bir sonraki komutta
geçerlidir; çalışan arka plan işi başladığı politikayla sürer.

## Sandbox dışında çalıştırma

- Model gerektiğinde `run_shell(command=…, unsandboxed=true)` ister. Bu istek **her seferinde**
  ayrıca sorulur (Otomatik kipte de; "bu oturumda sorma" sunulmaz). Yalnız "İzinleri atla"
  kipi sormaz; plan kipi soru soramadığı için isteği **engeller** (salt okunur komutta da).
  `sandbox.allow_unsandboxed: false` ise istek yok sayılır, komut sandbox içinde kalır.
- `sandbox.excluded_commands: ["docker", "git push"]` önekleri her zaman sandbox dışında, normal
  onayla çalışır. Yalnız tek ve sade komut eşleşir: `docker ps && curl …` sandbox içinde kalır.

## Diğer ayarlar

| Ayar | Varsayılan | Anlamı |
|------|-----------|--------|
| `sandbox.fail_if_unavailable` | `false` | `true`: sandbox kurulamazsa komut çalıştırılmaz (sorulmadan engellenir) |
| `sandbox.auto_allow` | `false` | `true`: sandbox içinde VE `network: allowlist` iken komut sorulmaz. Sandbox gerçekten kurulamıyorsa (ör. Linux'ta socat yok) sorulur. Yıkıcı komutlar, `ask`/`deny` kuralları ve plan kipi yine geçerli |
| `sandbox.allow_localhost` | `true` | Allowlist kipinde `localhost`'a doğrudan erişim |
| `sandbox.hide_secret_env` | `true` | Sır görünümlü ortam değişkenlerini gizle (yukarıya bakın) |
| `sandbox.allow_write` | `[]` | Ek yazılabilir dizinler, ör. `["~/.npm", "~/.cache/pip"]` |
| `sandbox.deny_read` | `[]` | Varsayılan okuma engeline EK yollar |
| `sandbox.allow_read` | `[]` | Varsayılan okuma engelinden bilerek açılan yollar |

Hepsi `/config sandbox.<alan>=<değer>` ile de değişir, ör. `/config sandbox.allow_write=~/.npm`.
Güvenilmeyen bir projenin `config.yaml`'ındaki `sandbox:` bölümü uygulanmaz (`fusion trust`).

## Deneme

```bash
fusion sandbox calistir -- "cat ~/.ssh/id_ed25519"      # okuma engeli
fusion sandbox calistir -- "echo x > ../disari.txt"     # yazma sınırı
fusion sandbox calistir -- curl -sS https://example.com  # ağ kuralı
```

`calistir`, kip kapalı olsa da komutu geçerli politikayla sandbox içinde çalıştırır
(Codex `codex sandbox` gibi) ve engellenen yazma/okuma/alan adı notlarını basar.

## Bilinen sınırlar

- macOS profili Seatbelt'in desteklenmeyen (ama sistemde hâlâ çalışan) arayüzüdür.
- Allowlist kipinde Unix soketleri (Docker soketi, `ssh-agent`) ve DNS (mDNSResponder) kapalıdır;
  proxy kullanmayan araçlar ağa çıkamaz. Böyle komutlar için `excluded_commands` ya da
  `unsandboxed=true` (onaylı) kullanın.
- Paket önbellekleri (`~/.npm`, `~/.cache`) `allow_write`'a eklenmedikçe yazılamaz.
- **localhost ve yerel dinleyiciler:** ağ `open` iken ya da `allow_localhost: true` ile sandbox
  içindeki komut 127.0.0.1 portlarına (dev sunucusu, veritabanı) bağlanabilir. İstisna: Fusion'ın
  web model profillerinin paylaşılan Chrome'u loopback'te kimlik doğrulamasız bir hata ayıklama
  portu (CDP) açar; bu port her komutta `web_profiles/*/*/DevToolsActivePort`'tan okunur ve
  sandbox'a kapatılır. macOS'ta Seatbelt kuralıyla her ağ kipinde; proxy de (ör. `127.0.0.1`
  açıkça izinliyken) her bağlantıda yeniden bakar. Linux'ta allowlist kipinde komut ayrı ağ ad
  alanında olduğundan ana makinenin localhost'una zaten ulaşamaz; **ağ `open` iken Linux'ta
  korunmaz** (bwrap port süzemez) — oturumlu web profilleriyle `network: allowlist` kullanın.
  macOS'ta Seatbelt kuralı komut başlarken yazılır: uzun süren bir arka plan işi başladıktan
  SONRA açılan Chrome'un portu o işe doğrudan bağlantıda kapalı değildir (proxy yolu kapalıdır).
  Neden `--remote-debugging-pipe` değil: bu Chrome başlatan süreçten bağımsız yaşar ve masaüstünün
  her sekme süreci ona bağlanır; boru tek sürece bağlıdır, ayrı bir aracı süreç gerektirirdi.
  Ajanın `browser_*` tarayıcısı ve doğrulama tarayıcıları Playwright ile zaten boru kullanır.
  Kullanıcının kendi `--remote-debugging-port` ile açtığı Chrome kapsanmaz. Durum: `/sandbox`
  "Tarayıcı CDP" satırı, masaüstü kartı.
- Linux (bubblewrap): komut kendi PID/IPC ad alanında ve yeni oturumda çalışır (host `/proc`
  görünmez, socat köprüsü komutla ölür). bwrap var olmayan dosyayı koruyamaz: proje henüz git
  deposu değilse `.git` ya da yoksa `.mcp.json` sandbox içinden oluşturulabilir (Fusion'ın güven
  karması ayar dosyası değişince projeyi güvenilmez sayar). macOS'ta yol yoksa da korunur.
- Yalnız kökteki `.git` korunur; iç içe depoların (alt dizindeki `.git`) yapılandırması korunmaz.
- Linux yolu birim testlerle doğrulandı; gerçek bubblewrap davranışı Linux makinede elle denenmelidir.
