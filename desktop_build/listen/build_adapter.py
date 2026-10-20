"""Platform konuşma adaptörünü Tauri resource dizinine derle."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

MACOS_SOURCE = Path(__file__).resolve().parent / "main.swift"
WINDOWS_PROJECT = Path(__file__).resolve().parent / "windows" / "FusionListen.csproj"


class BuildError(RuntimeError):
    """Adaptör pakete girmeye hazır üretilemedi."""


@dataclass(frozen=True)
class AdapterContract:
    platform_name: str
    architectures: frozenset[str]
    resource_name: str
    compiler: str


CONTRACTS = {
    "macos": AdapterContract(
        platform_name="macos",
        architectures=frozenset({"arm64", "aarch64", "x86_64"}),
        resource_name="fusion-listen",
        compiler="swiftc",
    ),
    "windows": AdapterContract(
        platform_name="windows",
        architectures=frozenset({"amd64", "x86_64", "arm64", "aarch64"}),
        resource_name="fusion-listen.exe",
        compiler="dotnet",
    ),
}


def host_platform() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macos"
    if system == "Windows":
        return "windows"
    raise BuildError(f"Konuşma adaptörü bu platformda desteklenmiyor: {system}")


def contract_for(platform_name: str, architecture: str) -> AdapterContract:
    normalized_platform = platform_name.strip().lower()
    contract = CONTRACTS.get(normalized_platform)
    if contract is None:
        raise BuildError(f"Bilinmeyen konuşma adaptörü platformu: {platform_name}")
    normalized_arch = architecture.strip().lower()
    if normalized_arch not in contract.architectures:
        raise BuildError(
            f"{contract.platform_name} konuşma adaptörü bu mimariyi desteklemiyor: {architecture}"
        )
    return contract


def run_checked(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise BuildError(f"Konuşma adaptörü derlenemedi: {error}") from error


def _sign_macos_adapter(output: Path) -> None:
    """Yardımcıyı ad-hoc ama GERÇEK bir imzayla imzala.

    Derleyicinin otomatik koyduğu `linker-signed` imzayı AMFI reddediyor
    ("has no CMS blob", "Unrecoverable CT signature issue"). TCC izin kaydı
    imza kimliğine bağlı olduğu için imzasız sürece macOS hata VERMEZ; sessizce
    sıfır dolu ses verir. Ölçülen sonuç: motor başlıyor, `hazir` yazılıyor, ama
    tek bir ses örneği gelmiyor ve konuşma hiç tanınmıyor.

    Uygulama paketini `codesign --deep` ile imzalamak bunu KURTARMAZ:
    `Contents/Resources` altındaki Mach-O, iç içe kod değil kaynak olarak
    mühürlenir ve linker imzası yerinde kalır. Bu yüzden imza burada, üretildiği
    anda atılır — hangi paketleme yolu kullanılırsa kullanılsın taşınır.
    """
    if shutil.which("codesign") is None:
        raise BuildError("codesign bulunamadı; imzasız yardımcı mikrofona erişemez")
    run_checked(["codesign", "--force", "--sign", "-", "--timestamp=none", str(output)])


def build(
    *,
    platform_name: str,
    architecture: str,
    output: Path,
    compiler_override: str | None = None,
) -> Path:
    contract = contract_for(platform_name, architecture)
    if output.name != contract.resource_name:
        raise BuildError(
            f"Paket resource adı {contract.resource_name} olmalı; verilen: {output.name}"
        )
    compiler = compiler_override or shutil.which(contract.compiler)
    if not compiler:
        raise BuildError(f"{contract.compiler} bulunamadı; konuşma adaptörü derlenemedi")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    if contract.platform_name == "macos":
        run_checked([compiler, "-O", "-o", str(output), str(MACOS_SOURCE)])
        _sign_macos_adapter(output)
    else:
        with tempfile.TemporaryDirectory(prefix="fusion-listen-") as temporary:
            build_dir = Path(temporary)
            run_checked(
                [
                    compiler,
                    "build",
                    str(WINDOWS_PROJECT),
                    "--configuration",
                    "Release",
                    "--output",
                    str(build_dir),
                    "--nologo",
                ]
            )
            compiled = build_dir / "FusionListen.exe"
            if not compiled.is_file():
                raise BuildError(f"Windows derleyicisi beklenen çıktıyı üretmedi: {compiled}")
            shutil.copy2(compiled, output)

    if not output.is_file() or output.stat().st_size == 0:
        raise BuildError(f"Konuşma adaptörü çıktısı eksik veya boş: {output}")
    print(f"Konuşma adaptörü hazır: {output} ({output.stat().st_size} bayt)")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", dest="platform_name", default=None)
    parser.add_argument("--arch", default=platform.machine())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiler", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        build(
            platform_name=args.platform_name or host_platform(),
            architecture=args.arch,
            output=args.output.resolve(),
            compiler_override=args.compiler,
        )
    except BuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
