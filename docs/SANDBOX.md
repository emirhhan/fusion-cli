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
/sandbox                  # panel: Kip · Geçersiz kılmalar · Yapılandırma · Bağımlılıklar
/sandbox on | off         # sandbox.enabled = true | false
fusion sandbox durum      # aynı durum, terminalden
fusion doctor             # "Kabuk sandbox'ı" satırı
```

Argümansız `/sandbox` (terminal ve TUI) Claude Code'daki paneli açar: **Kip** (sandbox otomatik
izinle / normal izinlerle / kapalı), **Geçersiz kılmalar** (sandbox dışı yeniden denemeye izin ya
da "Katı sandbox kipi" = `allowUnsandboxedCommands: false`), **Yapılandırma** (etkin ayarlar) ve
**Bağımlılıklar** (Linux'ta `bwrap`/`socat`, macOS'ta `sandbox-exec`). Fusion'ın seçicisi tek
liste olduğu için sekmeler listede başlıklı bölümlerdir; etkin seçim ● ile işaretlidir.
Etkileşimsiz ortamda durum metni basılır.

Masaüstünde: **Ayarlar › İzinler › Kabuk sandbox'ı**. Değişiklik bir sonraki görevde geçerli olur.

Varsayılan kapalıdır (Claude Code'daki gibi `sandbox.enabled: false`). `sandbox:` bölümü yoksa
aşağıdaki varsayılanlar uygulanır.

### Ayarların okunduğu yer (Claude Code ile aynı)

Sandbox ayarları Claude Code'un kendi dosyalarından okunur (sonraki öncekini ezer):
`~/.claude/settings.json` (ya da `CLAUDE_CONFIG_DIR`), proje `.claude/settings.json` ve
`.claude/settings.local.json`; proje dosyaları yalnız güvenilen projede (`fusion trust`)
uygulanır. Yol ve alan adı listeleri (`allowWrite`, `denyRead`, `allowedDomains`…) dosyalar
boyunca **birleşir**; tekil değerlerde son dosya kazanır. Fusion YAML'ındaki `sandbox:` bölümü
bunların altında en düşük katmandır. Dosyaların üstünde Claude'daki gibi `--settings` katmanı
ve en üstte yönetilen (managed) ayarlar gelir: macOS `/Library/Application Support/ClaudeCode/`,
Linux `/etc/claude-code/` altında `managed-settings.json` ve `managed-settings.d/*.json`
(alfabetik). Yönetilen dosyalar güven denetimi istemez, ortam değişkeniyle başka dizine
yönlendirilemez ve Fusion bunlara yazmaz. Yönetilen ayarda
`sandbox.filesystem.allowManagedReadPathsOnly: true` kullanıcı/proje/yerel/`--settings`
katmanlarındaki `allowRead` yollarını, `sandbox.network.allowManagedDomainsOnly: true` ise
oradaki `allowedDomains` listelerini yok sayar; ikincisinde izinli olmayan alan adı sorulmadan
engellenir. Bu iki anahtar yönetilen dosya dışında etkisizdir. `--settings <dosya|json>`
katmanı kök komutun argümanından okunur (sandbox bölümü ve `permissions.defaultMode`) ve aynı
süreçteki alt ajanlarla oturumdan başlayan alt süreçlere ortamla geçer.

Göreli yollar ayar dosyasının kapsamına göre çözülür: proje ayarında proje kökü, kullanıcı
ayarında `~/.claude`, `--settings` dosyasında o dosyanın dizini, yönetilen ayarda yönetilen
dizin; `/` mutlak, `~/` ev dizinidir (Fusion YAML'ındaki göreli yollar proje
köküne göredir).

`/sandbox` paneli, `/sandbox on|off|oto|disari` (REPL) ve masaüstü sandbox paneli kip ve
geçersiz kılma seçimini Claude'daki gibi projenin `.claude/settings.local.json` dosyasına
(`sandbox.enabled`, `sandbox.autoAllowBashIfSandboxed`, `sandbox.allowUnsandboxedCommands`)
yazar; proje yerel ayarı güvenilmiyorsa kullanıcı dosyasına düşer. `fusion sandbox` ve alan adı
/ bayrak eylemleri Fusion kullanıcı dosyasına yazar.

### Ayar adları (Claude Code ile aynı)

Ayarlar Claude Code'daki iç içe camelCase adlarla yazılır; `/sandbox` ve `fusion sandbox` de
dosyaya bu adlarla yazar:

```yaml
sandbox:
  enabled: true
  autoAllowBashIfSandboxed: true
  excludedCommands: []
  allowUnsandboxedCommands: true
  failIfUnavailable: false
  filesystem:
    allowWrite: ["~/.npm"]
    denyRead: []
    allowRead: []
  network:
    allowedDomains: ["github.com"]
    deniedDomains: []
    strictAllowlist: false
```

Ağ Claude'daki gibi her zaman proxy'den geçer (allowlist; `allowedDomains` boş başlar). Geçiş
süresince Fusion'a özgü `network.mode: open` kısıtsız ağı korur; kullanımdan kalkıyor ve bir kez
uyarılır. Eski adlar (`runtime.shell_sandbox`,
düz `allow_write`, `deny_read`, `allow_read`, `allowed_domains`, `denied_domains`, `auto_allow`,
`excluded_commands`, `allow_unsandboxed`, `fail_if_unavailable`, `network: open|allowlist`)
bir sürüm boyunca okunur ve bir kez uyarılır; ikisi birden yazılmışsa Claude adı kazanır.
`/sandbox` bir ayarı yazınca dosyadaki eski adlar Claude adlarına taşınır.

Ek Claude anahtarları: `network.allowUnixSockets` (bağlanılabilen Unix soket yolları; göreli yol
ayar dosyasının kapsamına göre) ve `network.allowAllUnixSockets` macOS Seatbelt'te soket
bağlantısını açar (Linux'ta dosya sistemi soketleri zaten erişilebilir); `network.allowLocalBinding`
localhost portunda dinlemeye izin verir (Fusion uzantısı `allow_localhost` kapalıyken anlamlıdır);
`bwrapPath` / `socatPath` Linux araçlarının yolunu verir. `allowMachLookup`, `allowAppleEvents` ve
`enableWeakerNetworkIsolation` okunur ama etkisizdir: Fusion'ın Seatbelt profili `(allow default)`
olduğu için Mach araması ve Apple Events zaten açıktır (Claude'da varsayılan kapalıdır).
`network.httpProxyPort` / `socksProxyPort` trafiği kullanıcının localhost'taki kendi HTTP /
SOCKS5 proxy'sine yönlendirir: Fusion proxy başlatmaz, `allowedDomains`/`deniedDomains` ve ağ
soruları o trafiğe uygulanmaz (süzme o proxy'dedir); macOS'ta Seatbelt yalnız bu portlara çıkışa
izin verir, Linux'ta port ad alanına Unix soketi + socat köprüsüyle (SOCKS için 1080) taşınır;
`ALL_PROXY` SOCKS adresini alır. `network.tlsTerminate` (`{}` oturum başına geçici CA ya da
`{caCertPath, caKeyPath}`) proxy'nin HTTPS'i sonlandırmasını sağlar: her ana makine için CA
imzalı sertifika üretilir, gerçek sunucuya doğrulanarak yeniden bağlanılır (HTTP/1.1), sandbox
içindeki istemciler CA'ya `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`,
`GIT_SSL_CAINFO`, `PIP_CERT`, `AWS_CA_BUNDLE` (sistem kökleri + CA) ve `NODE_EXTRA_CA_CERTS`
ile güvenir; CA ve yaprak anahtarlarının dizini sandbox'a okunamaz. TLS olmayan tüneller (ilk
bayt el sıkışması değilse; git+ssh) dokunulmadan geçer. CA okunamazsa komuta bir not düşülür
ve HTTPS sonlandırılmaz; `fusion doctor` (Claude `claude doctor` gibi) "TLS sonlandırma
kullanılamıyor" uyarısı verir. `filesystem.disabled: true` dosya sistemi yalıtımını atlar, ağ
yalıtımı kalır (Fusion sırları ve `.git/config` gibi korumalı yollar yine kapalı).
`enableWeakerNestedSandbox` (Linux) yetkisiz Docker içinde yeni `/proc` bağlamaz;
`allowNestedUserNamespaces` (Linux) kapalıyken sandbox içinde yeni kullanıcı ad alanı açılamaz
(`--unshare-user --disable-userns`; bunu desteklemeyen eski bwrap'te atlanır). `ripgrep:
{command, args}` (Linux) alt dizinlerdeki korumalı dosyaları (iç içe depoların `.git/config` ve
`.git/hooks`'u, `.claude` ayarları, `.mcp.json`; 4 dizin derinliğe kadar) bulan rg'dir; boşsa
PATH'teki `rg`, o da yoksa yalnız kök düzeyi korunur.

Claude'daki gibi proje ayar dosyaları (`.claude/settings.json`, `.claude/settings.local.json`)
`tlsTerminate`, mask girdileri, `allowPlaintextInject`, `filesystem.disabled`,
`allowNestedUserNamespaces` ve `ripgrep` ayarlayamaz: bunlar yok sayılır ve bir kez uyarılır;
yalnız kullanıcı ayarı, managed ve `--settings` geçerlidir. Etkin olanlar `/sandbox`
Yapılandırma ekranında ve masaüstü Sandbox kartında listelenir. Bilinmeyen anahtarlar yok
sayılır ve bir kez uyarılır.

## Ne sınırlanır?

- **Yazma:** proje kökü, `--add-dir` dizinleri, geçici dizinler ve `sandbox.allow_write`.
  `sandbox.filesystem.denyWrite` bu bölgelerin içinde de yazılamayan yolları verir (Claude
  Code ile aynı; macOS'ta yol yoksa da korunur, Linux'ta yalnız var olan yol).
  `echo x > ../y` reddedilir. Sade `rm` (Fusion çöpüne taşınan) da köklerin dışını silmez.
- **Zorunlu yazma engeli (kök altında da):** `.git/config`, `.git/config.worktree`,
  `.git/hooks`, `.claude/settings.json`, `.claude/settings.local.json`, `.claude/launch.json`,
  `.fusion/launch.json`, `.fusion/tools` ve `.mcp.json` sandbox içinden yazılamaz; `.git`,
  `.claude`, `.fusion` taşınamaz/silinemez (Claude Code'un zorunlu deny-write listesi gibi).
  Neden: Fusion'ın `git` aracı sandbox dışında çalışır ve `core.fsmonitor`'u ya da hook'ları
  yürütür. `git add/commit/checkout/fetch` çalışır; `git init`, `git remote add`,
  `git push -u`, `git config` bu dosyalara yazdığı için sandbox içinde düşer — gerekirse
  `dangerouslyDisableSandbox=true` (onaylı) ya da kullanıcı kendisi çalıştırır.
- **Okuma:** Claude Code gibi sandbox makinenin tamamını okuyabilir; yerleşik bir kimlik
  bilgisi listesi **yoktur** (`~/.ssh`, `~/.aws/credentials` de yazılmazsa okunur). Engellemek
  için `sandbox.filesystem.denyRead` ya da `sandbox.credentials.files` yazılır.
  `sandbox.filesystem.allowRead` engellenmiş bir bölgenin içini yeniden açar; kurallar çakışınca
  **dar yol kazanır**: `denyRead ["~/"]` + `allowRead ["~/projeler"]` projeyi açar, `allowRead
  ["~/"]` + `denyRead ["~/.env"]` sırrı kapalı tutar; aynı yol iki listede ise engel kazanır.
  Fusion'ın yüklediği her `.env` (`FUSION_HOME/.env`, hesap ve temel yapılandırma dizini),
  şifreli kasası ve tarayıcı/web oturum profilleri her zaman engellidir ve `allowRead` ile
  açılamaz.

  ```yaml
  sandbox:
    filesystem:
      denyRead: ["~/"]
      allowRead: ["~/projeler"]
    credentials:
      files: [{path: "~/.aws/credentials", mode: deny}, {path: "~/.ssh", mode: deny}]
      envVars: [{name: GITHUB_TOKEN, mode: deny}]
  ```

  **Eski davranış (1 Kasım öncesi):** 14 yollu yerleşik okuma engeli (`~/.ssh`, `~/.aws`,
  `~/.kube`…) vardı ve `allow_read` yalnız bu listedeki bir yolu birebir açabiliyordu (başka yol
  yapılandırma hatasıydı). Bu korumayı isteyen kullanıcı yolları `denyRead`'e yazar. Göreli
  yollar hâlâ proje köküne göre çözülür (Claude'da ayar dosyasının dizinine göre; #369 bekliyor).
- **Ağ:** Claude Code gibi komutun doğrudan çıkışı yoktur; komut yalnız Fusion'ın yerel
  proxy'sine bağlanabilir (`HTTP_PROXY`/`HTTPS_PROXY` ortamı verilir). `deniedDomains` her
  kipte reddedilir; `allowedDomains` ve `WebFetch(domain:…)` allow kuralındaki adlar sorulmadan
  geçer. Listede olmayan ad istenince komut sandbox'ta bekler ve karar izin kipine göredir:
  Manual, acceptEdits ve plan kipinde **sorulur** ("Evet" adı oturum boyunca açar, "Evet, bir
  daha sorma" yerel ayara `WebFetch(domain:<ad>)` yazar); bypassPermissions ve bypass
  kullanılabilen plan kipinde sorulmadan izin verilir; auto ve dontAsk kipinde reddedilir
  (Fusion'ın auto sınıflandırıcısı ana makine listesini onaylamaz). `strictAllowlist: true`
  her kipte sormadan reddeder. Soracak kimse yoksa (`fusion agent`, `-p`) reddedilir. İzinli bir
  ad iç ağ adresine (127.0.0.1, 10.x, 169.254.x…) çözülürse bağlanılmaz; iç adrese gitmek için
  IP'yi ya da `localhost`'u listeye açıkça yazın. `allow_localhost: true` dev sunucularına ve yerel
  veritabanına doğrudan erişimi açık tutar (Linux'ta yalnız sandbox içinde başlatılanlara).
- **Sır ortamı:** Claude gibi ortam Fusion'dan miras alınır. `sandbox.credentials.envVars`
  (`mode: deny`) adları sandbox içindeki komutun ortamından çıkarır. `mode: mask` (Claude gibi)
  komuta gerçek değer yerine oturum boyunca aynı kalan, aynı bayt uzunluğunda bir yer tutucu
  verir; proxy izinli ana makinelere (`injectHosts`, yoksa `allowedDomains`; `injectHosts`
  girdisi `allowedDomains` kapsamında olmalı) giden istekte yer tutucuyu gerçek değerle
  değiştirir, yanıtta geri çevirir. HTTPS için `network.tlsTerminate`, düz HTTP için
  `credentials.allowPlaintextInject` gerekir; ikisi de yoksa istek yer tutucuyla gider (sır
  sızmaz). Aynı ad iki kipte de yazılmışsa `deny` uygulanır. Kullanıcının kendi proxy'si
  (`httpProxyPort`) verilmişse yerine koyma yapılmaz. Kullanımdan
  kalkan Fusion uzantısı `hide_secret_env: true` adı sır gibi görünen değişkenleri
  (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `*PASSWORD*`…) de çıkarır; varsayılan `false`. Bu
  macOS'ta **kaza önleyicidir, güvenlik sınırı değildir** (aşağıya bakın).
  `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` (Claude Code ile aynı) sandbox açık olsun olmasın
  `run_shell` komutlarının ortamından Anthropic ve bulut sağlayıcı kimlik bilgilerini
  (`ANTHROPIC_API_KEY`, `AWS_*` anahtarları, `GOOGLE_APPLICATION_CREDENTIALS`…) ve Fusion'ın
  sağlayıcı anahtarlarını (`OPENROUTER_API_KEY`, `NVIDIA_NIM_API_KEY`, `OPENAI_API_KEY`,
  `GEMINI_API_KEY`) çıkarır; aynı temizlik kanca komutlarının ortamına da uygulanır. MCP stdio
  sunucuları zaten yalnız güvenli ortam adlarını (HOME, PATH, USER…) devralır; sunucuya `env`
  ile açıkça verilen değer kullanıcının seçimidir. Fusion'ın kendisi anahtarları API çağrıları
  için tutar.
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
işininki iş süreci bitince kapanır; işin ret notu günlüğün sonuna (çıktı dosyası)
eklenir. İşin kendi içinde arka plana attığı ve işten uzun yaşayan süreçler (`npm run dev &`)
iş bitince ağ erişimini kaybeder. `/sandbox izin` sonrası yeni politika bir sonraki komutta
geçerlidir; çalışan arka plan işi başladığı politikayla sürer.

## Sandbox dışında çalıştırma

- Model gerektiğinde `run_shell(command=…, dangerouslyDisableSandbox=true)` (eski ad `unsandboxed`
  de okunur) ister. Onay Claude Code'daki gibi kipe bağlıdır: "İzinleri atla" sormaz; Manuel ve
  "Düzenlemeleri kabul et" **Bash command (unsandboxed)** diye sorar (salt okunur komut da, çünkü
  okuma sınırı da kalkar); Otomatik kipte denetçi (sınıflandırıcı) karar verir, denetçi yoksa
  sorulur; `dontAsk` reddeder. Komuta uyan `allow` kuralı (`Bash(npm test)`) yeniden denemeyi
  sormadan onaylar; `ask: ["Bash(dangerouslyDisableSandbox:true)"]` her kipte (bypass dahil) soruyu
  zorunlu kılar, aynı yazımlı `deny` kuralı isteği reddeder. "Bu oturumda sorma" yalnız aynı
  sandbox dışı komutu kapsar; sandbox içi komuta verilen oturum izni sandbox dışını kapsamaz.
  `sandbox.allowUnsandboxedCommands: false` ise istek yok sayılır, komut sandbox içinde kalır.
- `sandbox.excludedCommands: ["docker *", "Bash(git push *)"]` desenleri Claude'un `Bash(...)`
  kural söz dizimindedir; sondaki ` *` argümanlı ve argümansız biçimi birlikte eşler. Eşleşen
  komut sandbox dışında, normal onayla çalışır. Zincirde (`&&`, `|`, `;`) **her** komut bir
  desene uyarsa çağrı dışarıda çalışır, biri uymazsa sandbox'ta kalır (`docker ps && curl …`).
  `unshare` ile başlayan komut her zaman sandbox'ta kalır. Eski yıldızsız önek yazımı
  (`docker`) bir sürüm boyunca `docker *` gibi okunur ve bir kez uyarılır.

## Diğer ayarlar

| Ayar | Varsayılan | Anlamı |
|------|-----------|--------|
| `sandbox.fail_if_unavailable` | `false` | `true`: sandbox kurulamazsa komut çalıştırılmaz (sorulmadan engellenir) |
| `sandbox.autoAllowBashIfSandboxed` | `true` | Claude gibi: sandbox içinde çalışan komut ağ kipinden bağımsız sorulmaz. Sandbox gerçekten kurulamıyorsa (ör. Linux'ta socat yok) sorulur. Yıkıcı komutlar, `ask`/`deny` kuralları, plan kipi ve `FOO=bar npm test`, `make CC=clang`, `eval "ls"` biçimleri olağan izin akışından geçer |
| `sandbox.network.strictAllowlist` | `false` | `true`: listede olmayan ad sorulmadan reddedilir |
| `sandbox.allow_localhost` | `true` | Allowlist kipinde `localhost`'a doğrudan erişim |
| `sandbox.hide_secret_env` | `false` | Kullanımdan kalkan uzantı: sır görünümlü ortam değişkenlerini de gizle |
| `sandbox.allow_write` | `[]` | Ek yazılabilir dizinler, ör. `["~/.npm", "~/.cache/pip"]` |
| `sandbox.filesystem.denyRead` | `[]` | Okunamayan yollar (yerleşik liste yok) |
| `sandbox.filesystem.allowRead` | `[]` | Engellenmiş bölgenin içinde yeniden açılan yollar (dar yol kazanır) |

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
  `dangerouslyDisableSandbox=true` (onaylı) kullanın.
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
- macOS'ta yalnız kökteki `.git` korunur; iç içe depoların (alt dizindeki `.git`) yapılandırması
  Linux'ta rg bulunursa (`ripgrep` ayarı ya da PATH) salt okunur bağlanır, macOS'ta korunmaz.
- TLS sonlandırmada istemci HTTP/1.1'e indirilir (ALPN); sertifika sabitleyen (pinning) ya da
  kendi kök deposunu ortamdan okumayan araçlar sonlandırılan bağlantıda başarısız olur. Yer
  tutucu bayt akışında aranır: sıkıştırılmış ya da kodlanmış (Basic auth base64) değer
  değiştirilmez.
- Linux yolu birim testlerle doğrulandı; gerçek bubblewrap davranışı Linux makinede elle denenmelidir.
