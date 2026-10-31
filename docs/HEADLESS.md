# Headless (betik) kullanım — `fusion agent`

`fusion agent` bir terminal olmadan, betikten ya da başka bir programdan çalıştırılmak
için tasarlanmıştır. Claude Code'un `claude -p` ve Codex'in `codex exec` davranışı örnek
alınmıştır; bayrak adları tanınır biçimde korunur, açıklamalar Türkçedir.

## Görev kaynağı

```bash
fusion agent "testleri çalıştır ve kırmızıları düzelt"     # argüman
echo "dosyaları listele" | fusion agent -                  # stdin (`-`)
echo "dosyaları listele" | fusion agent                    # boru hattında boş görev = stdin
```

Terminalde boş görev hata verir (`Görev metni boş olamaz.`); stdin yalnız boru hattında
okunur.

## Çıktı biçimi — `--output-format`

| Değer | Davranış |
|-------|----------|
| `text` (varsayılan) | İnsan için renkli çıktı; `--quiet` ilerleme satırlarını gizler. |
| `json` | Tek satır: nihai sonuç nesnesi (aşağıda). İlerleme satırı basılmaz. |
| `stream-json` | Her olay bir satır (JSONL). İlk satır `SystemInit`. `--json` bunun kısaltmasıdır. |

### `json` sonuç nesnesi

```json
{"type": "result", "ok": true, "durum": "completed", "sonuc": "…",
 "yapisal": null, "yapisal_hatalar": [], "durma_nedeni": null, "model_cagri": 3,
 "kullanim": {"girdi_token": 1200, "cikti_token": 300, "maliyet_usd": 0.0012,
              "maliyet_tam": true, "cagri": 3}}
```

`durum`: `completed` | `budget` (tur bütçe/tavan sebebiyle kesildi) | `failed`.
`maliyet_tam` false ise toplam alt sınırdır (ölçülmemiş ya da iptal edilmiş çağrı var).

### `stream-json` olayları

Her satır `{"event": "<OlayAdı>", ...alanlar}` biçimindedir; alanlar `core/events.py`
içindeki olay dataclass'larının alanlarıdır ve sırlar maskelenir. Betiklerin en çok
kullandığı olaylar:

| Olay | Anlamı (Claude Code karşılığı) |
|------|--------------------------------|
| `SystemInit` | İlk satır: `surum`, `model`, `kip`, `cwd`, `izin_kanali`, `mcp_sunuculari` (`system/init`). |
| `ModelCallStarted` / `ModelCallFinished` | Model çağrısı (token/maliyet `result.usage` içinde). |
| `ToolStarted` / `ToolExecuted` | Araç çağrısı ve sonucu (`tool_use` / `tool_result`). |
| `ApprovalRequested` / `ApprovalResolved` | Onay kanalı açıkken izin isteği ve karar (`permission_denied` karşılığı: `karar: "deny"`). |
| `QuestionAsked` | Model kullanıcıya soru sordu (onay kanalı açıkken). |
| `TurnBudgetExhausted` | Tur bütçe sebebiyle kesildi; `reason` alanı (`cost_limit`, `model_calls`, …). |
| `TurnAnswered` / `TurnFinished` | Nihai cevap ve tur sonu (`result`). |

## Sınırlar

| Bayrak | Etkisi |
|--------|--------|
| `--max-turns N` | Bu tur için model çağrısı üst sınırı (`runtime.agent_max_steps`'i geçersiz kılar). |
| `--max-budget-usd X` | Turun **bilinen** maliyeti X'e ulaşınca tur `cost_limit` ile kapanır (`runtime.agent_max_cost_usd`). Ücretsiz ya da maliyeti bilinmeyen model tavanı doldurmaz. |

İkisi de `config.yaml`'dan kalıcı olarak verilebilir:

```yaml
runtime:
  agent_max_steps: 40
  agent_max_cost_usd: 2.0     # null = tavan yok
```

## Araç listeleri

```bash
fusion agent "…" --allowed-tools read_file,grep,run_shell   # modele YALNIZ bunlar sunulur
fusion agent "…" --disallowed-tools run_shell                # çağrılırsa sorulmadan engellenir
```

Yasak liste izin kuralı gramerindedir: karar `BLOCKED`tır, kullanıcıya sorulmaz, tur
durmaz (model "bu yol kapalı" bilgisini alır). Kabuk takma adları (`run_shell`/`bash`)
tek aile sayılır.

## Sistem istemi ve ajan tanımı

```bash
fusion agent "…" --append-system-prompt "Yalnız Türkçe yaz."
fusion agent "…" --agent gozden-gecirici     # .claude/agents/gozden-gecirici.md
```

`--agent` tanımının gövdesi sistem istemine eklenir; `tools:` alanı varsa izin listesi
onunla kesişir (`--allowed-tools` da verildiyse ikisinin kesişimi).

## `--bare`

Bellek, MCP sunucuları, barındırılan bağlayıcılar ve proje talimatı (AGENTS.md/CLAUDE.md,
dış araç bellekleri) yüklenmez; tur yalnız yerleşik araçlarla çalışır
(`runtime.project_instructions: false` + boş `mcp_servers`). CI'da tekrarlanabilir
koşular için.

## Yapısal çıktı — `--json-schema`

```bash
fusion agent "bu depodaki açık TODO'ları say" \
  --json-schema sema.json --output-format json
```

Şema modele sistem eki olarak gider ("son cevabın yalnız bu şemaya uyan tek JSON
nesnesi olsun"); nihai cevaptan JSON ayıklanır (kod çiti sökülür) ve denetlenir. Uyumsuzsa
`yapisal_hatalar` dolar ve çıkış kodu 1 olur. Desteklenen JSON Schema alt kümesi:
`type` (tek ad ya da liste), `required`, `properties`, `items`, `enum`,
`additionalProperties: false`. Diğer anahtarlar denetlenmez.

## Dış onay kanalı — `--permission-channel stdin`

Etkileşimsiz oturumda onay istemi normalde `UNAVAILABLE` sayılır (sorulamadı, tur sürer).
Kanal açıkken istekler stdout'a, kararlar stdin'den JSON-Lines olarak akar:

```text
stdout → {"event": "ApprovalRequested", "istek_id": "1", "arac": "run_shell", "args": {...}, "tehlike": null, "etki": "..."}
stdin  ← {"istek_id": "1", "karar": "onayla"}          # onayla|oturum|reddet (allow|session|deny)
stdout → {"event": "ApprovalResolved", "istek_id": "1", "karar": "once"}
stdout → {"event": "QuestionAsked", "istek_id": "2", "soru": "...", "secenekler": [...], "onerilen": null}
stdin  ← {"istek_id": "2", "cevap": "..."}
```

Eşleşmeyen kimlik, bozuk satır ya da EOF insan reddi DEĞİLDİR: `UNAVAILABLE` döner.
Görev stdin'den okunurken kanal da stdin olamaz; görevi argüman olarak ver.

## Çıkış kodları

- `0` — tur tamamlandı, nihai metin dolu, şema (varsa) uyumlu.
- `1` — boş cevap, hata, bütçe/tavan kesintisi ya da şemaya uymayan cevap.
- `2` — bayrak hatası (Typer).
