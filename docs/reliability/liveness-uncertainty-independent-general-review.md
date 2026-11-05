# Belirsiz canlılık yoklaması: bağımsız genel inceleme

İncelenen commit: `d609ac896d8d989b96f45705b0f2e97c7c3e85e3`.
Karar: **APPROVE**. Yeni bulgu yok. Üretim kodu değiştirilmedi.

Kaynak, testler ve `pyproject.toml` ayrı `git archive` snapshot'ına çıkarıldı;
asıl sanal ortam Python'u ve snapshot'a bağlı `PYTHONPATH=src` kullanıldı.
Kapsam `liveness.py`, ilgili testler ve açıklama belgesiyle sınırlı.
`loop.py` commit içinde değişmiyor; mevcut tüketici/izleyici temizliği ve
çağrı/tur sınırları çevre koduyla birlikte incelendi.

Yoklama sonucu üç durumda ele alınıyor: başarılı yanıt/hız sınırı `None`, somut
hata kısa metin, zaman aşımı veya teşhis üretmeyen durum `UnknownHealth`.
Boş akış, hata ayrıntısı olmayan başarısız sonuç, sağlayıcı sonucuna çevrilmiş
zaman aşımı ve yerel kurulum/ayrıştırma istisnası birincil çağrının öldüğünün
kanıtı yapılmıyor. Eski `None`/hata metni sözleşmesi korunuyor.

Belirsiz yoklamada izleyici birincil çağrıyı iptal ettirmiyor; yeniden yoklama
mevcut aralıkta sürüyor. Kullanıcı iptali `CancelledError` olarak yayılıyor.
Birincil çağrı ve yoklama temizliği mevcut tüketici tarafından bekleniyor.
Birincil çağrının kendi zaman aşımı ve yetkili tur sınırları değiştirilmedi.
Yoklama sürerken birincil akış parçası gelmişse bu doğrudan gözlem yoklamanın
hata metninden önce değerlendiriliyor. Somut bağlantı hatası mevcut erken
iptal/yeniden deneme yolunu kullanmaya devam ediyor.

Kontrollü kuyruk deneyinde yoklaması zaman aşımına uğrayan birincil çağrı daha
sonra başarıyla tamamlanıyor. Bu, istemci tarafında gereksiz iptal edilebilen
bir durumun varlığını kanıtlar; önceki gerçek NIM A/B çağrılarının başarılı
olacağını veya upstream sorunun kök nedenini kanıtlamaz. Sağlayıcı/model
parametreleri, uygulama kurulumu ve canlı kabul davranışı bu onayın dışında.

## Bağımsız doğrulama

Görev çalışma alanında `work/reliability-v2/` altında tutulan günlükler:

| Günlük | Sonuç | Sonlanmış süreç |
|---|---|---|
| `general-liveness-d609-tests.log` | 174 geçti; canlılık, belirsizlik, dış tur sınırı, model tekrarları, öğretmen tekrarı ve ajan döngüsü | `96719`, çıkış 0 |
| `general-liveness-adjacent-d609.log` | 59 geçti; akış canlılığı, model hataları, tur bütçesi, yeniden deneme | `6546`, çıkış 0 |
| `general-liveness-error-boundaries-d609.log` | 9 bağımsız kontrol geçti; sağlayıcı kurulumu, sonuç hata sınıfları, iptal | doğrudan çıkış 0 |

Toplam **242 test geçti**. Ajan döngüsü testinde mevcut upstream Pydantic
`ReadOnly` uyarısı görüldü; test hatası oluşmadı. Ruff değişen kaynak ve iki
test dosyasında, mypy `liveness.py` üzerinde geçti (`2750`, çıkış 0).
İncelemeye ait çalışan süreç kalmadı. Gerçek sağlayıcı çağrısı, tam pytest
koşusu, yerel uygulama veya canlı bilgisayar işlemi yapılmadı.

İncelenen `src/fusion_cli/engines/agent/liveness.py` SHA-256:
`8dd09cd464ce0e248dcbaeeb9d4bf4bb887c0c6b47805941c6b5ffb8deeeb1ec`.

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE** — belirtilen sabit kaynak kapsamı.
