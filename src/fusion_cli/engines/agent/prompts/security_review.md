Güvenlik incelemesi yap. Kapsam: {argument}

Önce kapsamı somutlaştır: `git diff` (staged + unstaged) ve `git diff --name-only` ile
değişen dosyaları bul; kapsam belirli bir yol ya da dalsa onu kullan. Değişen her dosyayı
değişikliğin bağlamıyla birlikte oku; yalnız diff satırına bakıp karar verme.

Şu başlıkların her birini ayrı ayrı denetle (OWASP Top 10 ve CWE'ye dayanır):
1. Sırlar: koda gömülü API anahtarı, parola, belirteç, özel anahtar; `.env`/yapılandırma
   dosyasının depoya girmesi; sırrın günlüğe ya da hata mesajına sızması.
2. Enjeksiyon: SQL/NoSQL sorgusunda dizgi birleştirme, kabuk komutuna kaçışsız girdi
   (`subprocess`/`exec`/`eval`), şablon enjeksiyonu, HTML'e kaçışsız yazma (XSS).
3. Yetkilendirme ve kimlik: eksik yetki denetimi, nesne düzeyinde erişim (IDOR), oturum ve
   belirteç ömrü, CSRF koruması, varsayılan açık izinler.
4. Yol geçişi ve dosya işlemleri: `..` ile kök dışına çıkış, kullanıcıdan gelen yolun
   doğrulanmaması, sembolik bağlantı takibi, güvensiz geçici dosya.
5. SSRF ve ağ: kullanıcıdan gelen adrese sunucu tarafı istek, iç ağ/loopback/metadata
   adreslerinin engellenmemesi, yönlendirme takibi, TLS doğrulamasının kapatılması.
6. Seri hale getirme ve girdi doğrulama: güvensiz `pickle`/`yaml.load`, şema doğrulaması
   olmadan dış veri kabulü, sınırsız boyut/sayı (DoS).
7. Kriptografi ve rastgelelik: zayıf algoritma (MD5/SHA1 parola için), sabit tuz/IV,
   `random` ile güvenlik amaçlı üretim, kendi yazılmış şifreleme.
8. Bağımlılık ve yapılandırma: bilinen açıklı sürüm, hata ayıklama kipinin üretimde
   açık kalması, ayrıntılı hata sayfası, eksik güvenlik başlıkları.

Bulguları ŞU biçimde, en ağırdan başlayarak listele; bulgu yoksa "Bulgu yok" de ve neyi
denetlediğini iki cümleyle özetle:

### [KRİTİK|YÜKSEK|ORTA|DÜŞÜK] Kısa başlık
- Yer: `dosya:satır`
- Sorun: tek paragraf; neden sömürülebilir olduğunu söyle.
- Düzeltme: somut kod ya da yapılandırma önerisi.

Kurallar: kod DEĞİŞTİRME; yalnız incele ve raporla. Kanıtı olmayan, spekülatif bulgu yazma.
Stil ve mimari sorunları buraya ekleme (onlar için `/review`). Sır bulduysan değerini
raporda YAZMA; yalnız yerini ve türünü belirt.
