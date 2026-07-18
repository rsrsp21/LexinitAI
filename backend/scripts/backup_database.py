"""Encrypted, BSON-fidelity MongoDB backup and restore verification.

The archive and its key must be stored separately in durable production storage.

Create and immediately verify a backup:
    uv run --project backend python -m backend.scripts.backup_database create

Verify an existing backup:
    uv run --project backend python -m backend.scripts.backup_database verify \
        --archive path.lexbackup --key-file path.lexbackup.key
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import struct
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import dns.resolver
from bson import BSON, decode_all, json_util
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pymongo import MongoClient

from backend.config import Config
from backend.db import database_name_from_uri


MAGIC = b"LEXINIT-BACKUP-V1\n"
CHUNK_SIZE = 1024 * 1024


def _configure_dns() -> None:
    if not (Config.MONGO_URI or "").startswith("mongodb+srv://") or not Config.MONGO_DNS_NAMESERVERS:
        return
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = list(Config.MONGO_DNS_NAMESERVERS)
    resolver.timeout = 3
    resolver.lifetime = 6
    dns.resolver.default_resolver = resolver


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _encrypt(source: Path, destination: Path, key: bytes) -> None:
    nonce = secrets.token_bytes(12)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    with source.open("rb") as src, destination.open("wb") as dst:
        dst.write(MAGIC)
        dst.write(nonce)
        for chunk in iter(lambda: src.read(CHUNK_SIZE), b""):
            dst.write(encryptor.update(chunk))
        encryptor.finalize()
        dst.write(encryptor.tag)


def _decrypt(source: Path, destination: Path, key: bytes) -> None:
    size = source.stat().st_size
    header_size = len(MAGIC) + 12
    if size <= header_size + 16:
        raise ValueError("Backup archive is truncated.")
    with source.open("rb") as src:
        if src.read(len(MAGIC)) != MAGIC:
            raise ValueError("Backup archive has an unsupported format.")
        nonce = src.read(12)
        src.seek(-16, os.SEEK_END)
        tag = src.read(16)
        ciphertext_size = size - header_size - 16
        src.seek(header_size)
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        remaining = ciphertext_size
        with destination.open("wb") as dst:
            while remaining:
                chunk = src.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise ValueError("Backup archive ended unexpectedly.")
                remaining -= len(chunk)
                dst.write(decryptor.update(chunk))
            decryptor.finalize()


def _write_plain_archive(db, destination: Path) -> dict:
    manifest = {
        "format": "lexinit-mongodb-bson-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": db.name,
        "collections": [],
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for collection_name in sorted(db.list_collection_names()):
            collection = db[collection_name]
            digest = hashlib.sha256()
            count = 0
            with archive.open(f"collections/{collection_name}.bson", "w") as bson_file:
                for document in collection.find({}):
                    encoded = BSON.encode(document)
                    bson_file.write(encoded)
                    digest.update(encoded)
                    count += 1
            indexes = list(collection.list_indexes())
            archive.writestr(
                f"indexes/{collection_name}.json",
                json_util.dumps(indexes, json_options=json_util.CANONICAL_JSON_OPTIONS),
            )
            manifest["collections"].append(
                {
                    "name": collection_name,
                    "documents": count,
                    "bson_sha256": digest.hexdigest(),
                    "indexes": len(indexes),
                }
            )
        manifest["total_documents"] = sum(item["documents"] for item in manifest["collections"])
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def _read_key(key_file: Path) -> bytes:
    key = base64.urlsafe_b64decode(key_file.read_bytes().strip())
    if len(key) != 32:
        raise ValueError("Backup key must decode to exactly 32 bytes.")
    return key


def _verify_plain_archive(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as archive:
        bad_file = archive.testzip()
        if bad_file:
            raise ValueError(f"Corrupt file in backup: {bad_file}")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != "lexinit-mongodb-bson-v1":
            raise ValueError("Unsupported manifest format.")

        decoded = {}
        for entry in manifest["collections"]:
            raw = archive.read(f"collections/{entry['name']}.bson")
            if hashlib.sha256(raw).hexdigest() != entry["bson_sha256"]:
                raise ValueError(f"BSON checksum mismatch for {entry['name']}.")
            documents = decode_all(raw)
            if len(documents) != entry["documents"]:
                raise ValueError(f"Document count mismatch for {entry['name']}.")
            decoded[entry["name"]] = documents

        if sum(len(documents) for documents in decoded.values()) != manifest["total_documents"]:
            raise ValueError("Total document count mismatch.")

    return manifest


def verify_backup(archive_path: Path, key_file: Path) -> dict:
    archive_path = archive_path.resolve()
    expected_checksum_path = Path(f"{archive_path}.sha256")
    if expected_checksum_path.exists():
        expected = expected_checksum_path.read_text(encoding="ascii").strip().split()[0]
        actual = _sha256(archive_path)
        if not secrets.compare_digest(expected, actual):
            raise ValueError("Encrypted archive checksum mismatch.")
    key = _read_key(key_file.resolve())
    with tempfile.TemporaryDirectory(prefix="lexinit-verify-") as temp_dir:
        plain_path = Path(temp_dir) / "backup.zip"
        _decrypt(archive_path, plain_path, key)
        return _verify_plain_archive(plain_path)


def create_backup(output_dir: Path) -> tuple[Path, Path, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = output_dir / f"lexinit-{timestamp}.lexbackup"
    key_path = output_dir / f"lexinit-{timestamp}.lexbackup.key"
    if archive_path.exists() or key_path.exists():
        raise FileExistsError("A backup with this timestamp already exists.")

    key = secrets.token_bytes(32)
    with tempfile.TemporaryDirectory(prefix="lexinit-backup-") as temp_dir:
        plain_path = Path(temp_dir) / "backup.zip"
        if not Config.MONGO_URI:
            raise RuntimeError("MONGO_URI is not configured.")
        _configure_dns()
        client = MongoClient(Config.MONGO_URI, connect=False)
        try:
            database_name = Config.MONGO_DB_NAME or database_name_from_uri(Config.MONGO_URI) or "lexinit"
            manifest = _write_plain_archive(client[database_name], plain_path)
        finally:
            client.close()
        _encrypt(plain_path, archive_path, key)

    key_path.write_bytes(base64.urlsafe_b64encode(key) + b"\n")
    os.chmod(key_path, 0o600)
    checksum = _sha256(archive_path)
    Path(f"{archive_path}.sha256").write_text(f"{checksum}  {archive_path.name}\n", encoding="ascii")
    try:
        verified = verify_backup(archive_path, key_path)
    except Exception:
        archive_path.unlink(missing_ok=True)
        key_path.unlink(missing_ok=True)
        Path(f"{archive_path}.sha256").unlink(missing_ok=True)
        raise
    if verified["total_documents"] != manifest["total_documents"]:
        raise ValueError("Verified manifest does not match source manifest.")
    return archive_path, key_path, manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "backups",
    )
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--archive", type=Path, required=True)
    verify_parser.add_argument("--key-file", type=Path, required=True)
    verify_parser.add_argument(
        "--compare-live",
        action="store_true",
        help="Compare every backed-up collection count with the configured live database.",
    )
    args = parser.parse_args()

    if args.command == "create":
        archive_path, key_path, manifest = create_backup(args.output_dir)
        print(
            json.dumps(
                {
                    "status": "created_and_restore_verified",
                    "archive": str(archive_path.resolve()),
                    "key_file": str(key_path.resolve()),
                    "collections": len(manifest["collections"]),
                    "documents": manifest["total_documents"],
                },
                indent=2,
            )
        )
    else:
        manifest = verify_backup(args.archive, args.key_file)
        live_comparison = None
        if args.compare_live:
            if not Config.MONGO_URI:
                raise RuntimeError("MONGO_URI is not configured.")
            _configure_dns()
            client = MongoClient(Config.MONGO_URI, connect=False)
            try:
                database_name = Config.MONGO_DB_NAME or database_name_from_uri(Config.MONGO_URI) or "lexinit"
                db = client[database_name]
                differences = []
                for entry in manifest["collections"]:
                    live_count = db[entry["name"]].count_documents({})
                    if live_count != entry["documents"]:
                        differences.append(
                            {
                                "collection": entry["name"],
                                "backup": entry["documents"],
                                "live": live_count,
                            }
                        )
                live_comparison = {
                    "status": "matched" if not differences else "different",
                    "differences": differences,
                }
            finally:
                client.close()
        print(
            json.dumps(
                {
                    "status": "restore_verified",
                    "collections": len(manifest["collections"]),
                    "documents": manifest["total_documents"],
                    "created_at": manifest["created_at"],
                    "live_comparison": live_comparison,
                },
                indent=2,
            )
        )
        if live_comparison and live_comparison["differences"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
