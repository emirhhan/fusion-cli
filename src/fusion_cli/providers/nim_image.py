"""NVIDIA NIM üzerinden ücretsiz görsel üretimi (FLUX ailesi).

Canlı ölçüm (29 Eylül 2026, bu kurulumun NIM anahtarı, 1024×1024 ürün istemi):

    black-forest-labs/flux.1-dev          → 200, 8,1 sn, geçerli JPEG
    black-forest-labs/flux.2-klein-4b     → 200, 40,9 sn, geçerli JPEG
    black-forest-labs/flux.1-schnell      → 120 sn ve 240 sn içinde yanıt yok (listelenmez)
    black-forest-labs/flux.1-kontext-dev  → 422: görsel `example_id` ister, base64
                                            kabul etmez (referans için kullanılamaz)
    stabilityai/stable-diffusion-3-medium,
    stabilityai/stable-diffusion-xl, stabilityai/sdxl-turbo,
    briaai/bria-2.3                        → 404 "Not found for account"

Yalnız çalıştığı ölçülen modeller listelenir. NIM FLUX uçları referans görsel
almadığı için bu modeller yalnız "Üret" düğümünde kullanılabilir.
"""

from __future__ import annotations

import asyncio
import base64
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from .web_image import GeneratedImage

#: NIM görsel üretim uç noktası (model kimliği yola eklenir).
NIM_GENAI_URL = "https://ai.api.nvidia.com/v1/genai/{model}"

#: İstek zaman aşımı: ölçülen en yavaş çalışan model 40,9 sn; yaklaşık üç kat pay.
NIM_IMAGE_TIMEOUT_S = 120.0

#: Üretim boyutu: iki modelin de ölçüldüğü değer.
_EDGE = 1024

#: En-boy oranı → (genişlik, yükseklik). FLUX.1-dev NIM ucu kenar başına 672–1568
#: aralığını ve 32'nin katlarını kabul eder (Comfy-Org/NIMnodes'un NIM FLUX düğümü,
#: 30 Eylül 2026'da okundu). Değerler FLUX'un ~1 megapiksellik standart kovalarıdır;
#: kare dışındaki oranlar da aynı piksel bütçesinde kalır.
ASPECT_SIZES: dict[str, tuple[int, int]] = {
    "1:1": (_EDGE, _EDGE),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
}

#: Tohum üst sınırı: FLUX uçlarının kabul ettiği 32 bit işaretsiz aralık.
_SEED_LIMIT = 2**32


@dataclass(frozen=True, slots=True)
class NimImageModel:
    model: str
    label: str
    #: Kare dışı boyutları kabul ettiği doğrulandı mı? Doğrulanmayan modele
    #: yalnız ölçülmüş 1024×1024 gönderilir; oran istemde metin olarak kalır.
    aspect_sizes: bool = False


#: Canlı ölçümde çalışan modeller, hızlıdan yavaşa.
NIM_IMAGE_MODELS: tuple[NimImageModel, ...] = (
    NimImageModel("black-forest-labs/flux.1-dev", "FLUX.1-dev (NVIDIA NIM)", aspect_sizes=True),
    NimImageModel("black-forest-labs/flux.2-klein-4b", "FLUX.2 klein 4B (NVIDIA NIM)"),
)

NIM_PREFIX = "nvidia_nim/"


class NimImageError(RuntimeError):
    """NIM görsel üretemedi; mesaj kullanıcıya gösterilir."""


def nim_model_from_choice(choice: str) -> NimImageModel | None:
    """`nvidia_nim/<model>` seçimini ölçülmüş modele çevir; tanınmazsa None."""
    if not choice.startswith(NIM_PREFIX):
        return None
    model = choice.removeprefix(NIM_PREFIX)
    return next((item for item in NIM_IMAGE_MODELS if item.model == model), None)


def _suffix(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    return None


async def generate_nim_image(
    model: NimImageModel,
    prompt: str,
    out_dir: Path,
    *,
    api_key: str,
    client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
    size: tuple[int, int] = (_EDGE, _EDGE),
) -> list[GeneratedImage]:
    """Tek görsel üret ve `out_dir` altına yaz; başarısızlıkta `NimImageError`."""
    width, height = size if model.aspect_sizes else (_EDGE, _EDGE)
    body = {
        "prompt": prompt,
        "width": width,
        "height": height,
        # Sabit tohum aynı istemde hep aynı görseli verir; akışı yeniden
        # çalıştıran kullanıcı yeni bir sonuç bekler.
        "seed": secrets.randbelow(_SEED_LIMIT),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=NIM_IMAGE_TIMEOUT_S)
    try:
        response = await http.post(
            NIM_GENAI_URL.format(model=model.model), headers=headers, json=body
        )
    except httpx.TimeoutException as error:
        raise NimImageError(
            f"{model.label} {NIM_IMAGE_TIMEOUT_S:.0f} sn içinde yanıt vermedi."
        ) from error
    except httpx.HTTPError as error:
        raise NimImageError(f"{model.label} isteği başarısız: {type(error).__name__}") from error
    finally:
        if own_client:
            await http.aclose()
    if response.status_code != 200:
        raise NimImageError(f"{model.label} {response.status_code} döndü: {response.text[:160]}")
    artifacts = response.json().get("artifacts") or []
    first = artifacts[0] if artifacts and isinstance(artifacts[0], dict) else {}
    reason = str(first.get("finishReason", ""))
    if reason and reason != "SUCCESS":
        raise NimImageError(f"{model.label} görseli vermedi ({reason}); istemi değiştir.")
    data = base64.b64decode(str(first.get("base64") or ""))
    suffix = _suffix(data)
    if suffix is None:
        raise NimImageError(f"{model.label} geçerli bir görsel döndürmedi.")
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"fusion-{stamp}-{secrets.token_hex(3)}{suffix}"
    await asyncio.to_thread(_write, path, data)
    return [GeneratedImage(path, _EDGE, _EDGE)]


def _write(path: Path, data: bytes) -> None:
    """Dosya yazımı olay döngüsünü bekletmesin diye iş parçacığında yapılır."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
