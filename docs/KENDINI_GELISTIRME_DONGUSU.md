# Kendini geliştirme döngüsü

Gerçek konuşmadaki hatalar ölçülebilir eval görevine, eval görevleri de istem önerisine
dönüşür. Her halkada son söz kullanıcıdadır: hiçbir şey kendiliğinden kümeye girmez, istem
dosyası kendiliğinden değişmez.

```
konuşma günlüğü ──taslak-uret──▶ taslak ──kabul──▶ kullanıcı kümesi
                                                         │
                       istem dosyası ◀──uygula── öneri ◀─┴─ prompt-opt calistir (+ ayrı küme)
```

Komutlar depo kökünden çalışır (`evals/` ve `prompt_opt/` pakete girmeyen geliştirici
araçlarıdır): `.venv/bin/fusion ...`.

## 1. Hata → taslak

```bash
fusion eval taslak-uret --proje . --gun 7   # son 7 günün konuşması; model ÇAĞIRMAZ
fusion eval taslaklar                       # onay bekleyenler
fusion eval taslaklar tk-0123456789         # istek, kanıt, önerilen ölçüt
fusion eval kabul tk-0123456789             # kullanıcı kümesine ekle (ölçüt varsa)
fusion eval kabul tk-0123456789 --komut "python -m pytest -q" --kume kullanici
fusion eval sil tk-0123456789               # at; aynı hata bir daha önerilmez
```

Taslağı doğuran kanıtlar: açık düzeltme ("hayır, yanlış yaptın"), geri alma isteği, aynı
isteğin yeniden gönderilmesi, `failed`/`partial` biten tur (yalnız sağlayıcı/kota arızasıyla
düşen tur HARİÇ: o istem hatası değildir). Bir soruya verilen "hayır" düzeltme sayılmaz.

Ölçüt yalnız kanıttan çıkarılır: turda doğrulama komutu (pytest, ruff, tsc...) çalıştıysa
`exit_code`, dosya değiştiyse zayıf `file_changed`. İkisi de yoksa taslakta ölçüt YOKTUR ve
`kabul` için `--komut`, `--anahtar` ya da `--dosya` vermen gerekir; ölçütsüz görev kabul
edilmez.

**Gizlilik.** Taslaklar ve kabul edilen görevler yalnız `~/.local/share/fusion-cli/dongu/`
altında (Windows: `%LOCALAPPDATA%\fusion-cli\dongu\`) durur; depoya yazılmaz. Metin yazılırken
sırlar maskelenir, proje yolu köke göre kısalır, ev dizini `~` olur, uzun yapıştırmalar
kırpılır. Silinen sohbetler taramaya girmez. Kabul edilen görevin `setup:` bloğu boştur:
istek proje dosyalarına dayanıyorsa küme dosyasına (`dongu/kume/kullanici.yaml`) ilgili
dosyaları elle ekle.

## 2. Öneri

```bash
fusion prompt-opt calistir --kume kullanici --ayri hata --istem system
fusion prompt-opt oneriler
fusion prompt-opt oneriler on-0123456789    # modelin eklediği metin
```

Gerçek model çağrısı yapar (kota/ücret sana aittir): bir sağlayıcı çağrısı ek madde önerir,
ardından her aday iki kümede koşulur. Güvenceler:

- **Eklemeli.** Model yalnız kısa ek madde yazar (en çok 600 karakter ve temelin %25'i);
  aday, temel metnin birebir korunmuş hâlinin SONUNA eklenir. İstemin baştan yazılması
  yapı gereği imkânsızdır (ACE "context collapse" uyarısı).
- **Aşırı uyum denetimi.** `--kume` ve `--ayri` görev kimliği ya da istek metni paylaşıyorsa
  ya da bir küme 3 görevden küçükse tur HİÇ başlamaz (model çağrısı yapılmaz).
- **Gerilemeyen aday.** Optimizasyon kümesinde en az %2 iyileşmeli ve eskiden geçen hiçbir
  görevi bozmamalı; sonra AYRI kümede de eskiden geçen hiçbir görevi bozmamalı ve başarı
  oranı düşmemeli. Aksi halde öneri kaydedilmez.
- Çıkış kodları: 0 tamam, 1 kullanıcı/yapılandırma hatası, 2 kota ya da erişim yüzünden
  ölçüm durdu (sonuç yazılmaz).

## 3. Uygula / geri al

```bash
fusion prompt-opt uygula on-0123456789   # istem dosyasını yazar
make test                                # istem bütçesi ve davranış testleri
fusion prompt-opt geri-al system         # uygulamadan önceki sürüme döner
```

`uygula`, istemin o anki hâlini önce `dongu/surumler/` altına sürüm olarak kaydeder, sonra
adayı yayımlar ve dosyaya yazar. İstem dosyası öneri üretildikten sonra değişmişse öneri
bayattır ve reddedilir. `geri-al`, dosya elle düzenlenmişse üstüne yazmaz. Geçmiş silinmez;
geri alma yeni bir sürüm olarak yayımlanır.

Optimize edilebilen istemler (`prompt_opt/targets.py` izin listesi): `system`,
`system_chat`, `review`, `compress`. Güvenlik/onay metinleri listede yoktur.

## 4. Haftalık çalıştırma (örnek — otomatik KURULMAZ)

Zamanlayıcıya hiçbir şey eklenmez; aşağıdakiler kopyalayıp kendi makinende kuracağın
örneklerdir. Haftalık işe yalnız **taslak üretimi** önerilir: model çağırmaz, ücreti yoktur,
kümeye ya da isteme dokunmaz. `prompt-opt calistir` kota harcadığı için elle çalıştırılır.

crontab (her pazartesi 09:00; depo yolunu kendininkiyle değiştir):

```cron
0 9 * * 1  cd /yol/fusion-cli && .venv/bin/fusion eval taslak-uret --proje /yol/proje --gun 7 >> ~/fusion-dongu.log 2>&1
```

macOS launchd (`~/Library/LaunchAgents/tr.fusion.dongu.plist`, `launchctl load` ile yükle):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>tr.fusion.dongu</string>
  <key>WorkingDirectory</key><string>/yol/fusion-cli</string>
  <key>ProgramArguments</key>
  <array>
    <string>/yol/fusion-cli/.venv/bin/fusion</string>
    <string>eval</string><string>taslak-uret</string>
    <string>--proje</string><string>/yol/proje</string>
    <string>--gun</string><string>7</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer></dict>
</dict>
</plist>
```

Pazartesi sabahı bakılacak sıra: `fusion eval taslaklar` → mantıklı olanları `kabul`, gerisini
`sil` → kümede en az iki ayrı küme varsa (biri optimizasyon, biri ayrı) elle
`fusion prompt-opt calistir` → `oneriler` → `uygula`.

## 5. Ölçüm izi

Her halka `dongu/kayit.jsonl` dosyasına bir satır ekler (istek ya da istem metni YAZILMAZ):

| olay | alanlar |
|------|---------|
| `taslak_uretildi` | `bulunan`, `yeni`, `kaynaklar` (kaynak türüne göre sayı), `gun` |
| `taslak_kabul` / `taslak_silindi` | `taslak`, `kume`, `olcut` |
| `oneri` | `istem`, `kume`, `ayri_kume`, `sonuc`, `opt_temel`, `opt_skoru`, `ayri_temel`, `heldout_skoru`, `oneri` |
| `oneri_uygulandi` / `oneri_geri_alindi` | `oneri`, `istem`, `surum` |

`oneri.sonuc` değerleri: `onerildi`, `iyilestirme_yok` (temel zaten hepsini geçiyor),
`gecen_aday_yok` (optimizasyon kümesinde yeterli iyileşme yok), `ayri_kume_gerilemesi`
(aşırı uyum işareti; öneri kaydedilmedi).

## Bilinen sınırlar

- Kimliksiz olay kayıtları (`session_id: null`, çoğu olay) dosya sırasına göre en son
  kullanıcı mesajına bağlanır; aynı çalışma alanında iki sekme aynı anda çalışırsa tur
  sonucu yanlış mesaja yapışabilir.
- Düzeltme tespiti kalıp tabanlıdır (Türkçe/İngilizce ifadeler); gerçek bir düzeltmeyi
  kaçırabilir, nadiren de düzeltme olmayan bir cümleyi yakalayabilir. Taslak zaten onaya tabidir.
- Aday istem değerlendirmesi `loop.SYSTEM_PROMPT` gibi modül değişkenini geçici olarak
  değiştirir (görevler sırayla koşar); başka modüllere kopyalanmış metin bu yoldan değişmez.
- Eval görevleri izole boş bir çalışma dizininde koşar; projeye bağlı görevlerde `setup:`
  elle tamamlanmadıkça ölçüm anlamsızdır.
