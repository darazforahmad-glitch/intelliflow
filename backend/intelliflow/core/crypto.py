"""Authenticated encryption for secrets at rest (SEC-2): AES-256-GCM with a key ring.

Blob layout: version(1) | kid_len(1) | kid | nonce(12) | ciphertext+tag
The key id lets keys be rotated: the first key in ENCRYPTION_KEYS encrypts, every
key can decrypt. Associated data (AAD) binds a ciphertext to the row that owns it,
so an encrypted token copied into another row fails to decrypt.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from functools import lru_cache
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from django.conf import settings

_VERSION = 1
_NONCE_BYTES = 12


class DecryptionError(Exception):
    pass


class TokenCipher:
    def __init__(self, keyring: dict[str, bytes], primary_kid: str) -> None:
        if primary_kid not in keyring:
            raise ValueError("Primary key id missing from key ring")
        for kid, key in keyring.items():
            if len(key) != 32:
                raise ValueError(f"Encryption key '{kid}' must be 32 bytes (AES-256)")
        self._keys = {kid: AESGCM(key) for kid, key in keyring.items()}
        self._primary = primary_kid

    @classmethod
    def from_config(cls, spec: str) -> TokenCipher:
        keyring: dict[str, bytes] = {}
        primary: str | None = None
        for item in (part.strip() for part in spec.split(",")):
            if not item:
                continue
            kid, _, b64 = item.partition(":")
            if not kid or not b64:
                raise ValueError("ENCRYPTION_KEYS must look like 'kid:base64key[,kid:base64key]'")
            try:
                keyring[kid] = base64.b64decode(b64, validate=True)
            except binascii.Error as exc:
                raise ValueError(f"Encryption key '{kid}' is not valid base64") from exc
            primary = primary or kid
        if primary is None:
            raise ValueError("ENCRYPTION_KEYS is empty")
        return cls(keyring, primary)

    def encrypt(self, plaintext: bytes, aad: str = "") -> bytes:
        kid = self._primary.encode()
        nonce = os.urandom(_NONCE_BYTES)
        sealed = self._keys[self._primary].encrypt(nonce, plaintext, aad.encode())
        return bytes([_VERSION, len(kid)]) + kid + nonce + sealed

    def decrypt(self, blob: bytes | memoryview, aad: str = "") -> bytes:
        blob = bytes(blob)  # PostgreSQL BinaryField values arrive as memoryview
        try:
            if blob[0] != _VERSION:
                raise DecryptionError("Unsupported ciphertext version")
            kid_len = blob[1]
            kid = blob[2 : 2 + kid_len].decode()
            nonce = blob[2 + kid_len : 2 + kid_len + _NONCE_BYTES]
            sealed = blob[2 + kid_len + _NONCE_BYTES :]
            key = self._keys[kid]
        except (IndexError, KeyError, UnicodeDecodeError) as exc:
            raise DecryptionError("Malformed ciphertext or unknown key id") from exc
        try:
            return key.decrypt(nonce, sealed, aad.encode())
        except InvalidTag as exc:
            raise DecryptionError("Ciphertext failed authentication") from exc

    def encrypt_json(self, data: Any, aad: str = "") -> bytes:
        return self.encrypt(json.dumps(data, separators=(",", ":"), default=str).encode(), aad)

    def decrypt_json(self, blob: bytes | memoryview, aad: str = "") -> Any:
        return json.loads(self.decrypt(blob, aad))


@lru_cache(maxsize=1)
def get_cipher() -> TokenCipher:
    return TokenCipher.from_config(settings.ENCRYPTION_KEYS)


def generate_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()
