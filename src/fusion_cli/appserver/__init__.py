"""Masaüstü uygulaması için stdio protokolü.

Uygulama `fusion app` sürecini doğurur ve satır satır JSON konuşur. Bu paket
yalnız çeviri ve taşıma yapar: motor katmanı bu protokolü hiç tanımaz, mevcut
`EventSink` ve `Prompter` dikişlerine takılır.
"""

from __future__ import annotations
