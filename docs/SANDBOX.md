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
- **Okuma:** `sandbox.deny_read` yolları okunamaz. Varsayılan liste: `~/.ssh`, `~/.aws`,
  `~/.gnupg`, `~/.azure`, `~/.kube`, `~/.config/gcloud`, `~/.docker/config.json`, `~/.netrc`,
  `~/.git-credentials`, `~/.password-store`, `~/Library/Keychains`. Fusion'ın kendi `.env`'i,
  şifreli kasası ve tarayıcı/web oturum profilleri listede yazılmasa da her zaman engellidir.
- **Ağ:** `sandbox.network: open` (varsayılan, kısıtsız) ya da `allowlist`. Allowlist'te komut
  yalnız Fusion'ın yerel proxy'sine bağlanabilir (`HTTP_PROXY`/`HTTPS_PROXY` ortamı verilir);
  proxy yalnız `allowed_domains`'e bağlanır, `denied_domains` her zaman önce gelir. İzinli bir
  ad iç ağ adresine (127.0.0.1, 10.x, 169.254.x…) çözülürse bağlanılmaz; iç adrese gitmek için
  IP'yi ya da `localhost`'u listeye açıkça yazın. `allow_localhost: true` dev sunucularına ve yerel
  veritabanına doğrudan erişimi açık tutar (Linux'ta yalnız sandbox içinde başlatılanlara).
- **Sır ortamı:** `hide_secret_env: true` iken sandbox içindeki komutun ortamından adı sır gibi
  görünen değişkenler (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `*PASSWORD*`) çıkarılır.

```text
/sandbox ag allowlist
/sandbox izin github.com          # alan adı ekler (ağı allowlist'e alır)
/sandbox izin *.npmjs.org         # alt alan adları
/sandbox engelle gist.github.com
/sandbox kaldir github.com
fusion sandbox izin pypi.org
```

Engellenen bağlantıdan sonra modele `Sandbox ağı engelledi: <alan>` notu gider; izin vermek
kullanıcının kararıdır.

## Sandbox dışında çalıştırma

- Model gerektiğinde `run_shell(command=…, unsandboxed=true)` ister. Bu istek **her seferinde**
  ayrıca sorulur (Otomatik kipte de; "bu oturumda sorma" sunulmaz). Yalnız "İzinleri atla"
  kipi sormaz. `sandbox.allow_unsandboxed: false` ise istek yok sayılır, komut sandbox içinde kalır.
- `sandbox.excluded_commands: ["docker", "git push"]` önekleri her zaman sandbox dışında, normal
  onayla çalışır. Yalnız tek ve sade komut eşleşir: `docker ps && curl …` sandbox içinde kalır.

## Diğer ayarlar

| Ayar | Varsayılan | Anlamı |
|------|-----------|--------|
| `sandbox.fail_if_unavailable` | `false` | `true`: sandbox kurulamazsa komut çalıştırılmaz (sorulmadan engellenir) |
| `sandbox.auto_allow` | `false` | `true`: sandbox içinde VE `network: allowlist` iken komut sorulmaz. Yıkıcı komutlar, `ask`/`deny` kuralları ve plan kipi yine geçerli |
| `sandbox.allow_write` | `[]` | Ek yazılabilir dizinler, ör. `["~/.npm", "~/.cache/pip"]` |

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
- Linux yolu birim testlerle doğrulandı; gerçek bubblewrap davranışı Linux makinede elle denenmelidir.
