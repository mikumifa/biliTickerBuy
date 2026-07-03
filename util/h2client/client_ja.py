#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import os
import re
import socket
import struct
import sys
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote, urlsplit

try:
    from cryptography.hazmat.primitives import hashes, hmac, serialization
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
except ImportError as exc:  # pragma: no cover - only used for a friendly CLI error.
    print(
        "Missing dependency: cryptography. Install it with:\n"
        "  python -m pip install cryptography",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


DEFAULT_HOST = "show.bilibili.com"
DEFAULT_PORT = 443

TARGET_JA3_FULL = (
    "771,"
    "4865-4866-4867-49195-49199-49196-49200-52393-52392-49161-49171-49162-49172-156-157-47-53-10,"
    "0-23-65281-10-11-35-16-13-51-45-43-21,"
    "29-23-24,"
    "0"
)
TARGET_JA3 = "c88e49469ef95bb8d35733505283cbd0"
TARGET_JA4 = "t13d1812h2_e8a523a41297_ef7df7f74e48"
TARGET_JA4_R = (
    "t13d1812h2_"
    "000a,002f,0035,009c,009d,1301,1302,1303,c009,c00a,c013,c014,c02b,c02c,c02f,c030,cca8,cca9_"
    "000a,000b,000d,0015,0017,0023,002b,002d,0033,ff01_"
    "0403,0804,0401,0503,0805,0501,0806,0601,0201"
)


def u8(value: int) -> bytes:
    return struct.pack("!B", value)


def u16(value: int) -> bytes:
    return struct.pack("!H", value)


def u24(value: int) -> bytes:
    return value.to_bytes(3, "big")


def vec_u8(data: bytes) -> bytes:
    if len(data) > 255:
        raise ValueError("u8 vector is too long")
    return u8(len(data)) + data


def vec_u16(data: bytes) -> bytes:
    if len(data) > 65535:
        raise ValueError("u16 vector is too long")
    return u16(len(data)) + data


def tls_ext(ext_type: int, body: bytes) -> bytes:
    return u16(ext_type) + vec_u16(body)


@dataclass(frozen=True)
class ClientHelloProfile:
    record_version: int = 0x0301
    legacy_version: int = 0x0303
    session_id_len: int = 32
    target_record_payload_len: int = 512
    ciphers: tuple[int, ...] = (
        0x1301,
        0x1302,
        0x1303,
        0xC02B,
        0xC02F,
        0xC02C,
        0xC030,
        0xCCA9,
        0xCCA8,
        0xC009,
        0xC013,
        0xC00A,
        0xC014,
        0x009C,
        0x009D,
        0x002F,
        0x0035,
        0x000A,
    )
    extension_order: tuple[int, ...] = (
        0,
        23,
        65281,
        10,
        11,
        35,
        16,
        13,
        51,
        45,
        43,
        21,
    )
    supported_groups: tuple[int, ...] = (29, 23, 24)
    ec_point_formats: tuple[int, ...] = (0,)
    signature_algorithms: tuple[int, ...] = (
        0x0403,
        0x0804,
        0x0401,
        0x0503,
        0x0805,
        0x0501,
        0x0806,
        0x0601,
        0x0201,
    )
    supported_versions: tuple[int, ...] = (0x0304, 0x0303, 0x0302, 0x0301)
    psk_key_exchange_modes: tuple[int, ...] = (1,)
    alpn_protocols: tuple[bytes, ...] = (b"h2", b"http/1.1")
    key_share_group: int = 29


@dataclass
class BuiltClientHello:
    record: bytes
    handshake: bytes
    private_key: x25519.X25519PrivateKey
    profile: ClientHelloProfile
    sni: str
    padding_len: int


@dataclass(frozen=True)
class Fingerprints:
    ja3_full: str
    ja3: str
    ja4: str
    ja4_r: str


def build_extension_body(
    ext_type: int,
    *,
    sni: str,
    profile: ClientHelloProfile,
    key_share_public: bytes,
    padding_len: int,
) -> bytes:
    if ext_type == 0:
        name = sni.encode("idna")
        return vec_u16(b"\x00" + vec_u16(name))
    if ext_type == 23:
        return b""
    if ext_type == 65281:
        return b"\x00"
    if ext_type == 10:
        return vec_u16(b"".join(u16(group) for group in profile.supported_groups))
    if ext_type == 11:
        return vec_u8(bytes(profile.ec_point_formats))
    if ext_type == 35:
        return b""
    if ext_type == 16:
        return vec_u16(b"".join(vec_u8(proto) for proto in profile.alpn_protocols))
    if ext_type == 13:
        return vec_u16(b"".join(u16(alg) for alg in profile.signature_algorithms))
    if ext_type == 51:
        key_share = u16(profile.key_share_group) + vec_u16(key_share_public)
        return vec_u16(key_share)
    if ext_type == 45:
        return vec_u8(bytes(profile.psk_key_exchange_modes))
    if ext_type == 43:
        return vec_u8(b"".join(u16(version) for version in profile.supported_versions))
    if ext_type == 21:
        return b"\x00" * padding_len
    raise ValueError(f"unsupported extension type: {ext_type}")


def build_extensions(
    *,
    sni: str,
    profile: ClientHelloProfile,
    key_share_public: bytes,
    padding_len: int,
) -> bytes:
    extensions = []
    for ext_type in profile.extension_order:
        body = build_extension_body(
            ext_type,
            sni=sni,
            profile=profile,
            key_share_public=key_share_public,
            padding_len=padding_len,
        )
        extensions.append(tls_ext(ext_type, body))
    return b"".join(extensions)


def build_client_hello(
    *,
    sni: str,
    profile: ClientHelloProfile,
    random_bytes: bytes | None = None,
    session_id: bytes | None = None,
) -> BuiltClientHello:
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    if random_bytes is None:
        random_bytes = os.urandom(32)
    if session_id is None:
        session_id = os.urandom(profile.session_id_len)
    if len(random_bytes) != 32:
        raise ValueError("TLS random must be 32 bytes")
    if len(session_id) != profile.session_id_len:
        raise ValueError(f"session_id must be {profile.session_id_len} bytes")

    def body_with_padding(padding_len: int) -> bytes:
        extensions = build_extensions(
            sni=sni,
            profile=profile,
            key_share_public=public_key,
            padding_len=padding_len,
        )
        return b"".join(
            [
                u16(profile.legacy_version),
                random_bytes,
                vec_u8(session_id),
                vec_u16(b"".join(u16(cipher) for cipher in profile.ciphers)),
                vec_u8(b"\x00"),
                vec_u16(extensions),
            ]
        )

    body_without_padding_data = body_with_padding(0)
    handshake_without_padding_data = b"\x01" + u24(len(body_without_padding_data)) + body_without_padding_data
    padding_len = profile.target_record_payload_len - len(handshake_without_padding_data)
    if padding_len < 0:
        raise ValueError(
            "ClientHello is already larger than the target record length; "
            "reduce SNI length or increase target_record_payload_len"
        )

    body = body_with_padding(padding_len)
    handshake = b"\x01" + u24(len(body)) + body
    record = b"\x16" + u16(profile.record_version) + vec_u16(handshake)
    return BuiltClientHello(
        record=record,
        handshake=handshake,
        private_key=private_key,
        profile=profile,
        sni=sni,
        padding_len=padding_len,
    )


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("ascii")).hexdigest()


def sha256_12(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:12]


def tls_version_for_ja4(version: int) -> str:
    mapping = {
        0x0301: "10",
        0x0302: "11",
        0x0303: "12",
        0x0304: "13",
    }
    return mapping.get(version, f"{version & 0xff:02d}")


def is_domain_name(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return True
    return False


def parse_client_hello_record(record: bytes) -> dict[str, object]:
    if len(record) < 5:
        raise ValueError("TLS record is too short")
    content_type = record[0]
    if content_type != 22:
        raise ValueError(f"expected handshake record, got content type {content_type}")
    record_len = struct.unpack("!H", record[3:5])[0]
    if len(record) < 5 + record_len:
        raise ValueError("TLS record is truncated")

    handshake = record[5 : 5 + record_len]
    if len(handshake) < 4 or handshake[0] != 1:
        raise ValueError("expected ClientHello handshake")
    handshake_len = int.from_bytes(handshake[1:4], "big")
    body = handshake[4 : 4 + handshake_len]

    pos = 0
    legacy_version = struct.unpack("!H", body[pos : pos + 2])[0]
    pos += 2 + 32
    session_id_len = body[pos]
    pos += 1 + session_id_len

    cipher_len = struct.unpack("!H", body[pos : pos + 2])[0]
    pos += 2
    ciphers = [
        struct.unpack("!H", body[i : i + 2])[0]
        for i in range(pos, pos + cipher_len, 2)
    ]
    pos += cipher_len

    compression_len = body[pos]
    pos += 1 + compression_len

    ext_len = struct.unpack("!H", body[pos : pos + 2])[0]
    pos += 2
    ext_end = pos + ext_len

    extensions: list[int] = []
    supported_groups: list[int] = []
    ec_point_formats: list[int] = []
    signature_algorithms: list[int] = []
    supported_versions: list[int] = []
    alpn_protocols: list[str] = []
    sni = ""
    padding_len = 0

    while pos < ext_end:
        ext_type = struct.unpack("!H", body[pos : pos + 2])[0]
        ext_body_len = struct.unpack("!H", body[pos + 2 : pos + 4])[0]
        ext_body = body[pos + 4 : pos + 4 + ext_body_len]
        extensions.append(ext_type)

        if ext_type == 0 and len(ext_body) >= 5:
            names_len = struct.unpack("!H", ext_body[:2])[0]
            names = ext_body[2 : 2 + names_len]
            if len(names) >= 3 and names[0] == 0:
                name_len = struct.unpack("!H", names[1:3])[0]
                sni = names[3 : 3 + name_len].decode("ascii", errors="replace")
        elif ext_type == 10 and len(ext_body) >= 2:
            group_len = struct.unpack("!H", ext_body[:2])[0]
            supported_groups = [
                struct.unpack("!H", ext_body[2 + i : 4 + i])[0]
                for i in range(0, group_len, 2)
            ]
        elif ext_type == 11 and ext_body:
            ec_point_formats = list(ext_body[1 : 1 + ext_body[0]])
        elif ext_type == 13 and len(ext_body) >= 2:
            sig_len = struct.unpack("!H", ext_body[:2])[0]
            signature_algorithms = [
                struct.unpack("!H", ext_body[2 + i : 4 + i])[0]
                for i in range(0, sig_len, 2)
            ]
        elif ext_type == 16 and len(ext_body) >= 2:
            names_len = struct.unpack("!H", ext_body[:2])[0]
            p = 2
            while p < 2 + names_len and p < len(ext_body):
                name_len = ext_body[p]
                p += 1
                alpn_protocols.append(ext_body[p : p + name_len].decode("ascii", errors="replace"))
                p += name_len
        elif ext_type == 43 and ext_body:
            version_len = ext_body[0]
            supported_versions = [
                struct.unpack("!H", ext_body[1 + i : 3 + i])[0]
                for i in range(0, version_len, 2)
            ]
        elif ext_type == 21:
            padding_len = ext_body_len

        pos += 4 + ext_body_len

    return {
        "legacy_version": legacy_version,
        "ciphers": ciphers,
        "extensions": extensions,
        "supported_groups": supported_groups,
        "ec_point_formats": ec_point_formats,
        "signature_algorithms": signature_algorithms,
        "supported_versions": supported_versions,
        "alpn_protocols": alpn_protocols,
        "sni": sni,
        "padding_len": padding_len,
    }


def fingerprints_from_client_hello(record: bytes) -> Fingerprints:
    parsed = parse_client_hello_record(record)
    legacy_version = parsed["legacy_version"]
    ciphers = parsed["ciphers"]
    extensions = parsed["extensions"]
    supported_groups = parsed["supported_groups"]
    ec_point_formats = parsed["ec_point_formats"]
    signature_algorithms = parsed["signature_algorithms"]
    supported_versions = parsed["supported_versions"]
    alpn_protocols = parsed["alpn_protocols"]
    sni = parsed["sni"]

    assert isinstance(legacy_version, int)
    assert isinstance(ciphers, list)
    assert isinstance(extensions, list)
    assert isinstance(supported_groups, list)
    assert isinstance(ec_point_formats, list)
    assert isinstance(signature_algorithms, list)
    assert isinstance(supported_versions, list)
    assert isinstance(alpn_protocols, list)
    assert isinstance(sni, str)

    ja3_full = ",".join(
        [
            str(legacy_version),
            "-".join(str(cipher) for cipher in ciphers),
            "-".join(str(ext_type) for ext_type in extensions),
            "-".join(str(group) for group in supported_groups),
            "-".join(str(point_format) for point_format in ec_point_formats),
        ]
    )

    cipher_hex = ",".join(f"{cipher:04x}" for cipher in sorted(ciphers))
    ja4_extensions = sorted(ext_type for ext_type in extensions if ext_type not in (0, 16))
    extension_hex = ",".join(f"{ext_type:04x}" for ext_type in ja4_extensions)
    signature_hex = ",".join(f"{alg:04x}" for alg in signature_algorithms)
    extension_signature_hex = f"{extension_hex}_{signature_hex}"

    max_supported = max(supported_versions) if supported_versions else legacy_version
    sni_marker = "d" if sni and is_domain_name(sni) else "i"
    alpn = alpn_protocols[0] if alpn_protocols else "00"
    ja4_a = (
        f"t{tls_version_for_ja4(max_supported)}"
        f"{sni_marker}"
        f"{len(ciphers):02d}"
        f"{len(extensions):02d}"
        f"{alpn}"
    )
    ja4_r = f"{ja4_a}_{cipher_hex}_{extension_signature_hex}"
    ja4 = f"{ja4_a}_{sha256_12(cipher_hex)}_{sha256_12(extension_signature_hex)}"

    return Fingerprints(
        ja3_full=ja3_full,
        ja3=md5_hex(ja3_full),
        ja4=ja4,
        ja4_r=ja4_r,
    )


def read_targets_from_file(path: str) -> dict[str, str]:
    try:
        text = open(path, "r", encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        return {}

    patterns = {
        "ja4": r"\[JA4:\s*([^\]]+)\]",
        "ja4_r": r"\[JA4_r:\s*([^\]]+)\]",
        "ja3_full": r"\[JA3 Fullstring:\s*([^\]]+)\]",
        "ja3": r"\[JA3:\s*([0-9a-fA-F]+)\]",
    }
    targets: dict[str, str] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            targets[key] = match.group(1).strip()
    return targets


@dataclass(frozen=True)
class CipherSuiteSpec:
    name: str
    hash_factory: Callable[[], hashes.HashAlgorithm]
    hash_len: int
    key_len: int
    aead_factory: Callable[[bytes], object]


CIPHER_SUITES = {
    0x1301: CipherSuiteSpec("TLS_AES_128_GCM_SHA256", hashes.SHA256, 32, 16, AESGCM),
    0x1302: CipherSuiteSpec("TLS_AES_256_GCM_SHA384", hashes.SHA384, 48, 32, AESGCM),
    0x1303: CipherSuiteSpec("TLS_CHACHA20_POLY1305_SHA256", hashes.SHA256, 32, 32, ChaCha20Poly1305),
}

HANDSHAKE_NAMES = {
    2: "ServerHello",
    4: "NewSessionTicket",
    8: "EncryptedExtensions",
    11: "Certificate",
    15: "CertificateVerify",
    20: "Finished",
}

ALERT_DESCRIPTIONS = {
    0: "close_notify",
    10: "unexpected_message",
    20: "bad_record_mac",
    40: "handshake_failure",
    42: "bad_certificate",
    47: "illegal_parameter",
    70: "protocol_version",
    80: "internal_error",
    90: "user_canceled",
    109: "missing_extension",
    110: "unsupported_extension",
    112: "unrecognized_name",
}


class TLSAlert(RuntimeError):
    pass


class HandshakeBuffer:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> None:
        self._buffer.extend(data)

    def pop_messages(self) -> list[bytes]:
        messages: list[bytes] = []
        while len(self._buffer) >= 4:
            msg_len = int.from_bytes(self._buffer[1:4], "big")
            total_len = 4 + msg_len
            if len(self._buffer) < total_len:
                break
            messages.append(bytes(self._buffer[:total_len]))
            del self._buffer[:total_len]
        return messages


def hash_bytes(data: bytes, spec: CipherSuiteSpec) -> bytes:
    digest = hashes.Hash(spec.hash_factory())
    digest.update(data)
    return digest.finalize()


def hmac_bytes(key: bytes, data: bytes, spec: CipherSuiteSpec) -> bytes:
    mac = hmac.HMAC(key, spec.hash_factory())
    mac.update(data)
    return mac.finalize()


def hkdf_extract(salt: bytes | None, ikm: bytes, spec: CipherSuiteSpec) -> bytes:
    if salt is None:
        salt = b"\x00" * spec.hash_len
    return hmac_bytes(salt, ikm, spec)


def hkdf_expand(secret: bytes, info: bytes, length: int, spec: CipherSuiteSpec) -> bytes:
    output = b""
    previous = b""
    counter = 1
    while len(output) < length:
        mac = hmac.HMAC(secret, spec.hash_factory())
        mac.update(previous + info + bytes([counter]))
        previous = mac.finalize()
        output += previous
        counter += 1
    return output[:length]


def hkdf_expand_label(secret: bytes, label: bytes, context: bytes, length: int, spec: CipherSuiteSpec) -> bytes:
    full_label = b"tls13 " + label
    hkdf_label = u16(length) + vec_u8(full_label) + vec_u8(context)
    return hkdf_expand(secret, hkdf_label, length, spec)


def derive_secret(secret: bytes, label: bytes, transcript_hash: bytes, spec: CipherSuiteSpec) -> bytes:
    return hkdf_expand_label(secret, label, transcript_hash, spec.hash_len, spec)


def xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


@dataclass
class TrafficCipher:
    spec: CipherSuiteSpec
    secret: bytes
    sequence: int = 0

    def __post_init__(self) -> None:
        self.key = hkdf_expand_label(self.secret, b"key", b"", self.spec.key_len, self.spec)
        self.iv = hkdf_expand_label(self.secret, b"iv", b"", 12, self.spec)
        self.aead = self.spec.aead_factory(self.key)

    def nonce(self) -> bytes:
        sequence_bytes = self.sequence.to_bytes(12, "big")
        return xor_bytes(self.iv, sequence_bytes)

    def decrypt_record(self, header: bytes, ciphertext: bytes) -> tuple[int, bytes]:
        plaintext = self.aead.decrypt(self.nonce(), ciphertext, header)
        self.sequence += 1
        idx = len(plaintext) - 1
        while idx >= 0 and plaintext[idx] == 0:
            idx -= 1
        if idx < 0:
            raise ValueError("TLS inner plaintext has no content type")
        return plaintext[idx], plaintext[:idx]

    def encrypt_record(self, inner_type: int, content: bytes) -> bytes:
        plaintext = content + bytes([inner_type])
        ciphertext_len = len(plaintext) + 16
        header = b"\x17\x03\x03" + u16(ciphertext_len)
        ciphertext = self.aead.encrypt(self.nonce(), plaintext, header)
        self.sequence += 1
        return header + ciphertext


@dataclass
class ServerHello:
    selected_version: int
    cipher_suite: int
    key_share_group: int
    key_share_public: bytes
    session_id: bytes


@dataclass
class TLSHandshakeResult:
    cipher_suite: str
    selected_alpn: str
    server_finished_verified: bool
    client_finished_sent: bool
    post_handshake_record: str | None


@dataclass
class TLS13Connection:
    sock: socket.socket
    cipher_suite: str
    selected_alpn: str
    client_app_cipher: TrafficCipher
    server_app_cipher: TrafficCipher

    def send_application_data(self, data: bytes) -> None:
        max_fragment = 16384
        for pos in range(0, len(data), max_fragment):
            chunk = data[pos : pos + max_fragment]
            self.sock.sendall(self.client_app_cipher.encrypt_record(23, chunk))

    def read_inner_record(self) -> tuple[int, bytes]:
        while True:
            content_type, _, fragment, header = read_tls_record(self.sock)
            if content_type == 21:
                raise_for_alert(fragment)
            if content_type != 23:
                raise ValueError(f"expected encrypted TLS record, got content type {content_type}")
            inner_type, plaintext = self.server_app_cipher.decrypt_record(header, fragment)
            if inner_type == 22:
                continue
            return inner_type, plaintext

    def read_application_data(self) -> bytes:
        while True:
            inner_type, plaintext = self.read_inner_record()
            if inner_type == 21:
                raise_for_alert(plaintext)
            if inner_type == 23:
                return plaintext


def recvall(sock: socket.socket, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = sock.recv(length - len(chunks))
        if not chunk:
            raise EOFError("socket closed while reading")
        chunks.extend(chunk)
    return bytes(chunks)


def read_tls_record(sock: socket.socket) -> tuple[int, int, bytes, bytes]:
    header = recvall(sock, 5)
    content_type = header[0]
    version = struct.unpack("!H", header[1:3])[0]
    length = struct.unpack("!H", header[3:5])[0]
    fragment = recvall(sock, length)
    return content_type, version, fragment, header


def raise_for_alert(fragment: bytes) -> None:
    if len(fragment) < 2:
        raise TLSAlert("received malformed TLS alert")
    level, description = fragment[0], fragment[1]
    name = ALERT_DESCRIPTIONS.get(description, f"unknown_{description}")
    raise TLSAlert(f"received TLS alert level={level} description={description} ({name})")


def parse_server_hello(message: bytes) -> ServerHello:
    if message[0] != 2:
        raise ValueError("expected ServerHello")
    body = message[4:]
    pos = 0
    legacy_version = struct.unpack("!H", body[pos : pos + 2])[0]
    if legacy_version != 0x0303:
        raise ValueError(f"unexpected ServerHello legacy_version: 0x{legacy_version:04x}")
    pos += 2

    server_random = body[pos : pos + 32]
    pos += 32
    hello_retry_request_random = bytes.fromhex(
        "cf21ad74e59a6111be1d8c021e65b891"
        "c2a211167abb8c5e079e09e2c8a8339c"
    )
    if server_random == hello_retry_request_random:
        raise NotImplementedError("TLS 1.3 HelloRetryRequest is not implemented")

    session_id_len = body[pos]
    pos += 1
    session_id = body[pos : pos + session_id_len]
    pos += session_id_len

    cipher_suite = struct.unpack("!H", body[pos : pos + 2])[0]
    pos += 2
    compression_method = body[pos]
    pos += 1
    if compression_method != 0:
        raise ValueError("server selected non-null compression")

    selected_version = 0
    key_share_group = 0
    key_share_public = b""
    extensions_len = struct.unpack("!H", body[pos : pos + 2])[0]
    pos += 2
    end = pos + extensions_len
    while pos < end:
        ext_type = struct.unpack("!H", body[pos : pos + 2])[0]
        ext_len = struct.unpack("!H", body[pos + 2 : pos + 4])[0]
        ext_body = body[pos + 4 : pos + 4 + ext_len]
        if ext_type == 43:
            selected_version = struct.unpack("!H", ext_body[:2])[0]
        elif ext_type == 51:
            key_share_group = struct.unpack("!H", ext_body[:2])[0]
            key_len = struct.unpack("!H", ext_body[2:4])[0]
            key_share_public = ext_body[4 : 4 + key_len]
        pos += 4 + ext_len

    if not selected_version:
        raise ValueError("ServerHello did not include supported_versions")
    if not key_share_public:
        raise ValueError("ServerHello did not include key_share")

    return ServerHello(
        selected_version=selected_version,
        cipher_suite=cipher_suite,
        key_share_group=key_share_group,
        key_share_public=key_share_public,
        session_id=session_id,
    )


def parse_encrypted_extensions(message: bytes) -> str:
    if message[0] != 8:
        raise ValueError("expected EncryptedExtensions")
    body = message[4:]
    pos = 0
    extensions_len = struct.unpack("!H", body[pos : pos + 2])[0]
    pos += 2
    end = pos + extensions_len
    selected_alpn = ""
    while pos < end:
        ext_type = struct.unpack("!H", body[pos : pos + 2])[0]
        ext_len = struct.unpack("!H", body[pos + 2 : pos + 4])[0]
        ext_body = body[pos + 4 : pos + 4 + ext_len]
        if ext_type == 16 and len(ext_body) >= 3:
            names_len = struct.unpack("!H", ext_body[:2])[0]
            p = 2
            if names_len and p < len(ext_body):
                name_len = ext_body[p]
                p += 1
                selected_alpn = ext_body[p : p + name_len].decode("ascii", errors="replace")
        pos += 4 + ext_len
    return selected_alpn


def pop_first_handshake_message(sock: socket.socket, buffer: HandshakeBuffer) -> bytes:
    while True:
        content_type, _, fragment, _ = read_tls_record(sock)
        if content_type == 20:
            continue
        if content_type == 21:
            raise_for_alert(fragment)
        if content_type != 22:
            raise ValueError(f"expected plaintext handshake record, got content type {content_type}")
        buffer.feed(fragment)
        messages = buffer.pop_messages()
        if messages:
            if len(messages) > 1:
                raise ValueError("unexpected extra plaintext handshake messages")
            return messages[0]


def open_tls13_connection(sock: socket.socket, built: BuiltClientHello) -> TLS13Connection:
    sock.sendall(built.record)

    plaintext_buffer = HandshakeBuffer()
    server_hello_msg = pop_first_handshake_message(sock, plaintext_buffer)
    transcript = bytearray(built.handshake)
    transcript.extend(server_hello_msg)

    server_hello = parse_server_hello(server_hello_msg)
    if server_hello.selected_version != 0x0304:
        raise NotImplementedError(
            f"server selected TLS 0x{server_hello.selected_version:04x}; "
            "this script implements TLS 1.3 handshakes only"
        )
    if server_hello.cipher_suite not in CIPHER_SUITES:
        raise NotImplementedError(f"unsupported TLS 1.3 cipher suite: 0x{server_hello.cipher_suite:04x}")
    if server_hello.key_share_group != built.profile.key_share_group:
        raise NotImplementedError(
            f"server selected key share group {server_hello.key_share_group}; "
            f"expected {built.profile.key_share_group}"
        )

    spec = CIPHER_SUITES[server_hello.cipher_suite]
    peer_public_key = x25519.X25519PublicKey.from_public_bytes(server_hello.key_share_public)
    shared_secret = built.private_key.exchange(peer_public_key)

    zero_secret = b"\x00" * spec.hash_len
    empty_hash = hash_bytes(b"", spec)
    early_secret = hkdf_extract(None, zero_secret, spec)
    derived_early = derive_secret(early_secret, b"derived", empty_hash, spec)
    handshake_secret = hkdf_extract(derived_early, shared_secret, spec)

    server_hello_hash = hash_bytes(bytes(transcript), spec)
    client_hs_secret = derive_secret(handshake_secret, b"c hs traffic", server_hello_hash, spec)
    server_hs_secret = derive_secret(handshake_secret, b"s hs traffic", server_hello_hash, spec)
    client_hs_cipher = TrafficCipher(spec, client_hs_secret)
    server_hs_cipher = TrafficCipher(spec, server_hs_secret)

    encrypted_buffer = HandshakeBuffer()
    selected_alpn = ""
    server_finished_verified = False

    while True:
        content_type, _, fragment, header = read_tls_record(sock)
        if content_type == 20:
            continue
        if content_type == 21:
            raise_for_alert(fragment)
        if content_type != 23:
            raise ValueError(f"expected encrypted handshake record, got content type {content_type}")

        inner_type, plaintext = server_hs_cipher.decrypt_record(header, fragment)
        if inner_type != 22:
            raise ValueError(f"expected encrypted handshake content, got inner type {inner_type}")
        encrypted_buffer.feed(plaintext)

        for message in encrypted_buffer.pop_messages():
            msg_type = message[0]
            if msg_type == 8:
                selected_alpn = parse_encrypted_extensions(message)
                transcript.extend(message)
            elif msg_type == 20:
                finished_key = hkdf_expand_label(server_hs_secret, b"finished", b"", spec.hash_len, spec)
                expected_verify_data = hmac_bytes(finished_key, hash_bytes(bytes(transcript), spec), spec)
                received_verify_data = message[4:]
                if received_verify_data != expected_verify_data:
                    raise ValueError("server Finished verify_data did not match")
                server_finished_verified = True
                transcript.extend(message)
                break
            else:
                transcript.extend(message)
        if server_finished_verified:
            break

    app_traffic_hash = hash_bytes(bytes(transcript), spec)
    client_finished_key = hkdf_expand_label(client_hs_secret, b"finished", b"", spec.hash_len, spec)
    client_verify_data = hmac_bytes(client_finished_key, app_traffic_hash, spec)
    client_finished = b"\x14" + u24(len(client_verify_data)) + client_verify_data

    sock.sendall(b"\x14\x03\x03\x00\x01\x01")
    sock.sendall(client_hs_cipher.encrypt_record(22, client_finished))
    transcript.extend(client_finished)

    derived_handshake = derive_secret(handshake_secret, b"derived", empty_hash, spec)
    master_secret = hkdf_extract(derived_handshake, zero_secret, spec)
    client_app_secret = derive_secret(master_secret, b"c ap traffic", app_traffic_hash, spec)
    server_app_secret = derive_secret(master_secret, b"s ap traffic", app_traffic_hash, spec)

    return TLS13Connection(
        sock=sock,
        cipher_suite=spec.name,
        selected_alpn=selected_alpn,
        client_app_cipher=TrafficCipher(spec, client_app_secret),
        server_app_cipher=TrafficCipher(spec, server_app_secret),
    )


def complete_tls13_handshake(sock: socket.socket, built: BuiltClientHello) -> TLSHandshakeResult:
    sock.sendall(built.record)

    plaintext_buffer = HandshakeBuffer()
    server_hello_msg = pop_first_handshake_message(sock, plaintext_buffer)
    transcript = bytearray(built.handshake)
    transcript.extend(server_hello_msg)

    server_hello = parse_server_hello(server_hello_msg)
    if server_hello.selected_version != 0x0304:
        raise NotImplementedError(
            f"server selected TLS 0x{server_hello.selected_version:04x}; "
            "this script implements TLS 1.3 handshakes only"
        )
    if server_hello.cipher_suite not in CIPHER_SUITES:
        raise NotImplementedError(f"unsupported TLS 1.3 cipher suite: 0x{server_hello.cipher_suite:04x}")
    if server_hello.key_share_group != built.profile.key_share_group:
        raise NotImplementedError(
            f"server selected key share group {server_hello.key_share_group}; "
            f"expected {built.profile.key_share_group}"
        )

    spec = CIPHER_SUITES[server_hello.cipher_suite]
    peer_public_key = x25519.X25519PublicKey.from_public_bytes(server_hello.key_share_public)
    shared_secret = built.private_key.exchange(peer_public_key)

    zero_secret = b"\x00" * spec.hash_len
    empty_hash = hash_bytes(b"", spec)
    early_secret = hkdf_extract(None, zero_secret, spec)
    derived_early = derive_secret(early_secret, b"derived", empty_hash, spec)
    handshake_secret = hkdf_extract(derived_early, shared_secret, spec)

    server_hello_hash = hash_bytes(bytes(transcript), spec)
    client_hs_secret = derive_secret(handshake_secret, b"c hs traffic", server_hello_hash, spec)
    server_hs_secret = derive_secret(handshake_secret, b"s hs traffic", server_hello_hash, spec)
    client_hs_cipher = TrafficCipher(spec, client_hs_secret)
    server_hs_cipher = TrafficCipher(spec, server_hs_secret)

    encrypted_buffer = HandshakeBuffer()
    selected_alpn = ""
    server_finished_verified = False

    while True:
        content_type, _, fragment, header = read_tls_record(sock)
        if content_type == 20:
            continue
        if content_type == 21:
            raise_for_alert(fragment)
        if content_type != 23:
            raise ValueError(f"expected encrypted handshake record, got content type {content_type}")

        inner_type, plaintext = server_hs_cipher.decrypt_record(header, fragment)
        if inner_type != 22:
            raise ValueError(f"expected encrypted handshake content, got inner type {inner_type}")
        encrypted_buffer.feed(plaintext)

        for message in encrypted_buffer.pop_messages():
            msg_type = message[0]
            if msg_type == 8:
                selected_alpn = parse_encrypted_extensions(message)
                transcript.extend(message)
            elif msg_type == 20:
                finished_key = hkdf_expand_label(server_hs_secret, b"finished", b"", spec.hash_len, spec)
                expected_verify_data = hmac_bytes(finished_key, hash_bytes(bytes(transcript), spec), spec)
                received_verify_data = message[4:]
                if received_verify_data != expected_verify_data:
                    raise ValueError("server Finished verify_data did not match")
                server_finished_verified = True
                transcript.extend(message)
                break
            else:
                transcript.extend(message)
        if server_finished_verified:
            break

    app_traffic_hash = hash_bytes(bytes(transcript), spec)
    client_finished_key = hkdf_expand_label(client_hs_secret, b"finished", b"", spec.hash_len, spec)
    client_verify_data = hmac_bytes(client_finished_key, app_traffic_hash, spec)
    client_finished = b"\x14" + u24(len(client_verify_data)) + client_verify_data

    sock.sendall(b"\x14\x03\x03\x00\x01\x01")
    sock.sendall(client_hs_cipher.encrypt_record(22, client_finished))
    transcript.extend(client_finished)

    post_handshake_record = None
    try:
        old_timeout = sock.gettimeout()
        sock.settimeout(0.75)

        derived_handshake = derive_secret(handshake_secret, b"derived", empty_hash, spec)
        master_secret = hkdf_extract(derived_handshake, zero_secret, spec)
        server_app_secret = derive_secret(master_secret, b"s ap traffic", app_traffic_hash, spec)
        server_app_cipher = TrafficCipher(spec, server_app_secret)

        content_type, _, fragment, header = read_tls_record(sock)
        if content_type == 23:
            inner_type, plaintext = server_app_cipher.decrypt_record(header, fragment)
            if inner_type == 22 and plaintext:
                msg_name = HANDSHAKE_NAMES.get(plaintext[0], f"handshake_{plaintext[0]}")
                post_handshake_record = msg_name
            else:
                post_handshake_record = f"inner_type_{inner_type}"
        elif content_type == 21:
            raise_for_alert(fragment)
        else:
            post_handshake_record = f"content_type_{content_type}"
    except socket.timeout:
        post_handshake_record = None
    finally:
        try:
            sock.settimeout(old_timeout)
        except UnboundLocalError:
            pass

    return TLSHandshakeResult(
        cipher_suite=spec.name,
        selected_alpn=selected_alpn,
        server_finished_verified=server_finished_verified,
        client_finished_sent=True,
        post_handshake_record=post_handshake_record,
    )


def connect_tcp(
    *,
    host: str,
    port: int,
    family: str,
    source_ip: str | None,
    timeout: float,
    proxy_url: str | None = None,
) -> socket.socket:
    if proxy_url:
        return connect_tcp_via_proxy(
            host=host,
            port=port,
            timeout=timeout,
            proxy_url=proxy_url,
        )

    family_map = {
        "auto": socket.AF_UNSPEC,
        "ipv4": socket.AF_INET,
        "ipv6": socket.AF_INET6,
    }
    infos = socket.getaddrinfo(host, port, family_map[family], socket.SOCK_STREAM)
    last_error: OSError | None = None
    for af, socktype, proto, _, sockaddr in infos:
        sock = socket.socket(af, socktype, proto)
        sock.settimeout(timeout)
        try:
            if source_ip:
                if af == socket.AF_INET6:
                    sock.bind((source_ip, 0, 0, 0))
                else:
                    sock.bind((source_ip, 0))
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last_error = exc
            sock.close()
    if last_error is not None:
        raise last_error
    raise OSError(f"could not resolve {host}:{port}")


def connect_tcp_via_proxy(
    *,
    host: str,
    port: int,
    timeout: float,
    proxy_url: str,
) -> socket.socket:
    parsed = urlsplit(proxy_url)
    scheme = parsed.scheme.lower()
    if not parsed.hostname or not parsed.port:
        raise OSError(f"invalid proxy URL: {proxy_url!r}")

    if scheme in {"socks", "socks4", "socks5"}:
        try:
            import socks
        except ImportError as exc:
            raise OSError("SOCKS proxy requires PySocks") from exc

        proxy_type = socks.SOCKS4 if scheme == "socks4" else socks.SOCKS5
        sock = socks.socksocket()
        sock.settimeout(timeout)
        sock.set_proxy(
            proxy_type,
            parsed.hostname,
            parsed.port,
            username=unquote(parsed.username) if parsed.username else None,
            password=unquote(parsed.password) if parsed.password else None,
        )
        try:
            sock.connect((host, port))
            return sock
        except OSError:
            sock.close()
            raise

    if scheme not in {"http", "https"}:
        raise OSError(f"unsupported proxy scheme: {scheme}")
    if scheme == "https":
        raise OSError("HTTPS proxy is not supported by the JA/H2 transport")

    sock = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
    sock.settimeout(timeout)
    authority = f"{host}:{port}"
    lines = [
        f"CONNECT {authority} HTTP/1.1",
        f"Host: {authority}",
        "Proxy-Connection: Keep-Alive",
    ]
    if parsed.username is not None:
        user = unquote(parsed.username)
        password = unquote(parsed.password or "")
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        lines.append(f"Proxy-Authorization: Basic {token}")
    request = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")
    try:
        sock.sendall(request)
        buffer = bytearray()
        while b"\r\n\r\n" not in buffer:
            chunk = sock.recv(4096)
            if not chunk:
                raise OSError("proxy closed connection during CONNECT")
            buffer.extend(chunk)
            if len(buffer) > 65536:
                raise OSError("proxy CONNECT response is too large")
        status_line = bytes(buffer).split(b"\r\n", 1)[0].decode(
            "iso-8859-1",
            errors="replace",
        )
        parts = status_line.split()
        if len(parts) < 2 or not parts[1].isdigit() or int(parts[1]) // 100 != 2:
            raise OSError(f"proxy CONNECT failed: {status_line}")
        return sock
    except OSError:
        sock.close()
        raise


def send_client_hello_only(sock: socket.socket, built: BuiltClientHello) -> tuple[int, int, int]:
    sock.sendall(built.record)
    content_type, version, fragment, _ = read_tls_record(sock)
    if content_type == 21:
        raise_for_alert(fragment)
    return content_type, version, len(fragment)


def print_fingerprint_report(generated: Fingerprints, targets: dict[str, str], padding_len: int) -> None:
    target_ja3_full = targets.get("ja3_full", TARGET_JA3_FULL)
    target_ja3 = targets.get("ja3", TARGET_JA3)
    target_ja4 = targets.get("ja4", TARGET_JA4)
    target_ja4_r = targets.get("ja4_r", TARGET_JA4_R)

    checks = {
        "JA3 Fullstring": generated.ja3_full == target_ja3_full,
        "JA3": generated.ja3 == target_ja3,
        "JA4": generated.ja4 == target_ja4,
        "JA4_r": generated.ja4_r == target_ja4_r,
    }

    print("Generated ClientHello fingerprints:")
    print(f"  JA3 Fullstring: {generated.ja3_full}")
    print(f"  JA3: {generated.ja3}")
    print(f"  JA4: {generated.ja4}")
    print(f"  JA4_r: {generated.ja4_r}")
    print(f"  padding extension length: {padding_len}")
    print("Target match:")
    for name, ok in checks.items():
        print(f"  {name}: {'OK' if ok else 'MISMATCH'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send a TLS ClientHello matching the JA3/JA4 values in client_ja.txt. "
            "Default mode also completes a minimal TLS 1.3 handshake."
        )
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="TCP host to connect to.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port to connect to.")
    parser.add_argument("--sni", default=None, help="SNI hostname. Defaults to --host.")
    parser.add_argument(
        "--mode",
        choices=("handshake", "hello"),
        default="handshake",
        help="'handshake' completes TLS 1.3; 'hello' only sends ClientHello and reads one record.",
    )
    parser.add_argument(
        "--family",
        choices=("auto", "ipv4", "ipv6"),
        default="auto",
        help="Address family for the TCP connection.",
    )
    parser.add_argument("--source-ip", default=None, help="Optional local source IP to bind before connecting.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Socket timeout in seconds.")
    parser.add_argument("--ja-file", default="client_ja.txt", help="Wireshark text file containing target JA3/JA4.")
    parser.add_argument("--dump-client-hello", default=None, help="Write the generated TLS record to this file.")
    parser.add_argument("--no-connect", action="store_true", help="Only build and verify ClientHello locally.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sni = args.sni or args.host
    profile = ClientHelloProfile()
    built = build_client_hello(sni=sni, profile=profile)
    generated = fingerprints_from_client_hello(built.record)
    targets = read_targets_from_file(args.ja_file)

    print_fingerprint_report(generated, targets, built.padding_len)

    if args.dump_client_hello:
        with open(args.dump_client_hello, "wb") as fp:
            fp.write(built.record)
        print(f"Wrote ClientHello record: {args.dump_client_hello}")

    if args.no_connect:
        return 0

    sock = connect_tcp(
        host=args.host,
        port=args.port,
        family=args.family,
        source_ip=args.source_ip,
        timeout=args.timeout,
    )
    with sock:
        peer = sock.getpeername()
        print(f"Connected TCP: {peer}")
        if args.mode == "hello":
            content_type, version, fragment_len = send_client_hello_only(sock, built)
            print(
                "Received first TLS record: "
                f"content_type={content_type}, version=0x{version:04x}, fragment_len={fragment_len}"
            )
            return 0

        result = complete_tls13_handshake(sock, built)
        print("TLS 1.3 handshake completed:")
        print(f"  cipher: {result.cipher_suite}")
        print(f"  selected ALPN: {result.selected_alpn or '(none)'}")
        print(f"  server Finished verified: {result.server_finished_verified}")
        print(f"  client Finished sent: {result.client_finished_sent}")
        if result.post_handshake_record:
            print(f"  post-handshake record: {result.post_handshake_record}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
