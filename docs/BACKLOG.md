# BACKLOG

Taşıma sırasında ortaya çıkan, o fazın kapsamına girmediği için ertelenen işler.
CLAUDE.md gereği kod içine `TODO`/`FIXME` yazılmaz; her şey buraya düşer.

## Taşıma tamamlandı

Eski projeyle **özellik eşitliği doğrulandı**: 31 slash komutunun ve 24 aracın tamamı
yeni yapıda mevcut (karşılaştırma betikle yapıldı, elle değil).

Bilinçli olarak taşınmayan iki şey:

- **`live_input`** (tur çalışırken canlı giriş) — eski projede deneyseldi ve varsayılan
  olarak kapalıydı. Satır bozulmalarının kaynağı buydu; yeni yapıda giriş satırı ve akan
  çıktı asla aynı anda ekranda değil. İstenirse olay veriyolu üzerinden çakışmasız
  biçimde kurulabilir.
- **`agent_max_iterations`** → `agent_max_steps` olarak yeniden adlandırıldı (aynı işlev).

## Eski projeden düzeltilerek taşınan hatalar

- **Maliyet takibi çağrı yollarını atlıyordu** (yalnızca streaming turları sayılıyordu).
  Çözüldü: tek kaynak `ModelCallFinished` olayı; görünürlük (`background` bayrağı) ile
  muhasebe ayrıldı. Hakem, sentez, öz-denetim, ders çıkarımı ve bağlam sıkıştırma artık
  gösterilmiyor ama sayılıyor.
- **`config.yaml` iki kopya halinde elle senkronlanıyordu.** Çözüldü: tek `defaults.yaml`.
- **Kod içi varsayılanlar dosyadaki değerlerle ayrışmıştı.** Çözüldü: dataclass'ta
  varsayılan yok; eksik alan yükleme anında hata veriyor ve test bunu kilitliyor.
- **Çıktı çakışması** (cümlenin ortası araç kartının altına düşüyordu). Çözüldü: motorlar
  konsolu tanımıyor, olaylar tek veriyolundan sırayla akıyor.
- **Görev listesi modül-global'di**; alt-ajanlar ana ajanınkini eziyordu. Çözüldü:
  `ToolContext` üzerinde taşınıyor.
- **"İş yarım kaldı" sezgiseli** kısa ama tam cevapları (`src/app.py:42`) yarım sayıp
  aynı cevabı iki kez bastırıyordu. Çözüldü: somut teslim işaretleri tanınıyor.

## Karar bekleyen

- **Sürüm sabitleme:** `requirements.lock` üretilmeli mi, yoksa `pyproject` alt/üst
  sınırları yeterli mi?
- **Yol sınırlaması:** araçlar proje kökü dışına da yazabiliyor (eski davranış korundu;
  onay akışı + diff önizlemesi koruyor). `ToolContext`'e kök dışını reddeden bir kip
  eklenmeli mi?
- **`config show` görünümü:** yapılandırma büyüdükçe tablo görünümüne geçmeli mi?

## İzlenecek

- **Model bazen bozuk çıktı üretiyor.** `nemotron-3-super` yüksek bağlamda token çorbası
  üretebiliyor (gerçek bir turda görüldü; basit bir "VPN ne işe yarar" sorusunda "We need
  to answer:" ardından uzun token çorbası olarak tekrarlandı). Öz-denetim her iki seferde
  de yakalayıp düzeltici tur açtı, sistem kurtardı ve doğru cevabı verdi. Mimari gerilim:
  agent modu token'ları CANLI akıtır, öz-denetim ise tur bittikten SONRA çalışır; bu yüzden
  ham çöp düzeltmeden önce ekranda görünür. Gizlemek ya akışı (çekirdek özellik) feda eder
  ya da güvenilmez sezgisel gerektirir — bu yüzden gösterim tarafına dokunulmadı. Gerçek
  kaldıraç model seçimi: tekrar sıklaşırsa varsayılan agent modeli daha kararlı bir ücretsiz
  modelle değiştirilmeli (davranış/kimlik değişikliği — ayrıca konuşulur). `fusion models
  --fetch` ile canlı katalogdan alternatif bakılabilir.
- **Hakem eksik puanlama yapabiliyor:** üç aday yanıtladığında bazen ikisine puan veriyor.
  Ayrıştırıcı yalnızca geçerli adları aldığı için sorun çıkmıyor ama tablo eksik görünüyor.
- **`web_search` HTML kazımaya dayanıyor.** İki uç denenerek dayanıklılık sağlandı; kazıma
  mantığı saf fonksiyonlarda ve testli, uç değişirse yalnızca regex güncellenir.
- **ChromaDB kurulumu ağır** (~350 MB, onnxruntime dâhil). Depolama protokol arkasında
  olduğu için daha hafif bir arka uca (ör. sqlite-vec) geçmek `memory/` dışına dokunmaz.
- **Canlı input yok.** Tur çalışırken yazılamıyor; giriş satırı ve akan çıktı bilinçli
  olarak aynı anda ekranda değil (eski projedeki satır bozulmalarının kaynağı buydu).
  İstenirse olay veriyolu üzerinden çakışmasız bir canlı input kurulabilir.
- **Akış fusion modunda kapalı.** Hakem ve sentez paralel çalıştığı için, akan cevabın
  ortasına arka plan ilerlemesi düşmesin diye. Agent modu akıtarak çalışır.

## Çözüldü

- **Terminal yeniden boyutlandırmada `❯` çoğalması.** Alta sabitlenmiş `bottom_toolbar`
  durum çubuğu, reflow eden terminallerde prompt_toolkit'in bayat imleç modeliyle yaptığı
  silmeyi ıskalatıp `❯` kopyaları biriktiriyordu. Durum, giriş satırının içine (❯'nin
  soluna) alındı; ayrı çok-satırlı widget kalktı. Reflow taklit eden headless harness ile
  doğrulandı: fix öncesi 4-5 yetim `❯`, sonrası 1. `rprompt` denendi ama yetersizdi (3);
  yalnızca durumu giriş satırına almak tam çözdü.