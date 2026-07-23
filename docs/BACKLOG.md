# BACKLOG

Taşıma sırasında ortaya çıkan, o fazın kapsamına girmediği için ertelenen işler.
CLAUDE.md gereği kod içine `TODO`/`FIXME` yazılmaz; her şey buraya düşer.

## Faz 2+ için taşınacak (eski projede mevcut, henüz taşınmadı)

- Fusion motoru: paralel adaylar, straggler kesme, hakem, sentez
- Araç katmanı: kayıt defteri, executor'lar, tehlike tespiti, diff önizleme
- Agent motoru: tool-calling döngüsü, reflexion, öz-eleştiri, alt-ajan
- Bellek: performans belleği, ders belleği, semantik kod indeksi, embedding seçimi
- REPL: prompt_toolkit girişi, onay modları, slash komut kayıt defteri, tema
- Gözlemlenebilirlik: Langfuse izleme, oturum maliyeti takibi

## Karar bekleyen

- **Yapılandırma taşması:** `config show` çıktısı büyüdükçe tablo görünümüne geçmeli mi?
- **`--json` çıktısı:** olay veriyolu hazır; JSON dinleyicisi eklemek kolay. Hangi fazda?
- **Sürüm sabitleme:** `requirements.lock` üretilmeli mi, yoksa `pyproject` sınırları yeterli mi?

## Eski projeden düzeltilerek taşınacak hatalar

- Maliyet takibi eski projede yalnızca streaming turlarında çalışıyordu; hakem/sentez/ders
  çağrıları sayıma girmiyordu. Yeni yapıda tek kaynak: `ModelCallFinished` olayı.
- `config.yaml` iki kopya halinde elle senkronlanıyordu. Çözüldü: tek `defaults.yaml`.
- Kod içi varsayılanlar ile dosyadaki değerler ayrışmıştı. Çözüldü: dataclass'ta varsayılan yok.
