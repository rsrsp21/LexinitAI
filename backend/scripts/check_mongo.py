from __future__ import annotations

import os
import socket
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import dns.resolver
from dotenv import load_dotenv
from pymongo import MongoClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env", override=True)


def mask_uri(uri: str) -> str:
    parsed = urlsplit(uri)
    if "@" not in parsed.netloc:
        return uri

    credentials, hosts = parsed.netloc.rsplit("@", 1)
    if ":" in credentials:
        username, _password = credentials.split(":", 1)
        credentials = f"{username}:***"
    else:
        credentials = "***"

    return parsed._replace(netloc=f"{credentials}@{hosts}").geturl()


def resolver() -> dns.resolver.Resolver:
    nameservers = [
        item.strip()
        for item in os.environ.get("MONGO_DNS_NAMESERVERS", "").split(",")
        if item.strip()
    ]
    if not nameservers:
        return dns.resolver.get_default_resolver()

    custom_resolver = dns.resolver.Resolver(configure=False)
    custom_resolver.nameservers = nameservers
    custom_resolver.timeout = 3
    custom_resolver.lifetime = 6
    dns.resolver.default_resolver = custom_resolver
    return custom_resolver


def tcp_check(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=6):
            return True
    except OSError as exc:
        print(f"  TCP {host}:{port} failed: {exc}")
        return False


def env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def selected_mongo_uri() -> str:
    if env_bool("USE_LOCAL_MONGO"):
        return os.environ.get("LOCAL_MONGO_URI", "mongodb://localhost:27017/lexinit").strip()
    return os.environ.get("MONGO_URI", "").strip()


def srv_hosts(uri: str) -> list[tuple[str, int]]:
    parsed = urlsplit(uri)
    hostname = parsed.hostname
    if not hostname:
        raise RuntimeError("MONGO_URI has no hostname.")

    if not uri.startswith("mongodb+srv://"):
        port = parsed.port or 27017
        return [(hostname, port)]

    query_name = f"_mongodb._tcp.{hostname}"
    print(f"Checking SRV: {query_name}")
    answers = resolver().resolve(query_name, "SRV")
    hosts = []
    for answer in answers:
        target = str(answer.target).rstrip(".")
        hosts.append((target, int(answer.port)))
    return hosts


def print_uri_summary(uri: str) -> None:
    parsed = urlsplit(uri)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    print(f"URI: {mask_uri(uri)}")
    print(f"Scheme: {parsed.scheme}")
    print(f"Using local Mongo: {env_bool('USE_LOCAL_MONGO')}")
    print(f"Host: {parsed.hostname}")
    print(f"Database from path: {parsed.path.strip('/') or '(none)'}")
    print(f"MONGO_DB_NAME: {os.environ.get('MONGO_DB_NAME') or '(not set)'}")
    print(f"MONGO_DNS_NAMESERVERS: {os.environ.get('MONGO_DNS_NAMESERVERS') or '(system default)'}")
    if query:
        print("Options:")
        for key, value in sorted(query.items()):
            print(f"  {key}={value}")


def main() -> int:
    uri = selected_mongo_uri()
    if not uri:
        print("Mongo URI is missing in backend/.env")
        return 1

    print_uri_summary(uri)
    print()

    try:
        hosts = srv_hosts(uri)
    except Exception as exc:
        print(f"DNS/SRV failed: {type(exc).__name__}: {exc}")
        return 1

    print("Resolved MongoDB hosts:")
    for host, port in hosts:
        print(f"  {host}:{port}")

    print()
    print("Checking TCP:")
    tcp_ok = all(tcp_check(host, port) for host, port in hosts)
    if tcp_ok:
        print("  TCP is reachable for all resolved hosts.")
    else:
        print("  At least one MongoDB host is not reachable.")

    print()
    print("Checking MongoDB ping:")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
    except Exception as exc:
        print(f"  Ping failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        try:
            client.close()
        except Exception:
            pass

    print("  Connected successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
