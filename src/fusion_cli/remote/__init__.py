"""Kimlikli uzaktan görev servisi: cihaz eşleştirme, imzalı RPC, Telegram ve mobil PWA.

Servis ikinci bir ajan motoru DEĞİLDİR; mevcut `AppSession` oturumunun önüne
konan kimlik, yetki ve olay katmanıdır. Varsayılan olarak yalnız yerel döngü
adresinde dinler.
"""
