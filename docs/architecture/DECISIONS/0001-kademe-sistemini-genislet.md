# ADR 0001 — Profil sistemi kademe sistemini genişletir, paralelini kurmaz

- Durum: Kabul edildi
- Tarih: 2026-08-02
- Bağlam: Native universal runtime dönüşümü (master prompt)

## Karar

Master prompt "Low/Medium/High/Max profil sistemi" istiyor ve referans olarak
OmniRoute'un profil/routing mimarisini gösteriyor. Fusion'da bu yapının **büyük
kısmı zaten var**: `config/defaults.yaml` içindeki `tiers:` (low, medium, high,
ultra, premium), `config/models.py:TierSpec`, `config/model_select.py:apply_tier`
ve REPL'deki `/level` komutu.

RULES.md "Genel Tasarım": *"Aynı işi yapan ikinci bir yol açılmaz; mevcut yapı
ihtiyacı karşılamıyorsa mevcut yapı genişletilir."*

Bu nedenle master prompt'un önerdiği ayrı `profiles:` yapısı **kurulmayacaktır**.
Bunun yerine mevcut kademe (tier) sistemi execution-profile kavramına genişletilir.

## Eşleme

| Master prompt profili | Fusion kademesi | Aksiyon |
|---|---|---|
| low | `low` | Var — capability metadata + eligibility eklenecek |
| medium (varsayılan) | `medium` | Var — varsayılan zaten dengeli |
| high | `high` | Var |
| max | `premium` | `max` kabul edilen bir ALIAS'tır (`config/profile.py:PROFILE_ALIASES`); `premium`'a çözülür. Görünen ad DEĞİŞTİRİLMEZ — `premium`'u bilen kullanıcı şaşırmaz. `ultra` ara kademe olarak korunur. |
| auto | — | YENİ: `classify.py` çıktısı → kademe seçimi |
| custom | `/model` override | Var — oturum içi model sabitleme |

`ultra` kademesi silinmez: kullanıcı yapılandırmalarında referans olabilir ve
"aynı işi yapan ikinci yol" değil, ladder'da meşru bir ara basamaktır. Görünen
profil adları (`/mode` çıktısı) ile iç kademe adları arasındaki eşleme tek yerde
(config) tutulur.

## Sonuçlar

- Yeni kod, `TierSpec`/`apply_tier`/`task_model_map` üstüne oturur; router,
  `chain.py` ve `retrying.py` **korunur**.
- "reasoning effort" kademeden AYRI yeni bir kavramdır (mode ≠ effort); kademeye
  gömülmez, ayrı `ReasoningEffort` tipi olur.
- Model picker'ın eligibility filtrelemesi, kademeye capability metadata eklenince
  mümkün olur (Faz 2).
- Master prompt'un "reimplement independently" kararı bu alan için REDDEDİLDİ;
  gerekçe: mevcut yapı ihtiyacı karşılıyor ve ölçülmüş kararlar taşıyor.

## Provenance

- Kaynak fikir: OmniRoute profil/tier composition, master prompt §7–§11.
- Doğrudan kopyalanan kod: yok.
- Fusion uygulaması: mevcut `tiers`/`TierSpec` genişletmesi.
