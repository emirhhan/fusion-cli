# Arayüz Backlog'unun Kapatılması (23 Eylül 2026)

Kaynak: `reports/2026-09-22-arayuz-paritesi-sonuc.md` — Faz 5'in BACKLOG'a
düşen üç maddesi. Hepsi "gerçekten eksik" diye kendi taramasıyla doğrulanmış,
kapsamları belgelenmiş, yalnız zaman kalmamıştı.

## Faz U1 — `@` ile dosya anma (G6)

Bugün `Composer.tsx`'te hiçbir `@` işleyicisi yok; dosya eklemenin tek yolu
sürükle-bırak ya da ataç düğmesi. Claude'da `@` yazmak proje dosyaları
arasında arama açar.

**Veri kaynağı — merkezi tutulacak.** `core/repo_map.py` içinde 22 Eylül'de
yazılan `_git_source_files` zaten "git biliyorsa ondan al, yoksa budamalı
yürü" mantığını kuruyor ama uzantıyla sınırlı ve modüle gömülü. Bu mantık
`core/project_files.py`'ye çıkarılır; `repo_map` onu uzantı süzgeciyle,
yeni arama onu sorgu süzgeciyle kullanır (RULES.md "Genel Tasarım": tek
sorumluluk, kopyala-yapıştır yok).

1. `core/project_files.py` — `project_files(root)`: git'in bildiği dosyalar
   (`--cached --others --exclude-standard`), git yoksa budamalı `os.walk`.
   `repo_map` bu modülü kullanacak şekilde sadeleşir.
2. `core/file_match.py` — saf eşleştirme: alt dizi (subsequence) puanlaması,
   tam alt-dizge önce, dosya adı eşleşmesi yol eşleşmesinden önde.
3. `appserver/file_search.py` + `proje.dosya_ara` RPC.
4. `Composer.tsx`: `@` tetikleyicisi, açılır liste (komut paletiyle AYNI
   klavye sözleşmesi: ↑/↓/Enter/Esc), seçimde yolu metne yerleştirme.
5. Testler: eşleştirme saf testleri, RPC testi, `Composer.test.tsx`.

## Faz U2 — Takip önerileri (G7)

Tur bittiğinde 2-3 mantıklı sonraki adım önerilir. **Yeni model çağrısı
AÇILMAZ** (Faz 5'te kararlaştırıldı): öneriler turun kendi kanıtından
türetilir — değişen dosyalar, çalıştırılan komutlar, başarısız doğrulama.

1. `core/followups.py` — saf üretici: `AgentOutcome`/tur kaydından öneri
   listesi. Sabit metin değil, turun gerçeğine bağlı.
2. CLI: tur sonunda gösterim.
3. Masaüstü: cevabın altında tıklanabilir rozetler.
4. Testler: hangi turda hangi önerinin çıktığı kilitlenir; kanıt yoksa
   öneri de YOK (uydurma öneri, yalan başarıdan farksızdır).

## Faz U3 — Alt ajan kartları ve düşünme bloğu (G3/G4 masaüstü)

CLI'de ikisi de var (`┌ alt-ajan` başlığı, `--show-thinking`). Masaüstünde
karşılıkları yok. Olay akışında bu bilgi zaten taşınıyor mu, önce o
ölçülecek; taşınmıyorsa protokole eklenecek.

## Kalite kapısı

Her faz sonunda backend `ruff check . && mypy && pytest -q`, masaüstü
`npm test` + `tsc --noEmit`. Üçü temizse Türkçe conventional commit.

**Görsel QA sınırı:** `tauri dev` bu ortamda pratik değil. Masaüstü
değişiklikleri birim testleriyle doğrulanır; "ekranda gördüm" DENMEZ.
