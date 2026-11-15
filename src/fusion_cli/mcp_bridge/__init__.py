"""MCP köprüsü: dış MCP sunucularına bağlantı, havuz ve araç kaydı."""

from __future__ import annotations

import logging

# Ölçüldü (30 Ekim): uygulama günlük işleyicisi kurmadığı için Python'un "son çare"
# işleyicisi bu paketin uyarılarını ham hâliyle (sunucu adı/neden olmadan) terminale
# basıyordu. Kullanıcıya görünen tek satır `cli/mcp_notice.py`'den gelir; ayrıntı
# günlük yapılandırıldığında alanlarıyla (`extra`) yine yazılır.
logging.getLogger(__name__).addHandler(logging.NullHandler())
