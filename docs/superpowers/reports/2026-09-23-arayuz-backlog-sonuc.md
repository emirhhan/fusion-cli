# Arayüz Backlog'u Sonuç Raporu (23 Eylül 2026)

Plan: `plans/2026-09-23-arayuz-backlog.md`. Faz 5'in BACKLOG'a düşen üç maddesi
(G6, G7, G3/G4'ün masaüstü tarafı) kapatıldı.

## Faz U1 — `@` ile dosya anma (G6)

`Composer.tsx`'te hiçbir `@` işleyicisi yoktu; dosya eklemenin tek yolu
sürükle-bırak ya da ataç düğmesiydi.

**Veri kaynağı merkezîleştirildi.** 22 Eylül'de `repo_map.py` içine yazılan
"git biliyorsa ondan al, yoksa budamalı yürü" mantığı `core/project_files.py`'ye
çıkarıldı. `repo_map` artık onu uzantı süzgeciyle kullanıyor (199 satıra indi),
dosya anma ise sorgu süzgeciyle. Kopyala-yapıştır yok.

Yol boyunca bir tutarsızlık bulundu ve düzeltildi: git yolu nokta ile başlayan
DOSYALARI döndürüyordu (`.gitignore`, `.claude/launch.json`), elle yürüyüş
atlıyordu. İki yol farklı liste verseydi `@` önerileri deponun git olup
olmamasına göre değişirdi; test bu sözleşmeyi kilitliyor.

**Eşleştirme saf tutuldu** (`core/file_match.py`): alt dizi puanlaması, açık
kademelerle. Kademe kullanılıyor çünkü toplam puanda kısa bir yol doğru dosyayı
geçiyordu — ölçüldü: `composer` sorgusu `docs/composer-notlari.md`'yi
`screens/Composer.tsx`'in önüne koyuyordu. Şimdi uzantısız adı sorgunun AYNISI
olanlar her zaman önce geliyor.

| Katman | Dosya |
|---|---|
| Dosya listesi | `core/project_files.py` (48 ms, 1.319 dosya) |
| Eşleştirme | `core/file_match.py` (saf) |
| RPC | `appserver/file_search.py` + `proje.dosya_ara` |
| Ayrıştırma | `app/src/screens/dosyaAnmasi.ts` (saf) |
| Arayüz | `Composer.tsx` — komut paletiyle AYNI klavye sözleşmesi |

Önbellek 2 saniyelik: her tuş vuruşunda disk taranmıyor ama agent'ın az önce
yazdığı dosya listede görünüyor. Kök değişince düşürülüyor.

## Faz U2 — Takip önerileri (G7)

Faz 5'te kararlaştırılan kısıt uygulandı: **yeni model çağrısı AÇILMAZ.**
Öneriler turun kendi sayaçlarından türüyor (`core/followups.py`).

İkinci kural daha önemli: **kanıt yoksa öneri de yok.** Boş bir turun altına
"testleri çalıştır" yazmak, yapılmamış işi yapılmış gibi gösteren yalan
başarıdan farksız bir gürültüdür. Her kuralın bir kanıt koşulu var; hiçbiri
sabit metin döndürmüyor. Örnek: proje doğrulama komutu tanımlı DEĞİLSE
"doğrulamayı çalıştır" önerilmiyor, çünkü çalıştırılacak komut yok.

Sıra da kanıta bağlı: yanlış çalışma dizini her şeyin önüne geçiyor (doğru
klasöre geçilmeden başka hiçbir öneri anlamlı değil), sonra düşen doğrulama,
sonra bütçe sınırı.

Köprü ayrı bir modülde (`engines/agent/turn_evidence.py`) çünkü `core`
katmanı `engines`'e bakamaz. Kural ile köprü ayrı test ediliyor: bu depoda
daha önce "modül yazılmış ama hiçbir yerden çağrılmıyor" durumu yaşandı
(depo haritası, 6 Eylül denetimi).

## Faz U3 — Alt ajan kartları ve düşünme bloğu (G3/G4 masaüstü)

Ölçüm önce yapıldı: `SubAgentStarted`/`SubAgentFinished` olayları masaüstüne
ULAŞIYORDU ama `olayMetni.ts` onları hiç tanımıyordu. Aynı şekilde
`ModelCallFinished.result.reasoning` serileştiriciden geçiyordu ama hiç
okunmuyordu. Protokole ekleme GEREKMEDİ; yalnız okuma eklendi.

- Alt ajan adımları artık `altAjan` işaretiyle geliyor ve listede kenar
  çizgisi + rozetle ayrılıyor (CLI'deki `┌ alt-ajan` karşılığı).
- Düşünme metni `dusunme` alanında taşınıyor ve "adımları göster" açıkken
  çiziliyor (CLI'deki `--show-thinking` karşılığı). **Düşünme yoksa adım da
  açılmıyor** — her model çağrısı için boş satır akışı ikiye katlardı.

Yol boyunca bir hata kendi kendime yakalandı: stilleri hiçbir yerden import
edilmeyen yeni bir `ActivityLine.css` dosyasına yazmıştım, ölü kalacaktı.
Mevcut `.activity__*` kurallarının yanına (`Conversation.css`) taşındı.

## Kalite kapısı

Backend: `ruff check .` temiz, `mypy` 362 dosyada temiz, tam `pytest` yeşil.
Masaüstü: `tsc --noEmit` temiz, **676 test yeşil** (89 dosya).

## Görsel doğrulama — YAPILDI

Önceki fazlarda "bu ortamda pratik değil" denip atlanmıştı; bu turda gerçekten
yapıldı ve varsayım yanlış çıktı.

**1. Tarayıcı paneli (gerçek bileşen kodu, sahte veri).** `npm run dev` ile
Vite sunucusu açıldı. Uygulamanın tamamı Tauri köprüsü olmadan açılmıyor
(`transformCallback` hatası, beklenen), bu yüzden geçici bir kontrol sayfası
`Composer` ve `Conversation`'ı gerçek kodlarıyla çizdi. Görülenler: takip
önerisi rozetleri hap biçiminde, alt ajan adımları rozet + sol kenar
çizgisiyle ayrık, düşünme metni sönük ve küçük puntoyla. Sayfa kontrolden
sonra SİLİNDİ (commit edilmedi).

Bu sırada iki kendi hatam yakalandı: stilleri hiçbir yerden import edilmeyen
yeni bir `ActivityLine.css` dosyasına yazmıştım (ölü kalacaktı, taşındı) ve
sahte verideki adım listesinde sonuç adımı yoktu, bu yüzden bileşen "çalışıyor"
halinde kalıp adım listesini hiç çizmiyordu.

**2. Kurulu uygulama (gerçek uçtan uca).** `Fusion.app` açıldı ve AppleScript
ile sürüldü. `@comp` yazıldığında liste kullanıcının GERÇEK çalışma alanından
gerçek dosyalarla açıldı:

```
@Composer.test.tsx   01-Projeler/fusion-cli/app/src/screens/Composer.test.tsx
@compression.py      01-Projeler/fusion-cli/src/fusion_cli/core/compression.py
@compaction.py       01-Projeler/fusion-cli/src/fusion_cli/engines/agent/compaction.py
@components.css      .../gateway/static/components.css
```

React → `proje.dosya_ara` → `project_files` → `file_match` → geri: tam zincir
canlı çalıştı.

**Doğrulanamayan:** kurulu uygulamada TAM bir tur koşturulamadı. Birincil
sağlayıcı (`chatgpt_web`) insan doğrulaması beklediği için tur başlamadan
duruyor ve arayüz "Sağlayıcı doğrulama istiyor" diyalogunu gösteriyor. Bu
yüzden takip önerisi rozetleri GERÇEK bir turun ardından görülmedi — yalnız
bileşen düzeyinde doğrulandı. Kullanıcı `fusion web-login chatgpt_web` ile
doğrulamayı tamamladıktan sonra bu da görülebilir.
