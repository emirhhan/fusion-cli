"""Taslakların diskteki yeri — üret, listele, oku, sil.

Taslaklar `evals/` kümesinden AYRI bir dizinde durur ve kullanıcının kendi makinesinden
çıkmaz (gerçek konuşmadan türerler). Her taslak tek bir YAML dosyasıdır; görev kısmı
`evals/loader.py` biçimindedir ki kabulde olduğu gibi kümeye geçsin.

`sil` yalnız dosyayı kaldırmaz, kimliği `reddedilen.json`a da yazar: aynı hata günlükte
durduğu sürece sonraki taramalar silinmiş taslağı yeniden önermesin.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable
from pathlib import Path

import yaml

from evals.loader import criterion_to_mapping, parse_criterion
from evals.taslak import TASLAK_KIMLIK, Taslak, TaslakKaynagi
from fusion_cli.core.atomic_file import atomic_replace_text
from fusion_cli.core.errors import EvalError

REDDEDILEN_DOSYA = "reddedilen.json"


class TaslakDeposu:
    """Bir dizindeki taslak dosyaları."""

    def __init__(self, dizin: Path) -> None:
        self._dizin = dizin

    @property
    def dizin(self) -> Path:
        return self._dizin

    def kaydet(
        self, taslaklar: Iterable[Taslak], *, atla: Collection[str] = ()
    ) -> tuple[Taslak, ...]:
        """Yeni taslakları yaz; zaten var olan, reddedilen ya da `atla`daki kimlikler geçilir.

        `atla`: kümeye zaten kabul edilmiş görev kimlikleri. Döndürülen demet YENİ yazılanlardır.
        """

        engelli = {*atla, *self._reddedilen(), *(taslak.id for taslak in self.listele())}
        yeni: list[Taslak] = []
        for taslak in taslaklar:
            if taslak.id in engelli:
                continue
            engelli.add(taslak.id)
            atomic_replace_text(self._yol(taslak.id), _yamla(taslak))
            yeni.append(taslak)
        return tuple(yeni)

    def listele(self) -> tuple[Taslak, ...]:
        """Bekleyen taslaklar, kimliğe göre sıralı; okunamayan dosya atlanır."""

        if not self._dizin.is_dir():
            return ()
        taslaklar: list[Taslak] = []
        for yol in sorted(self._dizin.glob("tk-*.yaml")):
            try:
                taslaklar.append(_oku(yol))
            except EvalError:
                continue
        return tuple(taslaklar)

    def oku(self, taslak_id: str) -> Taslak:
        yol = self._yol(taslak_id)
        if not yol.is_file():
            raise EvalError(
                f"böyle bir taslak yok: {taslak_id} (liste için: fusion eval taslaklar)"
            )
        return _oku(yol)

    def kaldir(self, taslak_id: str, *, reddet: bool) -> None:
        """Taslak dosyasını kaldır; `reddet` ise kimlik bir daha önerilmez."""

        yol = self._yol(taslak_id)
        if not yol.is_file():
            raise EvalError(
                f"böyle bir taslak yok: {taslak_id} (liste için: fusion eval taslaklar)"
            )
        if reddet:
            kimlikler = sorted({*self._reddedilen(), taslak_id})
            atomic_replace_text(self._dizin / REDDEDILEN_DOSYA, json.dumps(kimlikler))
        yol.unlink()

    # ----------------------------------------------------------------------- #

    def _yol(self, taslak_id: str) -> Path:
        # Kimlik dosya adına dönüşür; `../` ile dizin dışına çıkılamaz.
        if not TASLAK_KIMLIK.fullmatch(taslak_id):
            raise EvalError(f"geçersiz taslak kimliği: {taslak_id!r} (örnek: tk-0123456789)")
        return self._dizin / f"{taslak_id}.yaml"

    def _var_olan(self, taslak_id: str) -> Path:
        yol = self._yol(taslak_id)
        if not yol.is_file():
            raise EvalError(f"böyle bir taslak yok: {taslak_id} (liste: fusion eval taslaklar)")
        return yol

    def _reddedilen(self) -> set[str]:
        try:
            ham = json.loads((self._dizin / REDDEDILEN_DOSYA).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        return (
            {kimlik for kimlik in ham if isinstance(kimlik, str)}
            if isinstance(ham, list)
            else set()
        )


def _yamla(taslak: Taslak) -> str:
    gorev: dict[str, object] = {"id": taslak.id, "request": taslak.request}
    if taslak.olcut is not None:
        gorev["criterion"] = criterion_to_mapping(taslak.olcut)
    belge = {
        "taslak": {
            "kaynak": taslak.kaynak.value,
            "olusturma": taslak.olusturma,
            "olcut_notu": taslak.olcut_notu,
            "kanit": list(taslak.kanit),
        },
        "tasks": [gorev],
    }
    return yaml.safe_dump(belge, allow_unicode=True, sort_keys=False, width=100)


def _oku(yol: Path) -> Taslak:
    try:
        belge = yaml.safe_load(yol.read_text(encoding="utf-8"))
        meta = belge["taslak"]
        gorev = belge["tasks"][0]
        olcut = parse_criterion(gorev["criterion"]) if "criterion" in gorev else None
        return Taslak(
            id=str(gorev["id"]),
            kaynak=TaslakKaynagi(meta["kaynak"]),
            request=str(gorev["request"]),
            olcut=olcut,
            olcut_notu=str(meta.get("olcut_notu", "")),
            kanit=tuple(str(satir) for satir in meta.get("kanit", ())),
            olusturma=str(meta.get("olusturma", "")),
        )
    except (OSError, yaml.YAMLError, KeyError, IndexError, TypeError, ValueError) as hata:
        raise EvalError(f"taslak okunamadı: {yol.name} — {hata}") from hata
