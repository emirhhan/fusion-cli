"""Sandbox proxy'sinin TLS sonlandırma CA'sı (Claude `network.tlsTerminate`, #350, #368).

`tlsTerminate: {}` oturum başına geçici bir CA üretir; `{caCertPath, caKeyPath}` kullanıcının
CA'sını kullanır. Her ana makine için CA imzalı yaprak sertifika bellekte önbelleklenir.
Sandbox içindeki istemciler CA'ya ortam değişkenleriyle güvenir (`trust_env`): sistem kökleri
+ CA demeti `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`, `GIT_SSL_CAINFO`…;
`NODE_EXTRA_CA_CERTS` yalnız CA. Anahtarların durduğu dizin sandbox'a OKUNAMAZ
(`private_dir` → `locked_read`).
"""

from __future__ import annotations

import datetime
import ipaddress
import ssl
import tempfile
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.types import CertificateIssuerPrivateKeyTypes
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from ..core.errors import ConfigError

__all__ = ["SessionCa", "session_ca"]

#: Yaprak sertifikanın ömrü; oturum süresince yeniden üretilmez.
_LEAF_DAYS = 2
_CA_DAYS = 7
_BUNDLE_ENV = (
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "GIT_SSL_CAINFO",
    "PIP_CERT",
    "AWS_CA_BUNDLE",
)
_LOCK = threading.Lock()
_CACHE: dict[tuple[str, str], SessionCa] = {}


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _system_roots() -> str:
    """Sistem kök sertifikaları (OpenSSL varsayılanı, yoksa certifi)."""
    paths = ssl.get_default_verify_paths()
    for candidate in (paths.cafile, paths.openssl_cafile):
        if candidate and Path(candidate).is_file():
            return Path(candidate).read_text(encoding="utf-8", errors="replace")
    try:
        import certifi

        return Path(certifi.where()).read_text(encoding="utf-8")
    except (ImportError, OSError):
        return ""


class SessionCa:
    """CA anahtarı + sertifikası; ana makine başına sunucu bağlamı üretir."""

    def __init__(self, cert_path: str = "", key_path: str = "") -> None:
        self.private_dir = Path(tempfile.mkdtemp(prefix="fusion-sbx-ca-key-"))
        self.public_dir = Path(tempfile.mkdtemp(prefix="fusion-sbx-ca-"))
        self.private_dir.chmod(0o700)
        if cert_path:
            self._key, self._cert = self._load(Path(cert_path), Path(key_path))
        else:
            self._key, self._cert = self._generate_ca()
        pem = self._cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
        self.cert_path = self.public_dir / "ca.pem"
        self.cert_path.write_text(pem, encoding="ascii")
        self.bundle_path = self.public_dir / "bundle.pem"
        self.bundle_path.write_text(_system_roots().rstrip() + "\n" + pem, encoding="utf-8")
        self._contexts: dict[str, ssl.SSLContext] = {}
        self._lock = threading.Lock()

    def _load(
        self, cert: Path, key: Path
    ) -> tuple[CertificateIssuerPrivateKeyTypes, x509.Certificate]:
        try:
            certificate = x509.load_pem_x509_certificate(cert.read_bytes())
            private = serialization.load_pem_private_key(key.read_bytes(), password=None)
        except (OSError, ValueError, TypeError) as error:
            raise ConfigError(f"sandbox.network.tlsTerminate CA okunamadı: {error}") from error
        if not isinstance(private, ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey):
            raise ConfigError("sandbox.network.tlsTerminate: CA anahtarı imzalamaya uygun değil.")
        return private, certificate

    def _generate_ca(self) -> tuple[CertificateIssuerPrivateKeyTypes, x509.Certificate]:
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Fusion Sandbox CA")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - datetime.timedelta(hours=1))
            .not_valid_after(_now() + datetime.timedelta(days=_CA_DAYS))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(_key_usage(ca=True), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .sign(key, hashes.SHA256())
        )
        return key, cert

    def _leaf(self, host: str) -> tuple[bytes, bytes]:
        key = ec.generate_private_key(ec.SECP256R1())
        alt: x509.GeneralName
        try:
            alt = x509.IPAddress(ipaddress.ip_address(host))
        except ValueError:
            alt = x509.DNSName(host)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)]))
            .issuer_name(self._cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(_now() - datetime.timedelta(hours=1))
            .not_valid_after(_now() + datetime.timedelta(days=_LEAF_DAYS))
            .add_extension(x509.SubjectAlternativeName([alt]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(_key_usage(ca=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self._key.public_key()), False
            )
            .sign(self._key, hashes.SHA256())
        )
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        return cert.public_bytes(serialization.Encoding.PEM), key_pem

    def server_context(self, host: str) -> ssl.SSLContext:
        with self._lock:
            cached = self._contexts.get(host)
            if cached is not None:
                return cached
            cert, key = self._leaf(host)
            stem = self.private_dir / f"leaf-{len(self._contexts)}"
            stem.with_suffix(".pem").write_bytes(cert)
            key_file = stem.with_suffix(".key")
            key_file.write_bytes(key)
            key_file.chmod(0o600)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(stem.with_suffix(".pem"), key_file)
            context.set_alpn_protocols(["http/1.1"])
            self._contexts[host] = context
            return context

    def upstream_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()
        context.set_alpn_protocols(["http/1.1"])
        return context

    def trust_env(self) -> dict[str, str]:
        """Sandbox içindeki istemcilerin CA'ya güvenmesi için ortam."""
        env = dict.fromkeys(_BUNDLE_ENV, str(self.bundle_path))
        env["NODE_EXTRA_CA_CERTS"] = str(self.cert_path)
        return env


def _key_usage(*, ca: bool) -> x509.KeyUsage:
    return x509.KeyUsage(
        digital_signature=True,
        content_commitment=False,
        key_encipherment=not ca,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=ca,
        crl_sign=ca,
        encipher_only=False,
        decipher_only=False,
    )


def session_ca(cert_path: str = "", key_path: str = "") -> SessionCa:
    """Süreç (oturum) boyunca tek CA: aynı ayar için aynı nesne."""
    key = (cert_path, key_path)
    with _LOCK:
        existing = _CACHE.get(key)
        if existing is None:
            existing = SessionCa(cert_path, key_path)
            _CACHE[key] = existing
        return existing
