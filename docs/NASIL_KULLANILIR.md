# Fusion — Sıfırdan Kullanım Kılavuzu

Hiçbir şey bilmiyormuş gibi, adım adım. Her adımda TAM olarak ne yazacağın yazıyor.

---

## 0) Fusion nedir? (tek cümle)

Terminalde çalışan bir kodlama asistanı — kod yazar, düzeltir, test eder. Bir de
"santral" gibi çalışıp birçok yapay zekâ modelini tek yerden kullanmanı sağlar.

---

## 1) Kurulum (bir kez yapılır)

Terminali aç, proje klasörüne gir ve şunu yaz:

```
make setup
```

Bu; Python ortamını kurar, gerekli her şeyi indirir, `.env` şablonu bırakır. Bitince
"kuruldu" der.

**Anahtar (ücretsiz):** Modellerin cevap vermesi için en az bir anahtar gerekir.
`.env` dosyasını aç, şu satırı gerçek anahtarınla doldur:

```
OPENROUTER_API_KEY=buraya-anahtarını-yapıştır
```

> Anahtarı https://openrouter.ai adresinden ücretsiz alırsın. Anahtar yoksa Fusion yine
> açılır ama model çağıramaz.

İsteğe bağlı ek özellikler için:
```
pip install 'fusion-cli[gateway]'   # web paneli / santral için
pip install 'fusion-cli[mcp]'       # MCP köprüsü için
```

---

## 2) İlk açılış

Terminale sadece şunu yaz:

```
fusion
```

Karşına renkli bir **FUSION** yazısı ve bir kutu çıkar. Artık içindesin — alta yazıp
Enter'a basarak konuşursun.

> **Not:** Büyük ASCII "FUSION" logosu terminal penceren GENİŞSE (≈91 sütun) çıkar.
> Pencere darsa otomatik olarak küçük "✦ FUSION" görünür. Pencereyi büyüt, büyük logo geri gelir.

---

## 3) En basit kullanım

Ne istiyorsan düz Türkçe yaz ve Enter'a bas. Örnek:

```
src/app.py dosyasındaki login hatasını bul ve düzelt
```

Fusion dosyayı okur, düzeltir, test eder ve ne yaptığını 1-2 cümleyle söyler. Sen hiçbir
şey ayarlamak zorunda değilsin — varsayılanlar iş görür.

---

## 4) İki motor: `agent` ve `fusion`

- **agent** (varsayılan) → İŞ yapar: dosya değiştirir, komut çalıştırır. Kodlama için bunu kullan.
- **fusion** → Aynı soruyu birçok modele sorar, en iyi cevabı seçer. Zor sorular / fikir için.

Geçiş:
```
/agent      → agent motoruna geç
/fusion     → fusion motoruna geç
```

---

## 5) "Ne kadar güçlü model?" → `/mode`

Yaz:
```
/mode
```
Bir liste çıkar; ok tuşlarıyla seç, Enter'a bas:

- `auto` → Fusion işe bakıp kendi seçer (önerilir).
- `low` → hızlı/ucuz · `medium` → dengeli · `high` → zor işler · `max` → en iyi.

Doğrudan da yazabilirsin:
```
/mode auto
/mode high
```

---

## 6) "Model ne kadar düşünsün?" → `/effort`

Bu, mode'dan AYRI. Yaz:
```
/effort high
```
Seçenekler: `auto · low · medium · high · xhigh · max`. Zor problemde `high`, basit işte
`low` mantıklı. Model desteklemiyorsa Fusion sessizce en yakınına iner.

---

## 7) Güvenlik ve geri alma (önemli)

- **Önce planı gör:** riskli/büyük değişiklikten önce
  ```
  /plan
  ```
  yaz. Fusion sadece PLAN yapar, dosyaya dokunmaz. Beğenirsen `/auto` ile uygulamaya
  geçersin.
- **Geri al:** son turun dosya değişikliklerini geri almak için
  ```
  /undo
  ```
- **Doğrula:** değişiklikten sonra test/lint çalıştırmak için
  ```
  /verify
  ```
- Yıkıcı bir komutta (`rm -rf` gibi) Fusion zaten durup sana sorar.

---

## 8) Fusion öğrensin → `/good` ve `/bad`

Fusion motorunda bir cevaptan memnunsan `/good`, değilsen `/bad` yaz. Fusion bunu
hatırlar ve zamanla senin için daha iyi model seçer.

---

## 9) Başka sağlayıcı / anahtar ekleme

İki yol var:

**A) Basit:** `.env` dosyasına ekle. Örnek OpenAI:
```
OPENAI_API_KEY=sk-...
```
Sonra model olarak `openai/gpt-4o` gibi yazabilirsin.

**B) Şifreli (önerilen):** Önce bir ana şifre belirle (bir kez):
```
export FUSION_SECRET_KEY=uzun-gizli-bir-cümle
```
Sonra Fusion içinde:
```
/providers add
```
Sağlayıcıyı seç, anahtarı yapıştır (ekranda görünmez). Anahtar **şifreli** saklanır.

Hangi sağlayıcılar tanınıyor, hangisi kurulu görmek için:
```
/providers
```

---

## 10) Çok hesap (ücretsizleri üst üste koy)

Aynı sağlayıcının birkaç ücretsiz hesabı varsa, `.env`'e şöyle yaz:
```
OPENROUTER_API_KEY=hesap1-anahtarı
OPENROUTER_API_KEY_2=hesap2-anahtarı
OPENROUTER_API_KEY_3=hesap3-anahtarı
```
Fusion istekleri bunlara dağıtır; biri "bugünlük doldu" derse otomatik ötekine geçer.
Üç hesap tek büyük kotaymış gibi çalışır.

---

## 11) Yerel web paneli + santral (başka araçları bağlama)

Bu, Fusion'ı "her aracın bağlanabildiği bir santral" yapar — hepsi SENİN bilgisayarında.

**Adım 1 —** Ayrı bir terminal aç, şunu yaz:
```
fusion serve
```
Ekranda iki adres görürsün:
- `http://127.0.0.1:8787/v1`  ← başka araçların bağlanacağı adres
- `http://127.0.0.1:8787/dashboard`  ← panel

**Adım 2 — Paneli aç:** Tarayıcına şunu yaz:
```
http://127.0.0.1:8787/dashboard
```
Sağlayıcıları, sağlık durumunu, modelleri görürsün. Kimse başkası göremez, sadece sen.

**Adım 3 — Başka bir aracı bağla** (ör. Cursor, Cline, OpenAI-uyumlu her şey):
o aracın ayarlarında:
- **Adres (base URL):** `http://127.0.0.1:8787/v1`
- **API key:** herhangi bir şey (yerelde kontrol edilmez, ör. `fusion`)
- **Model:** `auto` (ya da `low`/`medium`/`high`/`max`, ya da `openai/gpt-4o` gibi bir kimlik)

Artık o araç Fusion üzerinden çalışır: yedekleme, sağlık, çok-hesap otomatik devrede.
Durdurmak için `fusion serve`'ün olduğu terminalde **Ctrl-C**.

---

## 12) MCP köprüsü (alet paylaşımı)

**Fusion'ın aletlerini başka AI uygulamasına açmak** (ör. Claude masaüstü Fusion'ın kod
aramasını kullansın):
```
fusion mcp
```
(Claude masaüstü/Cursor'ın MCP ayarına bu komutu eklersin.)

**Fusion'a dışarıdan alet takmak** (ör. GitHub aleti): `~/.config/fusion-cli/config.yaml`
dosyasına ekle:
```yaml
mcp_servers:
  - name: github
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
```
Bağlı sunucuların aletlerini görmek için:
```
fusion mcp-tools
```
Bundan sonra ajan turlarında bu dış aletler otomatik kullanılabilir (onayınla).

---

## Komut kopya kâğıdı

| Yaz | Ne yapar |
|-----|----------|
| `fusion` | Fusion'ı aç (REPL) |
| `/agent` · `/fusion` | Motor değiştir |
| `/mode` · `/mode high` | Model gücü profili |
| `/effort high` | Düşünme yoğunluğu |
| `/model` | Model değiştir |
| `/plan` | Önce planla, değiştirme |
| `/undo` | Son değişikliği geri al |
| `/verify` | Test/lint çalıştır |
| `/good` · `/bad` | Fusion'a geri bildirim |
| `/providers` · `/providers add` | Sağlayıcıları gör / anahtar ekle |
| `/health` | Model sağlığı / devre durumu |
| `/help` | Tüm komutlar |
| `fusion serve` | Yerel santral + panel |
| `fusion mcp` | Araçları MCP ile dışa aç |
| `fusion mcp-tools` | Dış MCP araçlarını listele |

---

## Sık karşılaşılanlar

- **"FUSION yazısı küçük çıktı"** → Terminal pencereni genişlet (≈91 sütun); büyük ASCII geri gelir. Ayar değil, ekran genişliği.
- **"Hiçbir model yanıt veremedi"** → Anahtar eksik/yanlış. `.env`'i kontrol et, `/providers` ile kurulu mu bak, ya da `fusion doctor` çalıştır.
- **Bir model sürekli hata veriyor** → Fusion onu otomatik bir süre atlar; `/health` ile görebilirsin.
- **Değişiklikten memnun değilim** → `/undo`.
- **Yavaş** → `/mode low` ya da `/effort low`.

Takıldığın her yerde `/help` yaz — bütün komutlar orada.
