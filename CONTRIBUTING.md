# Katkıda bulunma

Hata raporlarında işletim sistemi, Fusion sürümü, beklenen davranış ve tekrar adımlarını belirtin. API anahtarlarını, oturum çerezlerini, kişisel dosyaları ve özel sohbetleri paylaşmayın.

## Geliştirme

Python 3.11+ ve `make install` ile geliştirme ortamını hazırlayın. Mimari ve kod kuralları [RULES.md](RULES.md) içinde açıklanır.

- Çekirdek doğrulaması: `make check`.
- Masaüstü doğrulaması: Node.js 22 ile `cd app && npm ci && npm run check`.
- Tarayıcı testleri için: `python -m playwright install chromium`.

Değişiklikleri tek konuya odaklayın; davranış değiştiğinde ilgili testleri ve kullanıcı belgelerini güncelleyin. Üçüncü taraf lisanslarını koruyun. Güvenlik açıkları için [SECURITY.md](SECURITY.md) dosyasını izleyin.
