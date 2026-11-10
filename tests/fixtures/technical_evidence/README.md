# Teknik kanıt regresyonu için kaynak parçaları

Bu iki JSON yalnız herkese açık kaynakların atıf yapılan kısa parçaları ile
kendi testimizde üretilen raporları/hakem hükümlerini içerir. Kullanıcı sırrı,
özel oturum kimliği/makbuzu veya ana makine yolu içermez. Tam tanı yakalaması
ürün yamasına eklenmez; çalışma kanıtı klasöründe kalır.

Kaynaklar:

- https://www.python.org/downloads/release/python-3140/
- https://docs.python.org/3.14/whatsnew/3.14.html
- https://www.python.org/downloads/release/python-3122/
- https://devguide.python.org/versions/

Copyright © 2001 Python Software Foundation; All Rights Reserved.
Python dokümantasyonu için PSF License Version 2 metni yanındaki
[PSF-LICENSE-2.txt](PSF-LICENSE-2.txt) dosyasındadır. Resmî lisans kaynağı:
https://docs.python.org/3.14/license.html

Değişiklik özeti: yalnız hükmün atıf yaptığı kaynak parçaları tutulmuştur.
Atıfsız makale metni çıkarılmış; `omitted_chars`/`newlines` bilgisi testte sentetik
boşluk üretir. Bu yerleşim kaynak parça numaraları ve atıf sınırlarını korur;
bir makale veya özel orijinal makbuz yeniden yayımlanmaz. Test sahipliği ve
özetleri yeniden bağlanır. Atıf yapılan özgün alıntıların baytları değişmez.
Yanlış-temiz örnekte 7.127, destekli örnekte 2.297 kaynak karakteri korunmuştur;
diğer kaynak metni içerilmez. Hüküm ve model raporu doğruluğun otoritesi değil,
regresyonda sınanan test verisidir.
