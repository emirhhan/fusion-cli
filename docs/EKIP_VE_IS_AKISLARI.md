# Ajan ekipleri ve dinamik iş akışları

Fusion'da alt ajanlar üç katmanda çalışır:

| Katman | Ne zaman | Araç / komut |
|--------|----------|--------------|
| Tek ya da paralel alt ajan | Birkaç bağımsız iş | `spawn_agent`, `spawn_agents`, `/subtask` |
| Dinamik iş akışı (P-062) | Çok sayıda ajan, evreler, boru hattı | `workflow_run`, `/workflows` |

Hepsi aynı alt ajan çekirdeğini kullanır: kişilik (`uzman`), araç süzgeci, yazma alanı,
`izolasyon: worktree`, masaüstündeki ajan kartları ve "Durdur" düğmesi aynen geçerlidir.
İş akışı yalnız ana ajana sunulur (iç içe iş akışı yok) ve araç şemaları yalnız
istek bu türdense modele gider: "iş akışı", "workflow", "ultracode", "paralel ajan" gibi
sözler iş akışını açar.

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
| `sira` | Boru hattı; her adım `{onceki}` ile bir öncekinin çıktısını alır |
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
kapatır.

**Bilinen fark.** Claude Code iş akışlarını arka planda koşturur ve sohbet sürer; Fusion'da
koşu, onu başlatan turun içinde biter (tur iptal edilirse koşu da durur).
