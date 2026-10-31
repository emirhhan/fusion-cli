# Ajan ekipleri ve dinamik iş akışları

Fusion'da alt ajanlar üç katmanda çalışır:

| Katman | Ne zaman | Araç / komut |
|--------|----------|--------------|
| Tek ya da paralel alt ajan | Birkaç bağımsız iş | `spawn_agent`, `spawn_agents`, `/subtask` |
| Dinamik iş akışı (P-062) | Çok sayıda ajan, evreler, boru hattı | `workflow_run`, `/workflows` |
| Ajan ekibi (P-061) | Birbirine yazan, görev paylaşan üyeler | `team_run`, `/team` |

Hepsi aynı alt ajan çekirdeğini kullanır: kişilik (`uzman`), araç süzgeci, yazma alanı,
`izolasyon: worktree`, masaüstündeki ajan kartları ve "Durdur" düğmesi aynen geçerlidir.
İkisi de yalnız ana ajana sunulur (iç içe ekip/iş akışı yok) ve araç şemaları yalnız
istek bu türdense modele gider: "iş akışı", "workflow", "ultracode", "paralel ajan" gibi
sözler iş akışını, "ekip", "takım", "team" ekibi açar.

## Dinamik iş akışları (`workflow_run`, `/workflows`)

Claude Code'da model bir JS betiği yazar (`agent()`, `parallel()`, `pipeline()`,
`phase()`). Fusion çalıştırılabilir kod yerine **JSON tanımı** kabul eder; tanım eval
edilmez, tek yan etki alt ajanlardır.

```json
{
  "ad": "inceleme",
  "aciklama": "Değişen dosyaları incele ve önceliklendir",
  "girdiler": {"dosyalar": ["src/a.py", "src/b.py"]},
  "eszamanli": 4,
  "adimlar": [
    {"evre": "Keşif", "adimlar": [
      {"her": "{girdi.dosyalar}", "id": "bulgu", "salt_okunur": true,
       "ajan": "{oge} dosyasındaki hataları bul, satır numarasıyla yaz"}
    ]},
    {"evre": "Rapor", "adimlar": [
      {"sira": [
        {"ajan": "Bulguları önem sırasına koy:\n{sonuc.bulgu}"},
        {"ajan": "Şu listeyi kullanıcıya kısa özet yap:\n{onceki}"}
      ]}
    ]}
  ]
}
```

| Düğüm | Anlamı |
|-------|--------|
| `ajan` | Tek alt ajan; istem metni. Seçenekler: `id`, `baslik`, `uzman`, `salt_okunur`, `yazma_alani`, `izolasyon` |
| `paralel` | Liste eşzamanlı koşar (tavan: `eszamanli`) |
| `sira` | Boru hattı; her adım `{onceki}` ile bir öncekinin çıktısını alır. Adım başarısız/iptal olursa kalanlar "atlandı" olur (paralel adım, bir kolu bile başarılıysa kısmi sonuçla sürer) |
| `evre` | Adlı aşama (`adimlar` sırayla); panoda başlık olur |
| `her` | Listedeki her öğe için `ajan` ya da `asamalar` (öğe başına boru hattı); öğeler paralel |

Yer tutucular yalnız `{girdi.X}`, `{sonuc.ID}`, `{onceki}`, `{oge}`, `{oge_no}`; başka
süslü parantezler (istemdeki kod örnekleri) dokunulmadan kalır. İngilizce anahtarlar
(`agent`, `parallel`, `pipeline`, `phase`, `each`, `steps`, `args`) eş anlamlıdır.

**Yazma güvenliği.** Paralel adımlarda dosya yazmayan ajana `salt_okunur: true`, yazana
`yazma_alani` verin. Alanları çakışan yazarlar sırayla, alanı belirsiz yazar tek başına
koşar (`spawn_agents` ile aynı kural).

**Kaydetme.** `workflow_run` çağrısında `kaydet: true` tanımı `.fusion/workflows/<ad>.json`
dosyasına yazar. Kullanıcı düzeyindeki akışlar `<yapılandırma dizini>/workflows/`
altındadır (macOS/Linux: `~/.config/fusion-cli/workflows/`); aynı ad projede varsa proje kazanır.

**Komutlar.**

```
/workflows                       kayıtlılar + son koşular
/workflows inceleme dosyalar=x   kayıtlı akışı (girdilerle) ajana çalıştırt
/workflows goster <ad|koşu>      tanım JSON'u ya da koşunun düğümleri
/workflows iptal <koşu>          koşan akışa iptal işareti (yarım saniyede durur)
/workflows sil <ad>              kayıtlı tanımı sil
fusion workflows [liste|goster|iptal|sil] [--kok <dizin>]
```

Koşu kayıtları `.fusion/workflows/kosular/<kimlik>.json` dosyasındadır (son 50 koşu).
Koşuyu yürüten süreç kapandıysa kayıt "yarım" görünür.

**Masaüstü.** Sohbette koşunun panosu (evre, ilerleme çubuğu, düğüm durumları) ve
altında aynı koşunun ajan kartları görünür. Ajanlar sekmesindeki **İş akışları**
bölümü kayıtlı akışları "Çalıştır" ile başlatır, koşanı "Durdur" ile iptal eder
(RPC: `akis.liste`, `akis.kosu`, `akis.iptal`).

**Bütçe ve ayarlar** (`runtime:`):

| Ayar | Varsayılan | Anlamı |
|------|-----------|--------|
| `dynamic_workflows` | `true` | `false` = araç sunulmaz |
| `dynamic_workflow_max_agents` | `50` | Bir koşunun en fazla ajanı; plan aşarsa koşu hiç başlamaz. Tanımdaki `en_fazla_ajan` yalnız daraltır |
| `dynamic_workflow_max_concurrent` | `0` | Eşzamanlı ajan tavanı; 0 = `max_parallel_agents` |
| `dynamic_workflow_confirm_agents` | `10` | Bu kadar ya da daha çok ajanlı koşu önce sorulur (maliyet uyarısı); 0 = sorma |

Koşunun ajan bütçesi turun `max_subagents_per_turn` tavanından ayrıdır; ajanlar yine de
oturumun alt ajan sahibine bağlıdır, bu yüzden tur iptali ve karttaki "Durdur" onları da
kapatır. `dynamic_workflow_max_agents` aynı zamanda **tur geneli** tavandır: aynı turda
art arda `workflow_run` / `team_run` çağrıları (ve turdaki diğer alt ajanlar) toplamda bu
sayıyı aşamaz; aşacak koşu başlamadan reddedilir. Maliyet sorusu soracak arayüz yoksa
(`fusion -p` gibi) bu tavan tek güvenlik sınırıdır.

**Bilinen fark.** Claude Code iş akışlarını arka planda koşturur ve sohbet sürer; Fusion'da
koşu, onu başlatan turun içinde biter (tur iptal edilirse koşu da durur).

## Ajan ekipleri (`team_run`, `/team`)

Claude Code agent teams karşılığı: **lider** ana ajandır, **üyeler** aynı anda koşan alt
ajanlardır. Üyeler paylaşımlı görev listesinden görev alır, bitirir, yeni görev ekler ve
birbirine, lidere ya da herkese mesaj atar.

```json
{"ad": "site", "hedef": "Açılış sayfasını yap",
 "uyeler": [
   {"ad": "tasarim", "uzman": "tasarimci", "yazma_alani": ["site/css"]},
   {"ad": "kod", "uzman": "kodcu", "yazma_alani": ["site/js"]},
   {"ad": "denetci", "uzman": "testci", "salt_okunur": true}],
 "gorevler": [
   {"baslik": "Renk paleti", "atanan": "tasarim"},
   {"baslik": "Etkileşim", "atanan": "kod"},
   {"baslik": "Son kontrol", "bagimli": ["Renk paleti", "g2"]}]}
```

- Görevler sırayla `g1`, `g2`… kimliği alır; `bagimli` kimlik ya da aynı çağrıdaki görevin
  başlığıdır. Bağımlılığı bitmemiş görev alınamaz, başarısız bağımlılık raporda
  "engellendi" görünür. Görev alma atomiktir (iki üye aynı görevi alamaz).
- Üye araçları yalnız üyelere sunulur: `team_board` (pano + yeni mesajlar),
  `team_task` (`al` / `bitir` / `ekle`), `team_send` (`kime`: üye, `lider`, `herkes`).
  `tools:` listesi dar olan kişilik de bu üç aracı görür.
- **Yazma güvenliği.** Üyeler iş akışıyla aynı kapıdan geçer: salt okur ve
  `izolasyon: worktree` üye herkesle, `yazma_alani` bildiren üye alanı çakışmayanlarla,
  alanı belirsiz yazar üye tek başına koşar. Kapıyı bekleyen üye panoda "sırada" görünür.
- **Boşta bekleme (TeammateIdle).** Koşusu biten üyenin üzerinde kalan görev panoya geri
  döner; üye, kendisine alınabilir görev ya da mesaj gelince yeniden uyandırılır.
  Kimse çalışmıyor ve kimsenin işi yoksa ekip biter; lider panonun son hâlini, lidere
  gelen mesajları ve üye özetlerini rapor olarak alır.
- **Sürdürme.** Pano `.fusion/ekip/<ad>/pano.json`, gelen kutuları
  `.fusion/ekip/<ad>/gelen_kutusu/<üye>.jsonl` dosyalarındadır. Aynı `ad` ile yeniden
  `team_run` (yeni `gorevler` ve `mesajlar` ile) kaldığı yerden sürer.

**Komutlar.**

```
/team                              ekipler ve görev ilerlemesi
/team <hedef>                      lider ekibi kursun ve çalıştırsın
/team goster <ad>                  pano + lidere gelen son mesajlar
/team mesaj <ad> <üye> <metin>     ekibi sürdür, üyeye mesaj ilet
/team sil <ad>                     panoyu ve gelen kutularını sil
fusion ekip [liste|goster|sil] [--kok <dizin>]
```

**Masaüstü.** Sohbette ekibin panosu (üyeler, Bekliyor / Çalışıyor / Bitti sütunları,
posta kutusu) ve altında üye kartları görünür. Ajanlar sekmesindeki **Ekipler** listesi
"Pano" ile `/team goster` çalıştırır (RPC: `ekip.liste`, `ekip.pano`, `ekip.sil`).

**Ayarlar** (`runtime:`):

| Ayar | Varsayılan | Anlamı |
|------|-----------|--------|
| `agent_teams` | `true` | `false` = araç sunulmaz |
| `agent_team_max_members` | `5` | Ekibin en fazla üyesi |
| `agent_team_max_wakes` | `3` | Boşa düşen üyenin yeniden uyandırılma sayısı |
| `agent_team_max_runs` | `16` | Tek `team_run` çağrısındaki toplam üye koşusu |
| `agent_team_confirm` | `true` | Yeni ekip kurulmadan önce maliyet uyarısıyla sor |

**Bilinen farklar.** Claude Code'da lider üyeler çalışırken sohbete devam eder ve üyeler
tmux/iTerm bölmesinde görünebilir; Fusion'da ekip, `team_run` çağrısının içinde koşar ve
masaüstü panosunda izlenir. `TaskCreated` / `TaskCompleted` / `TeammateIdle` kanca
olayları henüz kanca sistemine bağlı değildir.

