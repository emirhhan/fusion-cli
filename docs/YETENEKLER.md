# Fusion — Yetenekler

Fusion iki şeyi tek üründe birleştirir:

1. **Kodlama ustası (agent):** terminalde kod okuyan, düzenleyen, test eden, git kullanan,
   plan yapan, kendi kendini denetleyen, hatalardan ders çıkaran bir asistan.
2. **Yerel model geçidi (gateway):** birçok sağlayıcıya bağlanan, biri tükenince ötekine
   geçen, tek bir yerel adres açan bir "santral" — böylece başka araçlar da Fusion'a bağlanır.

## Sende olan yetenekler

| Yetenek | Ne işe yarar |
|---|---|
| Yerel geçit (`fusion serve`) | Bu bilgisayardaki her araç Fusion'a bağlanır (yalnız 127.0.0.1) |
| Yerel web paneli (`/dashboard`) | Tarayıcıda sağlayıcı/sağlık/model gösterir, senin makinenden |
| 48 gerçek sağlayıcı | OpenAI, Gemini, Anthropic, Groq, Mistral, DeepSeek… hepsi LiteLLM ile |
| Otomatik yedekleme + sağlık | Bir model bozulursa/yavaşsa otomatik atlanır, güvenilirlik öğrenilir |
| Çok-hesap havuzu | Aynı sağlayıcıya birkaç ücretsiz hesap; biri dolunca öteki devreye girer |
| Yönlendirme stratejileri | Sıra / ücretsiz-önce / en-sağlıklı / rastgele… |
| Profiller (`/mode`) + effort (`/effort`) | "Ne kadar güçlü model" ve "ne kadar düşünsün" ayrı ayrı |
| Şifreli anahtar deposu | Anahtarlar şifreli saklanır, log'a/git'e girmez |
| MCP köprüsü | Fusion araçlarını dışa aç (sunucu) + dış MCP araçlarını kullan (istemci) |
| MCP kurulumu (`/mcp`, `fusion mcp-add`, panel) | Sohbette `/mcp add <ad> <komut>`, terminalden `fusion mcp-add`, ya da Control Panel'in "MCP sunucusu bağla" kartından — üçü de aynı config.yaml'a yazar, elle düzenleme gerekmez |
| Öz-öğrenen bellek | Her görevden ders çıkarır, benzer işlerde hatırlar |
| Uzak MCP OAuth | HTTP MCP sunucularında tarayıcı girişi, PKCE ve macOS Keychain token deposu |
| Kanıta bağlı yeniden planlama | Aynı başarısız hedefte dönmek yerine doğrulanmış işi koruyup dalı bir kez yeniler |
| Gerçek asset kapısı | PNG/JPEG başlığı, boyut, kaynak URL'si ve lisans manifestini doğrular |
| Production değerlendirmesi | Godot asset, MCP, replan, büyük dosya ve sohbet izolasyonunu üç tekrarla ölçer |

Yayın ölçümü `python -m evals run evals/suite/production.yaml --profile production --repeat 3`
komutuyla çalışır. Rapor, bütün tekil koşuların başarı oranını ve yalnız üç tekrarın
üçünü de geçen görevlerin katı güvenilirlik oranını ayrı gösterir. Canlı Meta OAuth
girişi kullanıcı hesabı ve tarayıcı onayı gerektirdiği için son smoke kontroldür;
token hiçbir değerlendirme fikstüründe tutulmaz.

## Hâlâ eksik olanlar (dürüst)

- Ücretsiz-katman bütçe paneli (hangi hesapta ne kadar kota kaldı).
- Agresif token sıkıştırma (kodu bozmadan yapmak gerekir, dikkatli gidilmeli).
- Çok dilli arayüz (şu an Türkçe/İngilizce).

## Bilerek yapılmayanlar

- Başka uygulamaların trafiğini gizlice yakalama (MITM) — senin de istemediğin şey.
- ChatGPT/Gemini gibi tüketici web arayüzlerini kazıyan canlı bağlantı — bu sağlayıcıların
  şartlarına aykırı. Framework hazır; böyle bir bağlantıyı kullanıcı kendi yetkisiyle sağlar.

> Fikir, bir yerel model-geçidi ile kodlama asistanını birleştirmekti. Fusion bunu kendi
> bağımsız uygulaması olarak, tamamen senin bilgisayarında çalışacak biçimde yapar.

Adım adım kullanım için: [NASIL_KULLANILIR.md](NASIL_KULLANILIR.md).
