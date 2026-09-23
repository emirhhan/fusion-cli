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

**Görsel QA sınırı — açıkça belirtilir:** `tauri dev` bu ortamda pratik
değildi. Masaüstü değişiklikleri birim testleriyle doğrulandı; ekranda
görülmedi. "Test ettim" demek ile "gözümle gördüm" demek aynı şey değil ve
ikincisi yapılmadı.
