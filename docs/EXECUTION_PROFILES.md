# Çalışma Profilleri ve Reasoning Effort

Fusion'da iki ayrı eksen vardır ve **birbirinden bağımsızdır**:

## Otomatik profesyonel yürütme — görevin nasıl işlendiği

Yeni kurulumlarda `workflow_mode: auto` varsayılandır. Bu, model profilinden ve
onay kipinden ayrıdır: basit sohbet/tek cevap görevleri hızlı yolda kalır; kod
değişikliği, çok dosya, test, dış etki veya belirsiz araç kullanımı içeren görevler
tipli plan, adım kanıtı, sınırlı kurtarma ve final kabul kapısına yönlenir.

Planlı yolda Fusion:

- her adımın bağımlılığını ve başarı koşulunu doğrular;
- güvenli olmayan dış etkileri kör biçimde tekrar etmez;
- bütçe aşımında checkpoint alıp başarı iddia etmeden duraklar;
- sonraki çalıştırmada post-condition'ı yeniden ölçerek güvenle devam eder.

`workflow_mode: always` tüm kök görevleri planlı yola alır; `off` yalnızca ileri
uyumluluk/teşhis için hızlı yolu zorlar. Varsayılan `auto` değiştirilmese de tüm
kullanıcılar profesyonel akışı gerektiren görevlerde otomatik olarak korumayı alır.

### Çalışma sırasında yükseltme

Başlangıç kararı her zaman doğru olmak zorunda değildir. Kapsamı baştan belli
olmayan görevler `fast_promotable` yolunda başlar: hızlı çalışır, ama tur BÜYÜRSE
planlı yürütmeye devredilir. Yükseltme için iki koşul birlikte aranır:

1. Tur yarım kalmıştır (model hata verdi, adım sınırına dayandı ya da bütçe durdu).
2. Büyüme kanıtlanmıştır: üç veya daha fazla bekleyen iş, ikinci dosya/bileşen,
   ikinci araç ailesi, bir araç çıktısına bağlı sonraki iş, teşhis gerektiren
   hata, ayrı doğrulama gerektiren dış etki veya tükenen hızlı yol bütçesi.

Tamamlanmış bir hızlı tur ASLA yükseltilmez — aynı iş ikinci kez yapılmış olurdu.
Yükseltme tek yönlüdür ve kullanıcıya gerekçesiyle bildirilir (terminalde durum
satırı, masaüstünde ilerleme adımı). Plan üreten alt tur ham mesaj geçmişini
almaz; yalnız görev özeti, yükseltme gerekçesi, dokunulan dosyalar, bekleyen
işler ve araç kanıtından oluşan tipli bir bağlam alır — böylece zaten yapılmış iş
tekrar planlanmaz.

## Mode (çalışma profili) — hangi model

`/mode` komutu modeli/kademeyi seçer. Profil = mevcut kademe sistemi (RULES gereği
ikinci bir yapı kurulmadı, kademe sistemi genişletildi).

| Profil | Amaç |
|--------|------|
| `auto` | Görevi sınıflandırıp uygun kademeyi HER TUR kendisi seçer |
| `low` | Hızlı, ekonomik, basit işler |
| `medium` | Dengeli — günlük kodlama (varsayılan) |
| `high` | Zor debugging, mimari, çok dosyalı iş |
| `max` | En yüksek kalite (`premium` kademesine alias) |

Kullanım:

```
/mode              # seçim ekranı (auto + kademeler)
/mode high         # doğrudan
/mode auto         # her tur göreve göre kademe seç
```

`auto` açıkken her turda görev sınıflandırılır (`classify_task` + karmaşıklık
işaretleri) ve seçilen profil GEREKÇESİYLE basılır — örn. "Tüm mimariyi yeniden
tasarla" → `max` (karmaşıklık işaretleri: mimari, tüm, yeniden tasarla).

`auto` bir kademe değil oturum kipidir; elle bir profil seçmek onu kapatır.

> Not: `/mode` (execution profile) ≠ `/auto`·`/plan` (onay/permission modu). İkisi
> ayrı ayarlardır.

## Effort (reasoning yoğunluğu) — ne kadar düşünsün

`/effort` komutu, seçilen model reasoning DESTEKLİYORSA düşünme yoğunluğunu ayarlar.

```
/effort            # seçim ekranı
/effort high
```

| Seviye | Davranış |
|--------|----------|
| `auto` | Parametre gönderilmez; karar modele bırakılır |
| `low` / `medium` / `high` | Doğrudan sağlayıcıya iletilir |
| `xhigh` / `max` | Desteklenen en yakına (`high`) iner; indirgeme bildirilir |

**Model desteğine göre gating:** seçilen model reasoning desteklemiyorsa (`reasoning`
etiketi yok) `reasoning_effort` parametresi **hiç gönderilmez** — hatalı istek
kurulmaz. Effort yalnızca birincil kodlama (agent) yoluna uygulanır; utility çağrıları
(bağlam sıkıştırma, ders çıkarımı) effort almaz.

Effort oturum boyunca yaşar (onay modu gibi), kalıcılaştırılmaz.
