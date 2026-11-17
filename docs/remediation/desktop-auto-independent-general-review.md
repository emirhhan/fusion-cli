# Masaüstü otomatik profil: bağımsız genel inceleme

Sabit kaynak: `a58859c1a6400d875d256301346744d881b31a4f`.
Kaynak, testler ve `pyproject.toml` ayrı snapshot'ta incelendi. Üretim dosyası
değiştirilmedi. Karar: **WARNING — bir MEDIUM sohbet sahipliği yarışı**.

## MEDIUM: kabul ile çalıştırma arasındaki sohbet değişimi yeni modelin üzerine yazılıyor

Dosya: `src/fusion_cli/appserver/session.py:3352`, benimseme koruması `:3393`.

Gönderim kabulünde yapılandırma ve auto bayrağı yakalanıyor; görünür sohbet
nesli ise `_run_turn` içinde daha sonra okunuyor. Arada
`_execute_submission` kalıcı `state="running"` güncellemesini bekliyor.
Bu bekleme sırasında `oturum.baslat` başka sohbete bağlanabiliyor. Aynı
`ReplState` ve yapılandırma korununca yeni koruma yeni sohbetin neslini
eski işin başlangıç nesli sanıyor; üç karşılaştırma da geçiyor.

Gerçek AppSession yeniden üretimi:

1. `high` model yapılandırmasında `/mode auto` açıkken ad değiştirme işi kabul edilir.
2. `submission_store.finish(state="running")` kontrollü bekleme noktasında tutulur.
3. Gerçek `oturum.baslat {sohbet_id: "other-chat"}` isteğiyle yeni sohbete geçilir.
4. Eski iş serbest bırakılınca kendi düşük profilini yeni sohbetin oturumuna benimsetir.

Yeni sohbetin önceki `high` yapılandırması `low` ile değişti. Bu test, yalnız
sınıflandırma thread'i beklerken nesil değişimini yapan mevcut kontrolden
farklı bir başlangıç penceresini kapsıyor. İşin kendi kabul edilmiş yapılandırmasıyla
çalışması ayrı; burada hata eski işin yeni sohbetin seçimini değiştirmesi.

Düzeltme: benimseme sınırını iş kabulündeki sohbet/kök/nesil sahipliğine bağla;
yalnız `_run_turn` başında okunan mevcut görünür nesli yeterli sayma. Mevcut
iptal, elle yapılandırma değişikliği ve tekrar makbuzu korumaları korunmalı.

## Doğrulanan diğer kapsam

CLI/TUI seçim mantığı ortak yardımcıdan aynı sınıflandırıcı/alias/kademe
uygulayıcısını kullanıyor. Masaüstünde seçim çalışma görevine ait; iptal edilmiş
thread yalnız değer hesaplıyor. Auto kapalı elle/strict seçim, eksik kademe,
beceri model önceliği, engellenmiş MCP filtresi, otomatik devam ve tamamlanmış
gönderimin tekrar yürütülmemesi mevcut kontrollerde korundu.

Bağımsız ek kontrollerde sınıflandırma beklerken yapılan elle model değişikliği
benimsenmedi; sınıflandırıcı istisnası yürütücüyü başlatmadan makbuzu başarısız
bıraktı. Yeni sağlayıcı çağrı yolu veya gerçek model/native uygulama çağrısı yapılmadı.

## Bağımsız kanıt

- Dokuz ürün modülünde **169 test geçti**, süreç `94569`, çıkış 0.
  Günlük `general-desktop-auto-a588-tests.log`.
- İki bağımsız benimseme/hata kontrolü geçti; sohbet yeniden bağlama kontrolü
  başarısız. Süreç `11932`, çıkış 1. Günlük
  `general-desktop-auto-adversarial-a588-rebind.log`.
  Dosya sabit snapshot'ta `tests/test_general_auto_adoption.py`.
- Ruff dört değişen Python dosyasında geçti; mypy `--follow-imports=silent`
  ile üç kaynak modülünde geçti (`85217`, çıkış 0).

Kanıtlar görev çalışma alanında `work/reliability-v2/` altında. Ürün koşusunda
mevcut upstream Pydantic `ReadOnly` uyarısı görüldü. İncelemeye ait çalışan
süreç kalmadı. Tam ürün, native paket veya canlı kabul iddia edilmiyor.

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 0 | pass |

Verdict: **WARNING** — kabul anındaki sohbet sahipliği benimsemede korunmalı.
