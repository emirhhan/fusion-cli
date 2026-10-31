# Fusion ↔ Kits köprüsü

Kits, Fusion masaüstünün yan süreç olarak başlattığı ve iframe ile gömdüğü karakterli ajan
uygulamalarıdır (bkz. `fusion-kits` deposu). Bu belge iki yönlü iletişimi anlatır:
Fusion'dan bir Kit'e iş bırakmak ve bir Kit'in kullanıcının Chrome'unu kullanması (P-063).
Claude Code'daki karşılığı Channels/Dispatch'tir: oturumdan kanala görev bırakmak ve ajanın
kullanıcının tarayıcısına erişmesi.

## 1. Fusion → Kit: gelen kutusu

Her Kit'in bir **Fusion gelen kutusu** sohbeti vardır (ilk teslimde açılır). Fusion'ın
bıraktığı mesaj/görev, bu sohbete bağlı kalıcı bir görev olur; Kit onu kendi sırası gelince
kendi sohbetinde işler. **Makbuz "kuyruğa alındı" demektir, "yapıldı" değil.**

| Yüzey | Nasıl |
|---|---|
| Terminal | `fusion kit liste` · `fusion kit gonder <kit> "<metin>" [--baslik …] [--mesaj]` · `fusion kit gelen <kit>` · `fusion kit durum <kit> <görev-id>` |
| Sohbet (ajan aracı) | `kits_list` → `kit_send(kit, text, title?, kind=gorev|mesaj)` → `kit_task_status(kit, task_id?)` — "şunu Kod Kit'ine ver" denince kullanılır |
| Masaüstü RPC | `kit.listele {}` · `kit.gonder {kit, metin, baslik?, tur: gorev|mesaj}` · `kit.durum {kit, gorev_id?}` |

`<kit>` Kit adı (büyük/küçük harf duyarsız) ya da kimliğidir. Kits şu durumlarda teslimi
reddeder (403): çalışma alanı duraklatılmış, görev yürütme izni kapalı ya da Kit'in **Fusion
izni** kapalı. İzinler Kit ayarlarından değişir; Fusion bunları değiştiremez.

**Adres bulma.** Masaüstü Kits'i başlatırken `KITS_STATE_FILE` verir; Kits dinlediği adresi
ve pid'ini `~/.local/share/fusion-cli/kits/kits-bridge.json` dosyasına yazar (0600; sır
taşımaz). Fusion bu dosyayı okur, pid ölüyse yok sayar; dosya yoksa elle başlatılmış Kits
için `http://127.0.0.1:4410` dener. Ulaşılamazsa hata, Kits'in nereden açılacağını söyler.

**Kapatma.** `runtime.disabled_tools: [kit_send, kits_list, kit_task_status]` araçları
modelden gizler; `fusion kit` komutu ve RPC yalnız kullanıcı isteğiyle çalışır. `kit_send`
REMOTE_WRITE etkilidir: otomatik kipte de onay kartı çıkar.

## 2. Kit → kullanıcının Chrome'u

Fusion içinde açılan her Kit `fusion_browser` aracını görür. Eylemler:

| Eylem | Ne yapar | Onay |
|---|---|---|
| `read` | Açık sekmenin metni ve etkileşimli öğeleri (ref'lerle) | okuma |
| `find` (`value`) | Metne göre öğe bul | okuma |
| `text` (`value`=sayfa) | Tam sayfa metni, sayfa sayfa | okuma |
| `tabs` | Açık sekmeler | okuma |
| `scroll` (`value`=`up|down|left|right[:px]`) | Kaydır | okuma |
| `navigate` (`url`) | Adrese git (iç ağ/metadata adresleri kapalı) | her seferinde |
| `click` (`ref`) | Tıkla | her seferinde |
| `type` (`ref`, `value`) | Alana yaz | her seferinde |
| `key` (`value`, `ref?`) | Tuşa bas | her seferinde |

Akış: Kit (iframe) → `fusion-browser-request` (nonce + izinli origin) → Fusion hostu
(`app/src/kits/kitsBrowserHost.ts`) kullanıcıya sorar → onaylanırsa etkin oturumun
`chrome.kit_komut` RPC'si (`appserver/kits_browser_routes.py`) → Chrome köprüsü. Okuma
eylemleri Kits açık kaldığı sürece bir kez onaylanır; etkileşim her seferinde sorulur.
Yalnız metin döner (ekran görüntüsü taşınmaz), sırlar `redact` ile gizlenir. Chrome
eklentisinin native hostu Kit sürecine **açılmaz**; yetki her zaman Fusion uygulamasındaki
kullanıcı onayında kalır. Chrome köprüsü yoksa ya da eklenti bağlı değilse Kit'e
"kullanılamaz" döner ve nereden bağlanacağı söylenir.

## 3. Doğrulama

- Kits: `npx vitest run tests/kit-inbox.test.ts tests/kits-state-file.test.ts tests/fusion-browser-bridge.test.ts`
- Fusion: `pytest tests/test_kits_tools.py tests/test_kits_routes.py`; `cd app && npx vitest run src/kits/kitsBrowserHost.test.ts src/kits/KitsScreen.test.tsx`
- Elle: Fusion masaüstünde Kits bölümünü aç, terminalde `fusion kit liste`; `fusion kit gonder Kod "Merhaba"` sonrası Kits'te "Fusion gelen kutusu" sohbetinde görevin işlendiğini gör. Kit'e "Chrome'da açık sekmeyi oku" de; izin penceresi çıkmalı.
