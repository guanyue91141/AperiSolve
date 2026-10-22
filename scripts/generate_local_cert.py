#!/usr/bin/env python3
"""Create a private local CA and a TLS server certificate for this AperiSolve host."""

from __future__ import annotations

import ipaddress
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TLS_DIR = Path(os.environ.get("LOCAL_TLS_DIR", PROJECT_ROOT / "data" / "tls")).expanduser().resolve()
CA_KEY = TLS_DIR / "rootCA.key"
CA_CERT = TLS_DIR / "rootCA.crt"
SERVER_KEY = TLS_DIR / "server.key"
SERVER_CERT = TLS_DIR / "server.crt"


def _hostnames_and_ips() -> tuple[list[str], list[str]]:
    """Collect local names, the configured origin, and active LAN IPv4 addresses."""
    dns_names = {"localhost", socket.gethostname()}
    ip_addresses = {"127.0.0.1", "::1"}
    configured = os.environ.get("SITE_BASE_URL", "")
    host = urlsplit(configured).hostname if configured else None
    if host:
        try:
            ip_addresses.add(str(ipaddress.ip_address(host)))
        except ValueError:
            dns_names.add(host)

    result = subprocess.run(
        ["ip", "-4", "-o", "addr", "show", "scope", "global"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) >= 4:
                ip_addresses.add(fields[3].split("/", 1)[0])
    return sorted(dns_names), sorted(ip_addresses)


def _run(*args: str) -> None:
    subprocess.run(args, check=True, cwd=TLS_DIR)


def generate() -> None:
    """Keep the local CA stable and issue a fresh leaf certificate for current addresses."""
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    if CA_KEY.exists() != CA_CERT.exists():
        raise RuntimeError(f"Both local CA files must exist together in {TLS_DIR}")
    if not CA_CERT.exists():
        _run(
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:3072",
            "-sha256",
            "-days",
            "3650",
            "-nodes",
            "-keyout",
            str(CA_KEY),
            "-out",
            str(CA_CERT),
            "-subj",
            "/CN=AperiSolve Local Root CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-addext",
            "subjectKeyIdentifier=hash",
        )
    CA_KEY.chmod(0o600)

    dns_names, ip_addresses = _hostnames_and_ips()
    extensions = [
        "[server]",
        "basicConstraints=critical,CA:FALSE",
        "keyUsage=critical,digitalSignature,keyEncipherment",
        "extendedKeyUsage=serverAuth",
        "subjectKeyIdentifier=hash",
        "authorityKeyIdentifier=keyid,issuer",
        "subjectAltName=@names",
        "",
        "[names]",
    ]
    extensions.extend(f"DNS.{index}={name}" for index, name in enumerate(dns_names, 1))
    extensions.extend(f"IP.{index}={address}" for index, address in enumerate(ip_addresses, 1))
    ext_file = TLS_DIR / "server.ext"
    csr_file = TLS_DIR / "server.csr"
    ext_file.write_text("\n".join(extensions) + "\n", encoding="utf-8")
    try:
        _run(
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-keyout",
            str(SERVER_KEY),
            "-out",
            str(csr_file),
            "-subj",
            "/CN=localhost",
        )
        _run(
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr_file),
            "-CA",
            str(CA_CERT),
            "-CAkey",
            str(CA_KEY),
            "-CAcreateserial",
            "-out",
            str(SERVER_CERT),
            "-days",
            "397",
            "-sha256",
            "-extfile",
            str(ext_file),
            "-extensions",
            "server",
        )
    finally:
        csr_file.unlink(missing_ok=True)
        ext_file.unlink(missing_ok=True)
    SERVER_KEY.chmod(0o600)
    print(f"Local CA certificate: {CA_CERT}")
    print(f"HTTPS certificate: {SERVER_CERT}")


if __name__ == "__main__":
    try:
        generate()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Could not issue local TLS certificate: {error}", file=sys.stderr)
        raise SystemExit(1) from error
