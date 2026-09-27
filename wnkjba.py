"""
wnkjba.py — read and decrypt TISL backup files (`.wnkjba`).

A `.wnkjba` file is produced by the TISL platform's backup engine. It is an
encrypted container that can only be opened with the passphrase set on the
server when the backup was made. Without the passphrase the bytes are
meaningless — the encryption is authenticated, so a wrong passphrase fails
cleanly rather than returning garbage.

File layout (matches the platform's BackupExporter):

    "WNKJBAK1"                     8-byte magic
    uint32 big-endian header length
    header JSON { v, cipher, kdf, salt, opslimit, memlimit, ss_header }
    framed secretstream chunks:  [uint32 BE len][ciphertext] …  (last = FINAL)

The sealed payload is a ZIP of:  manifest.json + data/<module>/<table>.jsonl

Crypto: XChaCha20-Poly1305 secretstream, key = Argon2id(passphrase, salt).
This module only ever *reads*; it never writes to a database or the network.
"""

from __future__ import annotations

import io
import json
import struct
import zipfile
from dataclasses import dataclass, field
from typing import Iterator

import nacl.bindings as sodium
import nacl.pwhash.argon2id as argon2id

MAGIC = b"WNKJBAK1"
_KEYBYTES = sodium.crypto_secretstream_xchacha20poly1305_KEYBYTES
_TAG_FINAL = sodium.crypto_secretstream_xchacha20poly1305_TAG_FINAL
_ABYTES = sodium.crypto_secretstream_xchacha20poly1305_ABYTES


class WnkjbaError(Exception):
    """Anything that stops us reading the file (not a wrong passphrase)."""


class WrongPassphrase(WnkjbaError):
    """The passphrase did not decrypt the file."""


@dataclass
class Table:
    module: str
    name: str
    rows: list[dict]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def columns(self) -> list[str]:
        cols: list[str] = []
        seen: set[str] = set()
        for row in self.rows:
            for k in row.keys():
                if k not in seen:
                    seen.add(k)
                    cols.append(k)
        return cols


@dataclass
class Backup:
    manifest: dict
    tables: list[Table] = field(default_factory=list)

    # ── convenience accessors ────────────────────────────────────────────
    @property
    def business(self) -> str | None:
        return self.manifest.get("business")

    @property
    def client_uuid(self) -> str | None:
        return self.manifest.get("client_uuid")

    @property
    def created_at(self) -> str | None:
        return self.manifest.get("created_at")

    @property
    def modules(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for t in self.tables:
            if t.module not in seen:
                seen.add(t.module)
                out.append(t.module)
        return out

    def tables_for(self, module: str) -> list[Table]:
        return [t for t in self.tables if t.module == module]

    def get(self, module: str, name: str) -> Table | None:
        for t in self.tables:
            if t.module == module and t.name == name:
                return t
        return None

    @property
    def total_rows(self) -> int:
        return sum(t.row_count for t in self.tables)


# ── low-level: parse the container and decrypt ───────────────────────────

def _read_header(data: bytes) -> tuple[dict, int]:
    if len(data) < len(MAGIC) + 4:
        raise WnkjbaError("This file is too small to be a .wnkjba backup.")
    if data[: len(MAGIC)] != MAGIC:
        raise WnkjbaError(
            "This doesn't look like a .wnkjba backup (wrong file signature)."
        )
    pos = len(MAGIC)
    (hlen,) = struct.unpack(">I", data[pos : pos + 4])
    pos += 4
    if pos + hlen > len(data):
        raise WnkjbaError("The backup header is incomplete — the file may be truncated.")
    try:
        header = json.loads(data[pos : pos + hlen].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise WnkjbaError(f"The backup header is unreadable: {e}") from e
    return header, pos + hlen


def _iter_frames(data: bytes, start: int) -> Iterator[bytes]:
    pos = start
    n = len(data)
    while pos < n:
        if pos + 4 > n:
            raise WnkjbaError("The backup is truncated (a chunk length is cut off).")
        (clen,) = struct.unpack(">I", data[pos : pos + 4])
        pos += 4
        if clen < _ABYTES or pos + clen > n:
            raise WnkjbaError("The backup is truncated or corrupted (bad chunk).")
        yield data[pos : pos + clen]
        pos += clen


def _derive_key(passphrase: str, header: dict) -> bytes:
    try:
        import base64

        salt = base64.b64decode(header["salt"])
        opslimit = int(header["opslimit"])
        memlimit = int(header["memlimit"])
    except (KeyError, ValueError) as e:
        raise WnkjbaError(f"The backup header is missing key derivation info: {e}") from e

    if len(salt) != argon2id.SALTBYTES:
        raise WnkjbaError("The backup salt is the wrong size — file may be corrupted.")

    return argon2id.kdf(
        _KEYBYTES,
        passphrase.encode("utf-8"),
        salt,
        opslimit=opslimit,
        memlimit=memlimit,
    )


def decrypt_to_zip_bytes(data: bytes, passphrase: str) -> bytes:
    """Decrypt a whole .wnkjba file in memory and return the ZIP payload bytes."""
    import base64

    header, body_start = _read_header(data)
    key = _derive_key(passphrase, header)

    try:
        ss_header = base64.b64decode(header["ss_header"])
    except (KeyError, ValueError) as e:
        raise WnkjbaError(f"The backup header is missing the stream header: {e}") from e

    state = sodium.crypto_secretstream_xchacha20poly1305_state()
    try:
        sodium.crypto_secretstream_xchacha20poly1305_init_pull(state, ss_header, key)
    except Exception as e:  # pragma: no cover - defensive
        raise WnkjbaError(f"Could not initialise decryption: {e}") from e

    out = io.BytesIO()
    saw_final = False
    for cipher in _iter_frames(data, body_start):
        try:
            chunk, tag = sodium.crypto_secretstream_xchacha20poly1305_pull(
                state, cipher, None
            )
        except Exception as e:
            # Authenticated failure — almost always the wrong passphrase.
            raise WrongPassphrase(
                "That passphrase didn't unlock this backup. "
                "Check it's exactly the one set when the backup was made."
            ) from e
        out.write(chunk)
        if tag == _TAG_FINAL:
            saw_final = True
            break

    if not saw_final:
        raise WnkjbaError("The backup ended without a final chunk — it may be truncated.")

    return out.getvalue()


# ── high-level: open into a Backup object ────────────────────────────────

def open_backup(data: bytes, passphrase: str) -> Backup:
    """Open and fully parse a .wnkjba file into a Backup (manifest + tables)."""
    zip_bytes = decrypt_to_zip_bytes(data, passphrase)

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise WnkjbaError(
            "Decryption succeeded but the contents aren't a valid archive."
        ) from e

    names = set(zf.namelist())
    if "manifest.json" not in names:
        raise WnkjbaError("The backup has no manifest — it may be an unsupported version.")

    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

    # Map table path -> (module, name) from the manifest so names/modules match.
    tables: list[Table] = []
    for mod in manifest.get("modules", []):
        module_key = mod.get("module", "unknown")
        for tbl in mod.get("tables", []):
            table_name = tbl.get("table")
            path = f"data/{module_key}/{table_name}.jsonl"
            rows = _read_jsonl(zf, path) if path in names else []
            tables.append(Table(module=module_key, name=table_name, rows=rows))

    # Fallback: any data/*/*.jsonl the manifest didn't list.
    listed = {f"data/{t.module}/{t.name}.jsonl" for t in tables}
    for name in sorted(names):
        if name.startswith("data/") and name.endswith(".jsonl") and name not in listed:
            parts = name[len("data/") : -len(".jsonl")].split("/", 1)
            if len(parts) == 2:
                module_key, table_name = parts
                tables.append(
                    Table(module=module_key, name=table_name, rows=_read_jsonl(zf, name))
                )

    return Backup(manifest=manifest, tables=tables)


def _read_jsonl(zf: zipfile.ZipFile, path: str) -> list[dict]:
    rows: list[dict] = []
    raw = zf.read(path).decode("utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            # Skip a malformed line rather than losing the whole table.
            continue
    return rows


def peek_header(data: bytes) -> dict:
    """Return the (unencrypted) header of a .wnkjba file without the passphrase."""
    header, _ = _read_header(data)
    return header
