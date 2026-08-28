# Task 2 — Mesaj protokolü

## Durum

Tamamlandı. JSON Lines protokolü ve odaklı testler eklendi.

## Dosyalar

- `src/fusion_cli/appserver/protocol.py`
- `tests/test_appserver_protocol.py`

## RED / GREEN kanıtı

- RED: `.venv/bin/python -m pytest -q tests/test_appserver_protocol.py` — toplama aşamasında `ModuleNotFoundError`, modül henüz yoktu.
- GREEN: Aynı komut — `11 passed`.

## Kalite komutları

- `.venv/bin/ruff check src/fusion_cli/appserver/protocol.py tests/test_appserver_protocol.py` — geçti.
- `.venv/bin/ruff format src/fusion_cli/appserver/protocol.py tests/test_appserver_protocol.py` — dosyalar değişmedi.
- `.venv/bin/mypy src` — `Success: no issues found in 202 source files`.
- `.venv/bin/python -m pytest -q` — mevcut `tests/test_diff.py::test_eklenen_satir_yesil_silinen_kirmizi_boyanir` testi, ANSI renk kodu beklentisi nedeniyle başarısız; protokol testleri etkilenmedi.

## Öz inceleme

Mesaj anahtarları ve tür değerleri brief’teki Türkçe wire biçimine uygun. Kod çözücü bozuk, boş, bilinmeyen ve eksik alanlı girdilerde istisna yükseltmeden `None` döndürüyor. Kodlayıcılar `ensure_ascii=False` ile tek fiziksel JSON satırı üretiyor. Import-time I/O yok; değişiklikler yalnızca Task 2 dosyalarında.

## Commit / çalışma ağacı

Commit: `4fca25d2b72011981d5857daacc8398230eb6c6c`

` :memory:.ses` ve `index.html` mevcut, izlenmeyen kullanıcı dosyaları olarak korunuyor.

## Artifact

Rapor dosyası oluşturuldu.
