# Çalışma Profilleri ve Reasoning Effort

Fusion'da iki ayrı eksen vardır ve **birbirinden bağımsızdır**:

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
