# Windows konuşma tanıma adaptörü

`FusionListen.cs`, Windows'un yerel `System.Speech.Recognition` API'sini kullanır.
Dil varsayılan ve üretim çağrısında `tr-TR`'dir. Çıktı macOS yardımcısıyla aynı
JSONL sözleşmesidir:

```jsonl
{"tur":"hazir","metin":"tr-TR"}
{"tur":"kismi","metin":"bu projede"}
{"tur":"son","metin":"bu projede neler var"}
{"tur":"hata","metin":"açık Türkçe hata"}
```

Derleme Windows üzerinde .NET Framework 4.8 referans paketini gerektirir:

```powershell
python desktop_build/listen/build_adapter.py `
  --platform windows `
  --output app/src-tauri/resources/fusion-listen.exe
```

Script derleme hatasını veya eksik `FusionListen.exe` çıktısını non-zero ile
sonlandırır; önceki bir çıktı başarı olarak yeniden kullanılamaz.
