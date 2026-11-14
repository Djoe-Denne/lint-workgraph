#!/usr/bin/env python3
"""Collect explicit, read-only MCP evidence; never infer mandatory edits."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
import ipaddress
import hashlib
import json
import math
import importlib.util
import os
import re
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import tomllib
from urllib.parse import urlsplit, urlunsplit
from clippy_source_ranges import verify_function_range
import clippy_source_ranges as source_ranges

DEFAULT_URL = "http://127.0.0.1:3062/mcp?tags=rust-code-mcp"
TOOL_ROOT = Path(__file__).resolve().parents[2]
MAX_PAGES = 32
MAX_TOOLS = 2048
MAX_REQUESTS = 32
MAX_INPUT_BYTES = 131072
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_LIMIT = 200
MAX_OFFSET = 100000
ORIGIN_TARGET = "apparatus_contracts::runtime::validate_runtime_uid"
ORIGIN_NAME = "validate_runtime_uid"
ORIGIN_SOURCE = "crates/apparatus-contracts/src/runtime.rs"
ORIGIN_MANIFEST = "crates/apparatus-contracts/Cargo.toml"
ORIGIN_MODULE = "crates/apparatus-contracts/src/lib.rs"
SELECTORS = {
    "who_uses": {"target"},
    "who_uses_summary": {"target"},
    "who_calls": {"target"},
    "calls_from": {"caller"},
    "function_signature": {"target"},
    "who_imports": {"target"},
    "get_declared_reexports": {"module"},
    "get_exports": {"module", "consumer"},
    "workspace_stats": set(),
}
PAGED = set(SELECTORS) - {"function_signature", "workspace_stats"}


class EvidenceError(Exception):
    """An input, protocol, or evidence failure."""


def validate_url(value):
    """Accept literal loopback HTTP(S) only, without credentials or fragments."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if (parsed.scheme not in {"http", "https"} or not host
                or parsed.username is not None or parsed.password is not None
                or "#" in value or any(c.isspace() for c in value)):
            raise ValueError()
        # Normalize localhost without relying on ambient DNS configuration.
        host = "127.0.0.1" if host == "localhost" else host
        if "%" in host or not ipaddress.ip_address(host).is_loopback:
            raise ValueError()
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        return urlunsplit((parsed.scheme, authority, parsed.path, parsed.query, ""))
    except (ValueError, TypeError):
        raise EvidenceError("URL must be loopback HTTP(S), without credentials or fragment") from None


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_manifest(path, root):
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise EvidenceError("Manifest exceeds 128 KiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=strict_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              EvidenceError("Non-finite JSON number")))
    except (UnicodeError, json.JSONDecodeError):
        raise EvidenceError("Manifest must be strict UTF-8 JSON") from None
    return validate_manifest(data, root)


def same_root(value, root):
    if not isinstance(value, str) or not Path(value).is_absolute():
        return False
    return Path(value).resolve() == root.resolve()


def validate_manifest(data, root):
    if not isinstance(data, dict) or set(data) != {"workspace", "requests"}:
        raise EvidenceError("Manifest requires exactly workspace and requests")
    if not same_root(data["workspace"], root):
        raise EvidenceError("Manifest workspace must equal the collector repository root")
    requests = data["requests"]
    if not isinstance(requests, list) or not 1 <= len(requests) <= MAX_REQUESTS:
        raise EvidenceError("Manifest requires 1..32 requests")
    seen = set()
    validated = []
    for item in requests:
        if not isinstance(item, dict) or set(item) != {"id", "tool", "arguments"}:
            raise EvidenceError("Each request requires exactly id, tool, arguments")
        identity, tool, args = item["id"], item["tool"], item["arguments"]
        if (not isinstance(identity, str) or not identity or len(identity) > 128
                or identity in seen):
            raise EvidenceError("Request IDs must be unique nonempty strings (max 128)")
        seen.add(identity)
        if not isinstance(tool, str) or tool not in SELECTORS:
            raise EvidenceError("Tool is not in the curated semantic read-only allowlist")
        if not isinstance(args, dict):
            raise EvidenceError("arguments must be an object")
        required = SELECTORS[tool] | {"directory"}
        allowed = required | ({"limit", "offset", "summary"} if tool in PAGED else set())
        if not required <= set(args) or not set(args) <= allowed:
            raise EvidenceError(f"Unsupported or missing arguments for {tool}")
        if not same_root(args["directory"], root):
            raise EvidenceError("Every directory must equal the explicit workspace")
        # No path arguments are currently allowed. Selectors are qualified names,
        # never file paths, URLs, globs, or server configuration.
        for key in SELECTORS[tool]:
            value = args[key]
            if (not isinstance(value, str) or not value or len(value) > 1024
                    or any(c in value for c in "/\\\x00\r\n") or ".." in value
                    or "://" in value):
                raise EvidenceError(f"{key} must be a qualified symbol/module, not a path")
        prepared = dict(args, directory=str(root.resolve()))
        if tool in PAGED:
            prepared.setdefault("limit", 50)
            prepared.setdefault("offset", 0)
            for key, low, high in (("limit", 1, MAX_LIMIT), ("offset", 0, MAX_OFFSET)):
                if type(prepared[key]) is not int or not low <= prepared[key] <= high:
                    raise EvidenceError(f"{key} outside allowed bounds {low}..{high}")
            if "summary" in prepared and type(prepared["summary"]) is not bool:
                raise EvidenceError("summary must be boolean")
        validated.append(dict(item, arguments=prepared))
    return {"workspace": str(root.resolve()), "requests": validated}


def as_json(value):
    return value.model_dump(mode="json", by_alias=True, exclude_none=False)


async def catalog(session):
    """Follow MCP cursor pagination, detecting loops and finite budget exhaustion."""
    tools, seen, cursor = [], set(), None
    for _ in range(MAX_PAGES):
        page = await session.list_tools(cursor=cursor)
        tools.extend(as_json(tool) for tool in page.tools)
        if len(tools) > MAX_TOOLS:
            raise EvidenceError("Catalogue tool budget exceeded")
        cursor = page.nextCursor
        if cursor is None:
            return tools
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            raise EvidenceError("Invalid or repeated catalogue cursor")
        seen.add(cursor)
    raise EvidenceError("Catalogue page budget exceeded")


def resolve_requests(requests, tools):
    """Preflight every request before executing any semantic tool."""
    resolved = []
    for request in requests:
        suffix = "_1mcp_" + request["tool"]
        matches = [tool for tool in tools if isinstance(tool.get("name"), str)
                   and tool["name"].endswith(suffix)]
        if len(matches) != 1:
            raise EvidenceError(f"Unknown or ambiguous tool suffix: {request['tool']}")
        tool = matches[0]
        # Restrict the namespace as well as the suffix. An unrelated advertised
        # tool with a readOnly annotation is not authority to execute it.
        if tool["name"] != "rust-code-mcp" + suffix:
            raise EvidenceError("Resolved tool is outside the rust-code-mcp namespace")
        schema = tool.get("inputSchema", {})
        properties = schema.get("properties", {})
        args = request["arguments"]
        if (not set(args) <= set(properties)
                or not set(schema.get("required", [])) <= set(args)):
            raise EvidenceError("Advertised tool arguments drifted; inspect catalogue")
        resolved.append(dict(request, exact_tool=tool["name"]))
    return resolved


def payloads(raw):
    """Yield structured and JSON-text payloads, without executing their content."""
    structured = raw.get("structuredContent")
    if structured is not None:
        yield structured
    for block in raw.get("content", []):
        if block.get("type") == "text":
            text = block.get("text", "")
            try:
                yield json.loads(text)
            except (json.JSONDecodeError, TypeError):
                if isinstance(text, str) and text.lstrip().lower().startswith(
                        ("error:", "failed:", "permission denied")):
                    yield {"error": text}


def result_failed(raw):
    if raw.get("isError") is True:
        return True
    for payload in payloads(raw):
        if isinstance(payload, dict):
            if (payload.get("isError") is True or payload.get("success") is False
                    or payload.get("status") in ("error", "failed")
                    or bool(payload.get("error"))):
                return True
    return False


async def collect(session, requests, evidence):
    records = []
    for request in requests:
        record = {
            **request, "server": evidence["server"],
            "workspace": evidence["workspace"], "status": "not_executed",
            "coverage": "unknown; server index/features/macros/dynamic dispatch/tests not verified",
            "pagination": {
                "status": "unknown",
                "reason": "Semantic result envelope not verified; one bounded page only",
            },
        }
        evidence["requests"].append(record)
        records.append(record)
    for request, record in zip(requests, records):
        record["status"] = "pending"
        try:
            result = await session.call_tool(request["exact_tool"],
                                             arguments=request["arguments"])
            raw = as_json(result)
            if len(json.dumps(raw).encode("utf-8")) > MAX_RESULT_BYTES:
                raise EvidenceError("Tool result exceeds 8 MiB evidence budget")
            record["result"] = raw
            record["status"] = "tool_error" if result_failed(raw) else "received"
            if record["status"] == "tool_error":
                raise EvidenceError(f"Tool reported failure for request {request['id']}")
        except BaseException as exc:
            if record["status"] == "pending":
                record["status"] = "timeout" if isinstance(
                    exc, (TimeoutError, asyncio.CancelledError)) else "transport_error"
            raise


def load_sdk():
    try:
        if version("mcp") != "1.21.1":
            raise EvidenceError("Requires mcp==1.21.1; use the dedicated requirements file")
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        import httpx
    except (ImportError, PackageNotFoundError):
        raise EvidenceError(
            "Missing dependency: install requirements-mcp-code-evidence.txt in a dedicated venv"
        ) from None
    return ClientSession, streamablehttp_client, httpx


@asynccontextmanager
async def connect(url, timeout):
    ClientSession, streamablehttp_client, httpx = load_sdk()

    async def guard(request):
        validate_url(str(request.url))

    def factory(headers=None, timeout=None, auth=None):
        return httpx.AsyncClient(
            headers=headers, timeout=timeout, auth=auth, trust_env=False,
            follow_redirects=False, event_hooks={"request": [guard]},
        )

    async with streamablehttp_client(
        url, timeout=timeout, sse_read_timeout=timeout,
        terminate_on_close=True, httpx_client_factory=factory,
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            yield session


async def run(args, manifest, evidence):
    # One finite deadline includes connection, initialization, catalogue,
    # sequential requests and ordinary session cleanup. No retries.
    async with asyncio.timeout(args.timeout):
        async with connect(args.url, args.timeout) as session:
            initialized = await session.initialize()
            evidence["server"] = as_json(initialized.serverInfo)
            tools = await catalog(session)
            if args.command == "catalog":
                evidence.update(tools=tools, pagination={"status": "complete",
                                "scope": "advertised catalogue only"})
            else:
                resolved = resolve_requests(manifest["requests"], tools)
                await collect(session, resolved, evidence)
    evidence["status"] = "received"


def output_path(value, protected):
    if value is None:
        return None
    path = Path(value).resolve()
    if path in protected or path.suffix.lower() != ".json":
        raise EvidenceError("Output/report must be a .json file distinct from every input")
    return path


def atomic_json(path, data):
    """Replace only after complete serialization and successful flush."""
    text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, prefix=".mcp-evidence-",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_json(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise EvidenceError("Producer input exceeds 64 MiB")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          EvidenceError("Non-finite JSON number")))


class SourcePathError(EvidenceError):
    def __init__(self, message, status="unknown"):
        super().__init__(message)
        self.status = status


def source_path(root, raw):
    """Normalize repeated separators, but never dot, case, or symlink aliases."""
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise SourcePathError("Invalid source path")
    spelling = raw.replace("\\", "/")
    if spelling.startswith("//"):
        raise SourcePathError("UNC/device source paths are unresolved", "outside_root")
    spelling = re.sub("/+", "/", spelling)
    if spelling.startswith(("//", "/")) or re.match(r"^[A-Za-z]:", spelling):
        prefix = str(root).replace("\\", "/").rstrip("/") + "/"
        if not spelling.startswith(prefix):
            raise SourcePathError("Source outside workspace", "outside_root")
        spelling = spelling[len(prefix):]
    parts = re.split("/+", spelling)
    if any(part in ("", ".", "..") or part.endswith((".", " ")) or ":" in part
           for part in parts):
        raise SourcePathError("Dot/device/path aliases are unresolved", "ambiguous")
    path = root.joinpath(*parts)
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise SourcePathError("Source outside root", "outside_root")
    if resolved != path.absolute():
        raise SourcePathError("Symlink source alias", "ambiguous")
    # Windows Path equality folds case; inspect actual directory spellings too.
    parent = root
    for part in parts:
        names = [p.name for p in parent.iterdir() if p.name.casefold() == part.casefold()]
        if not names:
            raise SourcePathError("Missing source")
        if names != [part]:
            raise SourcePathError("Case source alias", "ambiguous")
        parent = parent / part
    if not path.is_file():
        raise SourcePathError("Source is not a file")
    return "/".join(parts), path


def validate_workspace(value):
    """CLI authority only: an absolute, existing Git top-level with a full HEAD."""
    path = Path(value)
    if not path.is_absolute():
        raise EvidenceError("--workspace must be an explicit absolute Git top-level")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise EvidenceError("Workspace is not a directory")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False, timeout=10)
    if result.returncode or Path(result.stdout.strip()).resolve() != root:
        raise EvidenceError("--workspace must select the target Git top-level, not a subdirectory")
    git_head(root)
    return root


def git_head(root):
    """Read Git metadata without invoking Git, a shell, or OpenCode."""
    git = root / ".git"
    if git.is_file():
        text = git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir: "):
            raise EvidenceError("Unsupported Git metadata")
        git = (root / text[8:]).resolve()
    value = (git / "HEAD").read_text(encoding="ascii").strip()
    if value.startswith("ref: "):
        ref = value[5:]
        if not re.fullmatch(r"refs/[A-Za-z0-9_./-]+", ref) or ".." in ref:
            raise EvidenceError("Invalid Git ref")
        common = git
        if (git / "commondir").exists():
            common = (git / (git / "commondir").read_text().strip()).resolve()
        if (common / ref).exists():
            value = (common / ref).read_text().strip()
        else:
            matches = [line.split()[0] for line in (common / "packed-refs").read_text().splitlines()
                       if line.endswith(" " + ref)]
            value = matches[0] if len(matches) == 1 else ""
    if not re.fullmatch("[0-9a-f]{40}", value):
        raise EvidenceError("Cannot establish full workspace HEAD")
    return value


def decode_wire(raw, serena=False):
    """Decode only verified MCP envelopes; disagreeing dual payloads fail closed."""
    if result_failed(raw):
        raise EvidenceError("Tool error envelope")
    candidates = []
    if raw.get("structuredContent") is not None:
        value = raw["structuredContent"]
        if serena and isinstance(value, dict) and set(value) == {"result"}:
            value = value["result"]
        candidates.append(value)
    for block in raw.get("content", []):
        if block.get("type") != "text":
            raise EvidenceError("Unsupported non-text tool payload")
        candidates.append(block.get("text"))
    decoded = []
    for value in candidates:
        if isinstance(value, str):
            try:
                value = json.loads(value, object_pairs_hook=strict_object)
            except json.JSONDecodeError:
                if not serena:
                    raise EvidenceError("Unsupported non-JSON HIR payload") from None
        decoded.append(value)
    if not decoded or any(value != decoded[0] for value in decoded[1:]):
        raise EvidenceError("Missing or conflicting tool payloads")
    return decoded[0]


def coverage():
    return {key: "unknown" for key in ("private", "macros", "traits", "features", "tests", "freshness")}


def definition_text(raw):
    """The verified definition tool returns one plain TextContent, not JSON."""
    if (result_failed(raw) or raw.get("structuredContent") is not None
            or len(raw.get("content", [])) != 1
            or raw["content"][0].get("type") != "text"
            or not isinstance(raw["content"][0].get("text"), str)):
        raise EvidenceError("Unsupported definition text envelope")
    return raw["content"][0]["text"]


class ProducerCapture:
    """One bounded, sequential capture; raw artifacts survive partial queries."""

    def __init__(self, session, tools, directory, budget, workspace):
        self.session, self.tools, self.directory = session, tools, directory
        self.workspace = workspace.resolve()
        self.remaining = budget
        self.queries = []
        self.next_id = 0

    async def query(self, namespace, suffix, arguments, serena=False):
        exact = f"{namespace}_1mcp_{suffix}"
        matches = [tool for tool in self.tools if tool.get("name", "").endswith("_1mcp_" + suffix)]
        if len(matches) != 1 or matches[0]["name"] != exact:
            raise EvidenceError("Unknown or ambiguous curated producer tool")
        allowed = {
            ("rust-code-mcp", "who_uses"), ("serena", "initial_instructions"),
            ("serena", "get_current_config"), ("serena", "get_symbols_overview"),
            ("serena", "find_symbol"),
            ("rust-code-mcp", "function_signature"), ("rust-code-mcp", "find_definition"),
        }
        if (namespace, suffix) not in allowed:
            raise EvidenceError("Producer tool is not curated")
        if namespace == "rust-code-mcp" and (
                not isinstance(arguments.get("directory"), str)
                or not Path(arguments["directory"]).is_absolute()
                or Path(arguments["directory"]).resolve() != self.workspace):
            raise EvidenceError("Producer directory must equal the selected workspace")
        if suffix == "find_symbol" and not arguments.get("name_path_pattern"):
            raise EvidenceError("Empty symbol patterns are forbidden")
        if suffix in ("find_definition", "function_signature"):
            fixed = ({"symbol_name": ORIGIN_NAME, "exact": True} if suffix == "find_definition"
                     else {"target": ORIGIN_TARGET})
            if (set(arguments) != set(fixed) | {"directory"}
                    or any(arguments.get(key) != value for key, value in fixed.items())
                    or (suffix == "find_definition" and arguments.get("exact") is not True)
                    or not isinstance(arguments.get("directory"), str)
                    or Path(arguments["directory"]).resolve() != self.workspace):
                raise EvidenceError("Origin lookup requires the fixed literal target/exact canonical root")
        schema = matches[0].get("inputSchema", {})
        if (not set(arguments) <= set(schema.get("properties", {}))
                or not set(schema.get("required", [])) <= set(arguments)):
            raise EvidenceError("Producer tool schema drift")
        if self.remaining <= 0:
            raise EvidenceError("Producer query budget exhausted")
        self.remaining -= 1
        self.next_id += 1
        identity = f"q{self.next_id:06d}"
        artifact = self.directory / (identity + ".json")
        query = {"id": identity, "tool": exact, "arguments": arguments,
                 "artifact": str(artifact), "artifact_sha256": None, "status": "error",
                 "pagination": {"status": "unknown", "pages": 1, "returned": 0,
                                "total": None, "reason": "Unverified result envelope"},
                 "coverage": coverage()}
        self.queries.append(query)
        try:
            raw = as_json(await self.session.call_tool(exact, arguments=arguments))
            if len(json.dumps(raw).encode()) > MAX_RESULT_BYTES:
                raise EvidenceError("Producer result exceeds evidence budget")
            atomic_json(artifact, raw)
            query["artifact_sha256"] = sha256(artifact)
            value = definition_text(raw) if suffix == "find_definition" else decode_wire(raw, serena)
            query["status"] = "ok"
            return value, query
        except Exception as exc:
            if not artifact.exists():
                atomic_json(artifact, {"failure": type(exc).__name__})
                query["artifact_sha256"] = sha256(artifact)
            raise


async def paged_who_uses(capture, workspace, target, limit=50, max_pages=8):
    """Only who_uses has a verified semantic page contract."""
    if not isinstance(target, str) or not target.strip() or any(c in target for c in "/\\\r\n"):
        raise EvidenceError("who_uses requires a nonempty qualified target")
    offset, total, rows, seen, queries = 0, None, [], set(), []
    reason, state = "Page budget exhausted", "partial"
    for _ in range(max_pages):
        try:
            data, query = await capture.query("rust-code-mcp", "who_uses", {
                "directory": str(workspace), "target": target,
                "offset": offset, "limit": limit, "summary": False})
            queries.append(query)
            if not isinstance(data, dict) or not isinstance(data.get("usages"), list):
                query["status"] = "unsupported"
                raise EvidenceError("Unsupported who_uses envelope")
            count, current_total = data.get("returned_match_count"), data.get("total_match_count")
            if (type(count) is not int or type(current_total) is not int or count < 0
                    or current_total < 0 or type(data.get("offset")) is not int
                    or type(data.get("limit")) is not int or data.get("offset") != offset
                    or data.get("limit") != limit or data.get("summary") is not False
                    or data.get("target") != target or count != len(data["usages"])
                    or count > limit or offset + count > current_total
                    or (total is not None and total != current_total)):
                raise EvidenceError("Inconsistent/gapped who_uses pagination")
            total = current_total
            identities = []
            for row in data["usages"]:
                if not isinstance(row, dict) or not all(
                        key in row for key in ("file", "start", "end", "category",
                                               "consumer_module")):
                    query["status"] = "unsupported"
                    raise EvidenceError("Unsupported who_uses usage")
                if (not all(isinstance(row[key], str) and row[key] for key in
                            ("file", "category", "consumer_module"))
                        or type(row["start"]) is not int or type(row["end"]) is not int
                        or not 0 <= row["start"] <= row["end"]
                        or ("consumer_function" in row and (
                            not isinstance(row["consumer_function"], str) or not row["consumer_function"]))):
                    query["status"] = "unsupported"
                    raise EvidenceError("Unsupported who_uses usage")
                identity = json.dumps(dict(row, file=re.sub(
                    "/+", "/", str(row["file"]).replace("\\", "/"))), sort_keys=True)
                if identity in seen or identity in identities:
                    raise EvidenceError("Repeated/duplicate who_uses page identity")
                identities.append(identity)
            if count == 0 and offset != total:
                raise EvidenceError("Non-progress/truncated who_uses page")
            seen.update(identities)
            rows.extend(data["usages"])
            offset += count
            if offset == total:
                state, reason = "complete", "Verified indexed-scope count sequence only"
                break
        except EvidenceError as exc:
            reason = str(exc)
            state = "partial" if rows else "unknown"
            if queries and queries[-1]["status"] == "ok":
                queries[-1]["status"] = "error"
            break
    pagination = {"status": state, "pages": len(queries), "returned": len(rows),
                  "total": total, "reason": reason}
    for query in queries:
        query["pagination"] = dict(pagination)
        if state != "complete" and query["status"] == "ok":
            query["status"] = "partial"
    return rows, queries, pagination


def source_lines(text):
    # Rust/source protocol lines advance on LF, not Unicode NEL/LS/PS.
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def offset_in_source(text, line, column, unit):
    """Validate and convert explicit native columns to Unicode scalar offsets."""
    lines = source_lines(text)
    if type(line) is not int or type(column) is not int or line < 1 or column < 0:
        raise EvidenceError("Invalid source coordinates")
    if line == len(lines) + 1 and column == 0 and (not text or text.endswith("\n")):
        return len(text)
    if line > len(lines):
        raise EvidenceError("Coordinate outside source")
    content = lines[line - 1].rstrip("\r\n")
    if unit == "unicode_scalar":
        prefix = content[:column]
        if column > len(content):
            raise EvidenceError("Column outside source")
    elif unit in ("utf8_byte", "utf16"):
        encoding = "utf-8" if unit == "utf8_byte" else "utf-16-le"
        width = column if unit == "utf8_byte" else column * 2
        data = content.encode(encoding)
        if width > len(data):
            raise EvidenceError("Column outside source")
        try:
            prefix = data[:width].decode(encoding)
        except UnicodeDecodeError:
            raise EvidenceError("Column splits a Unicode character") from None
    else:
        raise EvidenceError("Unknown column unit")
    return sum(map(len, lines[:line - 1])) + len(prefix)


def serena_extent(symbol, text):
    """Conservative whole-line extent for source-crosschecked simple functions."""
    location = symbol.get("body_location", {})
    start, end = location.get("start_line"), location.get("end_line")
    lines = source_lines(text)
    if (symbol.get("kind") != "Function" or type(start) is not int or type(end) is not int
            or not 0 <= start <= end < len(lines)):
        raise EvidenceError("Unsupported symbol body range/kind")
    body = "".join(lines[start:end + 1])
    name = symbol.get("name_path", "").split("/")[-1]
    # Fail closed for macro expansion, nested declarations and syntax requiring
    # a full Rust parser. Whole-line endpoints must independently match source.
    declaration = re.search(
        r"(?m)^[ \t]*(?:(?:pub(?:\([^)\n]*\))?|async|unsafe)\s+)*fn\s+"
        + re.escape(name) + r"\s*(?:<|\()", body)
    if not declaration or not lines[end].strip().startswith("}") or lines[end].strip() != "}":
        raise EvidenceError("Unverified inclusive body endpoint")
    prefix = body[:declaration.start()]
    if any(line.strip() and not line.lstrip().startswith("///") for line in prefix.split("\n")):
        raise EvidenceError("Unverified documentation/attribute boundary")
    tail = body[declaration.end():]
    if re.search(r"\b(?:fn|struct|enum|impl|mod|trait|const|static|type|union|use|extern)\b"
                 r"|\w+\s*!|['\"#|]|//|/\*|\*/", tail):
        raise EvidenceError("Macro/nested/string syntax requires richer source verification")
    if tail.count("{") != tail.count("}") or "{" not in tail:
        raise EvidenceError("Unverified function extent")
    has_newline = lines[end].endswith("\n")
    return {"start_line": start + 1, "start_column": 0,
            "end_line": end + 2 if has_newline else end + 1,
            "end_column": 0 if has_newline else len(lines[end]),
            "column_unit": "unicode_scalar"}


def diagnostic_rows(inventory):
    if (not isinstance(inventory, dict) or type(inventory.get("schema_version")) is not int
            or inventory["schema_version"] != 1):
        raise EvidenceError("Expected overlap inventory schema_version 1")
    for namespace in ("clippy", "sonar"):
        records = inventory.get(namespace)
        if not isinstance(records, list):
            raise EvidenceError("Inventory requires explicit clippy and sonar arrays")
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise EvidenceError("Invalid inventory diagnostic identity")
            spans = record.get("primary_spans", []) if namespace == "clippy" else [
                {"file": record.get("file"), "range": record.get("range")}]
            yield namespace + ":" + record["id"], namespace, spans


def map_diagnostics(inventory, workspace, sources, symbols, refs, bound, contexts=None):
    mappings = []
    seen = set()
    for key, namespace, spans in diagnostic_rows(inventory):
        if key in seen:
            raise EvidenceError("Duplicate inventory diagnostic ID")
        seen.add(key)
        mapping = {"diagnostic_key": key, "status": "unknown", "symbols": [],
                   "evidence_refs": [], "reasons": []}
        mappings.append(mapping)
        if len(spans) != 1 or not spans[0].get("range"):
            mapping["reasons"].append("Missing or multi-primary range")
            continue
        try:
            path, _ = source_path(workspace, spans[0]["file"])
        except EvidenceError as exc:
            mapping.update(status=getattr(exc, "status", "unknown"), reasons=[str(exc)])
            continue
        if path not in sources:
            mapping["reasons"].append("Source not captured before queries")
            continue
        text = sources[path]["text"]
        context = (contexts or {}).get(key)
        unit = "unicode_scalar" if namespace == "clippy" else None
        if context and context["data"].get("source_sha256") == sources[path]["sha256"]:
            mapping["evidence_refs"].append(context["reference"])
            if namespace == "sonar":
                unit = context["data"].get("inventory_column_unit")
        if unit not in ("unicode_scalar", "utf8_byte", "utf16"):
            mapping["reasons"].append("Sonar native column convention not independently verified")
            continue
        try:
            line, col, end_line, end_col = spans[0]["range"]
            begin = offset_in_source(text, line, col, unit)
            end = offset_in_source(text, end_line, end_col, unit)
            if end <= begin:
                raise EvidenceError("Empty or reversed diagnostic range")
        except (EvidenceError, ValueError, TypeError) as exc:
            mapping["reasons"].append("Unverified diagnostic coordinates: " + str(exc))
            continue
        candidates = []
        local_ambiguous = False
        for symbol in symbols:
            if symbol["path"] != path:
                continue
            r = symbol["range"]
            a = offset_in_source(text, r["start_line"], r["start_column"], r["column_unit"])
            b = offset_in_source(text, r["end_line"], r["end_column"], r["column_unit"])
            if a <= begin < b and begin <= end <= b:
                if "range_witnesses" in sources[path]:
                    checked = verify_function_range(text, symbol, spans[0]["range"], unit,
                                                    sources[path]["range_witnesses"])
                    if checked["status"] != "verified":
                        local_ambiguous |= checked["status"] == "ambiguous"
                        mapping["reasons"].extend(checked["reasons"])
                        continue
                candidates.append(symbol)
        mapping["symbols"] = candidates
        mapping["evidence_refs"] = sorted({ref for s in candidates for ref in refs[s["id"]]}) + mapping["evidence_refs"]
        if path not in bound:
            mapping.update(status="stale", reasons=["Historical inventory source equivalence not proven"])
        elif len(candidates) == 1:
            mapping.update(status="exact", reasons=["Unique source-crosschecked simple function extent"])
        elif candidates:
            mapping.update(status="ambiguous", reasons=["Overlapping enclosing symbols"])
        elif local_ambiguous:
            mapping["status"] = "ambiguous"
        else:
            mapping["reasons"].append("No supported verified enclosing symbol")
    return mappings


def capture_sources(workspace, paths, budget):
    sources = {}
    total_bytes = 0
    for raw in paths:
        path, absolute = source_path(workspace, raw)
        if path in sources:
            raise EvidenceError("Duplicate/aliased source path")
        if len(sources) >= budget or absolute.stat().st_size > MAX_RESULT_BYTES:
            raise EvidenceError("Source capture budget exceeded")
        data = absolute.read_bytes()
        total_bytes += len(data)
        if total_bytes > MAX_SOURCE_BYTES:
            raise EvidenceError("Aggregate source capture exceeds 128 MiB")
        sources[path] = {"sha256": hashlib.sha256(data).hexdigest(),
                         "text": data.decode("utf-8"), "path": absolute, "bytes": len(data)}
    return sources


def verify_sources(sources):
    changed = [path for path, value in sources.items() if sha256(value["path"]) != value["sha256"]]
    if changed:
        raise EvidenceError("Sources changed during collection: " + ", ".join(changed[:8]))


def verify_output_source_separation(outputs, sources):
    for output in outputs:
        for source in sources.values():
            path = source["path"].resolve()
            if output == path or (output.exists() and output.samefile(path)):
                raise EvidenceError("Outputs cannot overwrite or alias captured source inputs")


def capture_name(workspace, path):
    """Contract references are root-relative; native tool arguments stay native."""
    return source_path(workspace, str(Path(path).resolve()))[0]


def simple_file_functions(text):
    """Replay the initial proof method's explicit, whole-file syntax subset."""
    clean = []
    for line in text.split("\n"):
        if line.lstrip().startswith("///") and not line.lstrip().startswith("////"):
            if any(marker in line.lower() for marker in
                   ("@generated", "automatically generated", "do not edit")):
                raise EvidenceError("Generated documentation/source is unsupported")
            clean.append(" " * len(line))
        else:
            clean.append(line)
    clean = "\n".join(clean)
    if re.search(r'//|/\*|\*/|["\'`#!$|\\]|[^\x00-\x7f]', clean):
        raise EvidenceError("Whole-file comment/string/macro/closure syntax is unsupported")
    header = re.compile(
        r"(?:pub(?:\(crate\))?\s+)?(?:async\s+)?fn\s+"
        r"([A-Za-z_][A-Za-z_0-9]*)\s*\(([A-Za-z_0-9\s,:&]*)\)\s*"
        r"(?:->\s*[A-Za-z_][A-Za-z_0-9:]*(?:\s*)?)?\{")
    items = re.compile(r"\b(?:fn|impl|trait|mod|struct|enum|union|type|const|static|"
                       r"use|extern|async|move|macro_rules)\b")
    cursor, functions = 0, []
    while cursor < len(clean):
        if clean[cursor].isspace():
            cursor += 1
            continue
        match = header.match(clean, cursor)
        if not match or items.search(match.group(2)):
            raise EvidenceError("Unsupported top-level syntax or competing declaration")
        opening, depth, end = match.end() - 1, 1, match.end()
        while end < len(clean) and depth:
            depth += (clean[end] == "{") - (clean[end] == "}")
            end += 1
        body = clean[opening + 1:end - 1]
        if (depth or items.search(body)
                or not re.fullmatch(r"[A-Za-z_0-9\s{}();,:.+*/%=&<>?\-]*", body)):
            raise EvidenceError("Unsupported nested/competing declaration or function body")
        functions.append(match.group(1))
        cursor = end
    if not functions:
        raise EvidenceError("No supported whole-file functions")
    return functions


def localization_proofs(mappings, queries, workspace, directory, sources, contexts, inventory=None):
    """Emit the shared proof only after replaying the bounded local checks."""
    indexed_queries = {query["id"]: query for query in queries}
    inputs = []
    locations = {key: spans[0]["range"] for key, _, spans in diagnostic_rows(inventory)
                 if len(spans) == 1 and spans[0].get("range")} if inventory is not None else {}
    for mapping in mappings:
        if mapping["status"] != "exact":
            continue
        symbol = mapping["symbols"][0]
        name = symbol["qualified_name"].split("::")[-1]
        extent = symbol["range"]
        native_end = extent["end_line"] - (2 if extent["end_column"] == 0 else 1)
        method = "source_crosschecked_simple_function_v1"
        unit = "unicode_scalar" if mapping["diagnostic_key"].startswith("clippy:") else (
            contexts[mapping["diagnostic_key"]]["data"]["inventory_column_unit"])
        predicates = None
        try:
            functions = simple_file_functions(sources[symbol["path"]]["text"])
            if functions.count(name) != 1:
                raise EvidenceError("Whole-file selected function name is ambiguous")
            checked = serena_extent({
                "kind": symbol["kind"], "name_path": name,
                "body_location": {"start_line": extent["start_line"] - 1, "end_line": native_end},
            }, sources[symbol["path"]]["text"])
        except EvidenceError as exc:
            if mapping["diagnostic_key"] not in locations:
                mapping.update(status="unknown", reasons=mapping["reasons"] + [str(exc)])
                continue
            witnesses = []
            for ref in mapping["evidence_refs"]:
                if not isinstance(ref, str):
                    continue
                query = indexed_queries[ref]
                if query["tool"] != "serena_1mcp_find_symbol" or query["status"] != "ok":
                    continue
                artifact = workspace / query["artifact"]
                if sha256(artifact) != query["artifact_sha256"]:
                    raise EvidenceError("Source-symbol query witness hash changed")
                witnesses.extend(decode_serena_witnesses(
                    decode_wire(strict_json(artifact), True), query["id"]))
            replay = verify_function_range(sources[symbol["path"]]["text"], symbol,
                                           locations[mapping["diagnostic_key"]], unit, witnesses)
            if replay["status"] != "verified":
                mapping.update(status="ambiguous" if replay["status"] == "ambiguous" else "unknown",
                               reasons=mapping["reasons"] + replay["reasons"])
                continue
            checked = replay["normalized_range"]
            method = "source_crosschecked_function_range_v1"
            predicates = dict(replay["checked_predicates"])
            # These two facts belong to the independently bound caller, never
            # the lexical utility. Exact mappings already passed that binding.
            predicates["source_binding_verified"] = True
            verify_sources(sources)
            predicates["source_hash_stable_before_after"] = True
        if checked != extent:
            raise EvidenceError("Localization proof endpoint replay mismatch")
        query_ids = [ref for ref in mapping["evidence_refs"] if isinstance(ref, str)
                     and indexed_queries[ref]["tool"] == "serena_1mcp_find_symbol"
                     and indexed_queries[ref]["status"] == "ok"]
        if not query_ids:
            mapping.update(status="unknown", reasons=mapping["reasons"] + [
                "No successful decoded source-symbol query for local proof"])
            continue
        proof = {
            "schema_version": 1, "kind": "clippy-localization-proof",
            "diagnostic_key": mapping["diagnostic_key"], "source_path": symbol["path"],
            "source_sha256": symbol["source_sha256"], "symbol_id": symbol["id"],
            "inventory_column_unit": unit,
            "local_discovery": {
                "method": method, "scope_range": extent,
                "candidate_symbol_ids": [candidate["id"] for candidate in mapping["symbols"]],
                "query_ids": query_ids,
                "checked_predicates": predicates or {key: True for key in (
                    "source_binding_verified", "source_hash_stable_before_after",
                    "diagnostic_coordinates_verified", "symbol_endpoints_source_verified",
                    "diagnostic_fully_enclosed", "relevant_local_candidates_exhausted",
                    "nested_or_competing_symbols_excluded")},
                "limitations": [],
            },
        }
        proof_path = directory / ("localization-" + str(len(inputs) + 1) + ".json")
        atomic_json(proof_path, proof)
        ref = {"path": capture_name(workspace, proof_path), "sha256": sha256(proof_path), "locator": "/"}
        mapping["evidence_refs"].append(ref)
        inputs.append({"role": "localization_proof", "path": ref["path"], "sha256": ref["sha256"]})
    return inputs


def bound_sources(binding, inventory_hash, head, sources, workspace):
    """Only explicit independently captured hash metadata can bind old diagnostics."""
    if binding is None:
        return set()
    if (binding.get("inventory_sha256") != inventory_hash or binding.get("head") != head
            or binding.get("method") not in ("fresh_capture", "independent_equivalence")
            or not isinstance(binding.get("evidence_refs"), list) or not binding["evidence_refs"]):
        raise EvidenceError("Invalid independent inventory source binding")
    for ref in binding["evidence_refs"]:
        if (not isinstance(ref, dict) or set(ref) != {"path", "sha256", "locator"}
                or not isinstance(ref["locator"], str) or not ref["locator"]
                or sha256(workspace / ref["path"]) != ref["sha256"]):
            raise EvidenceError("Inventory binding requires hash-verified independent context references")
    result = set()
    for item in binding.get("files", []):
        path = item["path"]
        if path not in sources or item["sha256"] != sources[path]["sha256"]:
            raise EvidenceError("Stale or absent inventory source hash")
        result.add(path)
    return result


def producer_plan(plan, workspace, budget):
    if (not isinstance(plan, dict) or type(plan.get("schema_version")) is not int
            or plan["schema_version"] != 1
            or not set(plan) <= {"schema_version", "source_files", "symbols", "targets", "configuration"}
            or not isinstance(plan.get("source_files"), list)):
        raise EvidenceError("Producer plan requires schema_version 1 and explicit source_files")
    sources = capture_sources(workspace, plan["source_files"], budget)
    symbols, targets = plan.get("symbols", []), plan.get("targets", [])
    if not isinstance(symbols, list) or not isinstance(targets, list):
        raise EvidenceError("Plan symbols/targets must be arrays")
    normalized_seeds = []
    for seed in symbols:
        if not isinstance(seed, dict) or set(seed) != {"path", "name_path"}:
            raise EvidenceError("Symbol seeds require exactly path and name_path")
        path, _ = source_path(workspace, seed["path"])
        if path not in sources or not isinstance(seed["name_path"], str) or not seed["name_path"].strip():
            raise EvidenceError("Symbol seed must have a captured path and nonempty name")
        normalized_seeds.append(dict(seed, path=path))
    for target in targets:
        if (not isinstance(target, str) or not target.strip() or len(target) > 1024
                or any(c in target for c in "/\\\r\n") or ".." in target):
            raise EvidenceError("Plan HIR targets must be explicit nonempty qualified names")
    return sources, normalized_seeds, targets


def decode_serena_witnesses(payload, query_id):
    """Extract only actual returned nodes; absence never invents children."""
    if not isinstance(payload, list):
        raise EvidenceError("Unsupported Serena source-symbol envelope")
    witnesses = []
    def visit(node, parent=None):
        if not isinstance(node, dict):
            raise EvidenceError("Unsupported Serena symbol node")
        name, location = node.get("name_path"), node.get("body_location")
        if not isinstance(name, str) or not name or not isinstance(location, dict):
            raise EvidenceError("Serena source-symbol identity/range missing")
        witnesses.append({
            "query_id": query_id, "name_path": name, "kind": node.get("kind"),
            "relative_path": node.get("relative_path"),
            "body_location": dict(location),
            "parent_name_path": parent if parent is not None else (
                name.rsplit("/", 1)[0] if "/" in name else None),
        })
        if "children" in node:
            if not isinstance(node["children"], list):
                raise EvidenceError("Unsupported Serena children envelope")
            for child in node["children"]:
                visit(child, name)
    for node in payload:
        visit(node)
    return witnesses


def native_function_extent(native, text):
    """Whole-line native conversion; the shared validator must verify it."""
    location, lines = native.get("body_location", {}), source_lines(text)
    a, b = location.get("start_line"), location.get("end_line")
    if (native.get("kind") not in ("Function", "Method", 6, 12)
            or type(a) is not int or type(b) is not int or not 0 <= a <= b < len(lines)):
        raise EvidenceError("Unsupported source function/method body")
    return {"start_line": a + 1, "start_column": 0,
            "end_line": b + 2 if lines[b].endswith("\n") else b + 1,
            "end_column": 0 if lines[b].endswith("\n") else len(lines[b]),
            "column_unit": "unicode_scalar"}


async def discover_serena(capture, workspace, sources, seeds, limitations, inventory=None):
    initial, iq = await capture.query("serena", "initial_instructions", {}, True)
    config, cq = await capture.query("serena", "get_current_config", {}, True)
    # These are the verified 2.1.0 text formats, not instructions to execute.
    reported = re.findall(
        r"(?:^|\n)The project with name '[^'\r\n]+' at ([^\r\n]+) is activated\.(?:\r?$)",
        initial, re.MULTILINE) if isinstance(initial, str) else []
    if (len(reported) != 1 or not Path(reported[0]).is_absolute()
            or Path(reported[0]).resolve() != workspace
            or not isinstance(config, str)
            or not re.search(r"(?m)^Language server status: ready\r?$", config)):
        raise EvidenceError("Serena root/readiness not verified: report the selected absolute root and ready language server; never activate a project")
    for query in (iq, cq):
        query["pagination"] = {"status": "not_applicable", "pages": 1, "returned": 1,
                               "total": None, "reason": "Connection root/readiness text"}
    symbols, refs = [], {}
    for path in sorted({seed["path"].replace("\\", "/") for seed in seeds}):
        overview, oq = await capture.query("serena", "get_symbols_overview", {
            "relative_path": path, "depth": 0}, True)
        if not isinstance(overview, dict) or not all(
                isinstance(names, list) and all(isinstance(n, str) for n in names)
                for names in overview.values()):
            oq["status"] = "unsupported"
            limitations.append(f"{path}: unsupported symbol overview; no exact mapping")
            continue
        names = set(n for group in overview.values() for n in group)
        text = sources[path]["text"]
        selected = {seed["name_path"] for seed in seeds
                    if seed["path"].replace("\\", "/") == path}
        all_functions = set(overview.get("Function", [])) | selected
        file_symbols = []
        incomplete = False
        pending, requested, witnesses = list(sorted(all_functions)), set(), []
        while pending:
            name = pending.pop(0)
            if name in requested:
                continue
            requested.add(name)
            try:
                found, query = await capture.query("serena", "find_symbol", {
                    "name_path_pattern": name, "relative_path": path,
                    "include_body": False, "depth": 0, "max_matches": 64}, True)
            except EvidenceError as exc:
                limitations.append(f"{path}: symbol discovery incomplete: {exc}")
                incomplete = True
                break
            try:
                decoded = decode_serena_witnesses(found, query["id"])
                for native in decoded:
                    normalized, _ = source_path(workspace, native["relative_path"])
                    if normalized != path:
                        raise EvidenceError("Source symbol outside requested file")
                    native["relative_path"] = normalized
                    parent = native["parent_name_path"]
                    if parent and parent not in requested:
                        pending.append(parent)
                witnesses.extend(decoded)
            except EvidenceError:
                query["status"] = "unsupported"
                incomplete = True
                continue
            query["pagination"] = {"status": "unknown", "pages": 1, "returned": len(found),
                                   "total": None, "reason": "No completeness metadata; source crosscheck required"}
        sources[path]["range_witnesses"] = witnesses
        locations = []
        if inventory is not None:
            for key, namespace, spans in diagnostic_rows(inventory):
                if (namespace == "clippy" and len(spans) == 1 and spans[0].get("range")
                        and re.sub("/+", "/", str(spans[0]["file"]).replace("\\", "/")) == path):
                    locations.append(spans[0]["range"])
        seen_symbols = set()
        for native in witnesses:
            if native["kind"] not in ("Function", "Method", 6, 12):
                continue
            try:
                extent = native_function_extent(native, text)
                symbol = {"id": f"s{len(symbols) + len(file_symbols) + 1:06d}",
                          "qualified_name": f"serena::{path}::{native['name_path']}",
                          "kind": native["kind"], "path": path, "range": extent,
                          "source_sha256": sources[path]["sha256"]}
                if inventory is not None:
                    relevant = [location for location in locations
                                if (extent["start_line"], 0) <= (location[0], location[1])
                                and (location[2], location[3]) <= (extent["end_line"], extent["end_column"])]
                    if not any(verify_function_range(text, symbol, location, "unicode_scalar", witnesses)["status"]
                               == "verified" for location in relevant):
                        limitations.append(
                            f"{path}: {native['name_path']}: no applicable verified diagnostic mapping; raw witness retained")
                        continue
                else:
                    # Historical helper callers without inventory retain the old
                    # strict discovery contract; production supplies inventory.
                    serena_extent(native, text)
                identity = (native["name_path"], tuple(extent.values()))
                if identity in seen_symbols:
                    continue
                seen_symbols.add(identity)
                file_symbols.append(symbol)
                refs[symbol["id"]] = sorted({oq["id"]} | {w["query_id"] for w in witnesses})
            except EvidenceError as exc:
                limitations.append(f"{path}: {native['name_path']}: {exc}")
        if incomplete:
            limitations.append(f"{path}: some source queries incomplete; verified range-local facts only")
        symbols.extend(file_symbols)
    return symbols, refs


def check_usage_sources(rows, target, workspace, sources, budget, limitations):
    """Byte-span witness checks do not infer coordinate conventions or endpoints."""
    valid = True
    expected = target.rsplit("::", 1)[-1]
    for row in rows:
        try:
            path, absolute = source_path(workspace, row["file"])
            if path not in sources:
                if len(sources) >= budget:
                    raise EvidenceError("Consumer source budget exhausted")
                new = capture_sources(workspace, [path], budget)
                if sum(s["bytes"] for s in sources.values()) + new[path]["bytes"] > MAX_SOURCE_BYTES:
                    raise EvidenceError("Aggregate consumer/source capture exceeds 128 MiB")
                sources.update(new)
                limitations.append(f"{path}: consumer captured after discovery, no pre-query hash")
                valid = False
            data = absolute.read_bytes()
            start, end = row["start"], row["end"]
            if (type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(data)
                    or data[start:end].decode("utf-8") != expected):
                raise EvidenceError("Native byte span does not match target spelling; no offset repair")
        except (EvidenceError, UnicodeError) as exc:
            limitations.append(f"Unresolved who_uses endpoint {row.get('file')}: {exc}")
            valid = False
    return valid


class CaptureIntegrityError(EvidenceError):
    """A changed bound artifact/source cannot be exported as partial evidence."""


def verified_query_payload(workspace, query, plain=False):
    path = workspace / query["artifact"]
    if sha256(path) != query["artifact_sha256"]:
        raise CaptureIntegrityError("Origin query capture hash changed")
    if query["status"] != "ok":
        raise EvidenceError("Origin query status is not successful")
    raw = strict_json(path)
    return definition_text(raw) if plain else decode_wire(raw, query["tool"].startswith("serena_"))


def verify_origin_context(manifest_text, module_text):
    """The single authorized default crate/module chain, not a Rust resolver."""
    try:
        manifest = tomllib.loads(manifest_text)
    except tomllib.TOMLDecodeError:
        raise EvidenceError("Unsupported origin manifest") from None
    package, lib = manifest.get("package", {}), manifest.get("lib", {})
    if (not isinstance(package, dict) or package.get("name") != "apparatus-contracts"
            or package.get("autolib", True) is not True or not isinstance(lib, dict)
            or "name" in lib or "path" in lib):
        raise EvidenceError("Origin default crate/library identity overridden")
    pending, item, count = [], "", 0
    for line in module_text.split("\n"):
        value = line.strip()
        if not value or value.startswith("//"):
            continue
        if value.startswith("#[") and not item:
            if not re.fullmatch(r'#\[cfg\(feature\s*=\s*"[\w-]+"\)\]', value):
                raise EvidenceError("Unsupported origin module-root attribute")
            pending.append(value)
            continue
        item += " " + value
        if not item.endswith(";"):
            if not item.lstrip().startswith("pub use "):
                raise EvidenceError("Unsupported origin module-root syntax")
            continue
        item = item.strip()
        declaration = re.fullmatch(r"pub mod ([A-Za-z_]\w*);", item)
        if declaration:
            if declaration[1] == "runtime":
                if pending:
                    raise EvidenceError("Origin runtime module is conditional/path-attributed")
                count += 1
        elif (not re.fullmatch(r"pub use [A-Za-z_]\w*(?:::[A-Za-z_]\w*)*(?:::\{[\w,\s]+\})?;", item)
              or re.search(r"\bruntime\b", item)):
            raise EvidenceError("Unsupported origin reexport/module indirection")
        pending, item = [], ""
    if count != 1 or pending or item:
        raise EvidenceError("Exactly one unconditional literal pub mod runtime required")


def parse_origin_definition(text, workspace, source):
    match = re.fullmatch(
        r"Found 1 definition\(s\) for 'validate_runtime_uid':\r?\n"
        r"([^\r\n]+):(\d+):(\d+) \(validate_runtime_uid, exact=true\)\s*", text)
    if not match:
        raise EvidenceError("Unsupported or ambiguous origin definition")
    raw = match[1]
    if raw.startswith("\\\\?\\"):
        if not re.match(r"^\\\\\?\\[A-Za-z]:\\", raw):
            raise EvidenceError("Unsupported definition device/UNC wrapper")
        raw = raw[4:]
    path, _ = source_path(workspace, raw)
    if path != ORIGIN_SOURCE:
        raise EvidenceError("Definition is not the authorized origin file")
    line, column = int(match[2]), int(match[3])
    lines = source_lines(source)
    if not 1 <= line <= len(lines) or column < 1:
        raise EvidenceError("Definition coordinates outside current source")
    header = lines[line - 1].rstrip("\r\n")
    if (header[:column - 1] != "pub fn " or not header[column - 1:].startswith(ORIGIN_NAME + "(")
            or re.sub(r"\s+", "", header) !=
            "pubfnvalidate_runtime_uid(value:&str)->Result<(),RuntimeErrorCodeV1>{"):
        raise EvidenceError("Definition/signature token mismatch; no coordinate repair")
    return [line, 0, line, len(header)]


def build_origin_proof(workspace, directory, sources, queries):
    indexed = {query["id"]: query for query in queries}
    def one(suffix):
        items = [q for q in queries if q["tool"] == "rust-code-mcp_1mcp_" + suffix]
        if len(items) != 1 or items[0]["arguments"].get("directory") != str(workspace):
            raise EvidenceError("Origin lookup witness missing/ambiguous/root mismatch")
        return items[0]
    signature_query, definition_query = one("function_signature"), one("find_definition")
    if (signature_query["arguments"].get("target") != ORIGIN_TARGET
            or definition_query["arguments"] !=
            {"directory": str(workspace), "symbol_name": ORIGIN_NAME, "exact": True}):
        raise EvidenceError("Origin lookup was not the fixed exact target")
    data = verified_query_payload(workspace, signature_query)
    expected_params = [{"name": "value", "ty": "&str", "by_ref": True, "mutability": False}]
    signature = data.get("signature") if isinstance(data, dict) else None
    if (not isinstance(signature, dict) or data.get("target") != ORIGIN_TARGET
            or not {"is_async", "self_param", "params", "return_type", "generics"} <= set(signature)
            or signature.get("is_async") is not False or signature.get("self_param") is not None
            or signature.get("params") != expected_params or signature.get("generics") != []
            or signature["params"][0]["by_ref"] is not True
            or signature["params"][0]["mutability"] is not False
            or not isinstance(signature.get("return_type"), str)
            or re.sub(r"\s+", "", signature["return_type"]) != "Result<(),RuntimeErrorCodeV1>"):
        signature_query["status"] = "unsupported"
        raise EvidenceError("Origin signature does not match the supported declaration")
    for path in (ORIGIN_SOURCE, ORIGIN_MANIFEST, ORIGIN_MODULE):
        if path not in sources:
            raise EvidenceError("Origin/context source must be explicitly prehashed: " + path)
    verify_sources(sources)
    verify_origin_context(sources[ORIGIN_MANIFEST]["text"], sources[ORIGIN_MODULE]["text"])
    source = sources[ORIGIN_SOURCE]["text"]
    try:
        location = parse_origin_definition(
            verified_query_payload(workspace, definition_query, True), workspace, source)
    except CaptureIntegrityError:
        raise
    except EvidenceError:
        definition_query["status"] = "unsupported"
        raise
    witnesses = []
    for query in queries:
        if (query["tool"] == "serena_1mcp_find_symbol" and query["status"] == "ok"
                and query["arguments"].get("relative_path") == ORIGIN_SOURCE):
            witnesses.extend(decode_serena_witnesses(verified_query_payload(workspace, query), query["id"]))
    selected = [w for w in witnesses if w["name_path"] == ORIGIN_NAME
                and w["parent_name_path"] is None and w["relative_path"] == ORIGIN_SOURCE
                and w["kind"] in ("Function", 12)]
    identities = {(w["body_location"].get("start_line"), w["body_location"].get("end_line"))
                  for w in selected}
    if len(identities) != 1:
        raise EvidenceError("Unique top-level Serena origin witness missing")
    extent = native_function_extent(selected[0], source)
    symbol = {"path": ORIGIN_SOURCE, "qualified_name": "serena::" + ORIGIN_SOURCE + "::" + ORIGIN_NAME,
              "kind": "Function", "range": extent}
    verified = verify_function_range(source, symbol, location, "unicode_scalar", witnesses)
    if verified["status"] != "verified" or verified["candidate_name_paths"] != [ORIGIN_NAME]:
        raise EvidenceError("Origin function/source witness replay failed: " + "; ".join(verified["reasons"]))
    ids = [signature_query["id"], definition_query["id"]] + sorted({w["query_id"] for w in selected})
    if any(identifier not in indexed for identifier in ids):
        raise EvidenceError("Origin query reference missing")
    proof = {"schema_version": 1, "kind": "clippy-origin-binding", "target": ORIGIN_TARGET,
             "source_path": ORIGIN_SOURCE, "source_sha256": sources[ORIGIN_SOURCE]["sha256"],
             "declaration_range": verified["normalized_range"],
             "crate_manifest_ref": {"path": ORIGIN_MANIFEST, "sha256": sources[ORIGIN_MANIFEST]["sha256"],
                                    "locator": "package.name"},
             "module_root_ref": {"path": ORIGIN_MODULE, "sha256": sources[ORIGIN_MODULE]["sha256"],
                                 "locator": "pub mod runtime;"},
             "query_ids": ids, "method": "direct_crate_module_function_v1"}
    path = directory / "origin-binding.json"
    atomic_json(path, proof)
    return proof, {"path": capture_name(workspace, path), "sha256": sha256(path), "locator": "/"}


def file_observations(workspace, sources, state, origin, origin_ref):
    observations = []
    for usage in state["usages"]:
        for row in usage["rows"]:
            path, absolute = source_path(workspace, row["file"])
            if path not in sources:
                raise EvidenceError("Unbound returned endpoint blocks observation export: " + path)
            current = absolute.read_bytes()
            if hashlib.sha256(current).hexdigest() != sources[path]["sha256"]:
                raise CaptureIntegrityError("Observation endpoint source changed")
            stable = path in state["prehashed"]
            spelling = current[row["start"]:row["end"]] == ORIGIN_NAME.encode("ascii")
            supported_query = usage["status"] in ("ok", "partial")
            positive = origin is not None and stable and spelling and supported_query
            reasons = []
            if origin is None:
                reasons.extend(state["origin_reasons"])
            if not stable:
                reasons.append("Endpoint discovered after query; subsequent bounded capture required")
            if not spelling:
                reasons.append("Raw span/spelling mismatch; no offset repair; native units retained in raw query")
            if not supported_query:
                reasons.append("Usage sequence has an error/unsupported envelope; no candidate promotion")
            if "consumer_function" not in row:
                reasons.append("No consumer_function advertised; no caller identity inferred")
            observations.append({
                "id": f"observation-{len(observations) + 1:06d}", "kind": "reference",
                "origin": {"path": ORIGIN_SOURCE, "source_sha256": sources[ORIGIN_SOURCE]["sha256"],
                           "symbol_id": None, "range": origin["declaration_range"] if origin else None},
                "destination": {"path": path, "source_sha256": sources[path]["sha256"],
                                "symbol_id": None, "range": None},
                "query_ids": [usage["query_id"]], "origin_binding_ref": origin_ref,
                "identity_status": "file_candidate" if positive else "unresolved",
                "endpoint_status": "source_verified" if positive else "path_only",
                "relationship_scope": "symbol_to_file_candidate", "reasons": reasons})
    return observations


def verify_output_input_separation(outputs, inputs):
    for index, output in enumerate(outputs):
        for path in list(inputs) + list(outputs[:index]):
            if output == path or (output.exists() and path.exists() and output.samefile(path)):
                raise EvidenceError("Observation/accepted outputs alias an input or each other")


def verify_capture_hashes(workspace, evidence):
    refs = [(q["artifact"], q["artifact_sha256"]) for q in evidence["queries"]]
    refs += [(ref["path"], ref["sha256"]) for ref in evidence["producer"]["captures"]]
    for path, expected in refs:
        if sha256(workspace / path) != expected:
            raise CaptureIntegrityError("Captured query/context hash changed before publication")


async def produce(args, inventory, plan, workspace, directory, sources, seeds, targets,
                  evidence, limitations):
    async with asyncio.timeout(args.timeout):
        async with connect(args.url, args.timeout) as session:
            server = as_json((await session.initialize()).serverInfo)
            tools = await catalog(session)
            catalogue_path = directory / "hir-catalog.json"
            atomic_json(catalogue_path, {"server": server, "tools": tools})
            capture = ProducerCapture(session, tools, directory, args.max_queries, workspace)
            evidence["producer"]["captures"].append(
                {"path": str(catalogue_path), "sha256": sha256(catalogue_path), "locator": "tools"})
            for target in targets:
                first_page = len(capture.queries)
                rows, queries, pagination = await paged_who_uses(
                    capture, workspace, target, args.page_size, args.max_pages)
                witnessed = check_usage_sources(rows, target, workspace, sources,
                                                args.max_sources, limitations)
                for query in queries:
                    query["coverage"]["freshness"] = "unknown" if witnessed else "partial"
                pages = capture.queries[first_page:]
                if not pages:
                    raise EvidenceError("Producer query budget exhausted before target capture")
                if pages:
                    pagination = dict(pagination, pages=len(pages))
                    # One normalized logical query points to a hash-bound page
                    # manifest. Individual raw MCP responses remain untouched.
                    group = dict(pages[0])
                    group_path = directory / (group["id"] + "-sequence.json")
                    atomic_json(group_path, {
                        "target": target, "pagination": pagination,
                        "pages": [{"id": q["id"], "tool": q["tool"], "arguments": q["arguments"],
                                   "artifact": capture_name(workspace, q["artifact"]),
                                   "artifact_sha256": q["artifact_sha256"],
                                   # A valid page can belong to an incomplete
                                   # sequence. Keep that scope on the group.
                                   "status": "ok" if q["status"] == "partial" else q["status"]} for q in pages]})
                    group.update(artifact=str(group_path), artifact_sha256=sha256(group_path),
                                 pagination=pagination, coverage=coverage())
                    group["coverage"]["freshness"] = "unknown" if witnessed else "partial"
                    group["status"] = ("error" if any(q["status"] == "error" for q in pages)
                                       else "unsupported" if any(q["status"] == "unsupported" for q in pages)
                                       else "ok" if pagination["status"] == "complete" else "partial")
                    evidence["queries"].append(group)
                    if args.observations is not None:
                        args.observation_state["usages"].append(
                            {"query_id": group["id"], "rows": rows, "status": group["status"],
                             "pagination": dict(pagination)})
                    evidence["producer"]["captures"].extend(
                        {"path": q["artifact"], "sha256": q["artifact_sha256"], "locator": q["id"]}
                        for q in pages)
                limitations.append(
                    f"{target}: {pagination['status']} indexed-scope pagination; "
                    "HIR endpoint coordinate units/qualified symbol linkage unverified; no normalized relation")
            if args.observations is not None:
                first = len(capture.queries)
                for suffix, arguments in (
                    ("function_signature", {"directory": str(workspace), "target": ORIGIN_TARGET}),
                    ("find_definition", {"directory": str(workspace), "symbol_name": ORIGIN_NAME, "exact": True}),
                ):
                    try:
                        _, query = await capture.query("rust-code-mcp", suffix, arguments)
                        query["pagination"] = {"status": "not_applicable", "pages": 1,
                                               "returned": 1, "total": None, "reason": "Single origin lookup"}
                    except EvidenceError as exc:
                        args.observation_state["origin_reasons"].append(str(exc))
                evidence["queries"].extend(capture.queries[first:])
            remaining, last_id = capture.remaining, capture.next_id
        if seeds:
            if args.serena_url is None:
                limitations.append("Symbol seeds supplied without --serena-url; mapping unsupported")
                return [], {}
            async with connect(args.serena_url, args.timeout) as session:
                server = as_json((await session.initialize()).serverInfo)
                tools = await catalog(session)
                catpath = directory / "serena-catalog.json"
                atomic_json(catpath, {"server": server, "tools": tools})
                evidence["producer"]["captures"].append(
                    {"path": str(catpath), "sha256": sha256(catpath), "locator": "tools"})
                # Use distinct artifact names and query IDs across connections.
                capture = ProducerCapture(session, tools, directory, remaining, workspace)
                capture.queries = list(evidence["queries"])
                capture.next_id = last_id
                try:
                    return await discover_serena(capture, workspace, sources, seeds, limitations, inventory)
                finally:
                    evidence["queries"] = capture.queries
    return [], {}


def producer_main(args):
    """Produce contract artifacts; inputs never become arbitrary tool calls."""
    directory = None
    try:
        workspace = validate_workspace(args.workspace)
        args.url = validate_url(args.url)
        if args.serena_url:
            args.serena_url = validate_url(args.serena_url)
        if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 300:
            raise EvidenceError("Producer deadline must be within 1..300 seconds")
        for value, low, high in ((args.max_queries, 1, 4096), (args.max_sources, 1, 20000),
                                 (args.max_pages, 1, 128), (args.page_size, 1, 200)):
            if not low <= value <= high:
                raise EvidenceError("Producer budget outside supported bounds")
        inputs = [args.inventory.resolve(), args.plan.resolve()]
        inputs += [p.resolve() for p in (args.binding, args.source_equivalence) if p]
        inputs += [p.resolve() for p in args.context]
        binding = strict_json(args.binding) if args.binding else None
        if binding is not None:
            if not isinstance(binding, dict) or not isinstance(binding.get("evidence_refs"), list):
                raise EvidenceError("Malformed source-binding references")
            for ref in binding["evidence_refs"]:
                if not isinstance(ref, dict) or not isinstance(ref.get("path"), str):
                    raise EvidenceError("Malformed source-binding reference")
                inputs.append((workspace / ref["path"]).resolve())
        inputs = list(dict.fromkeys(inputs))
        for path in inputs:
            capture_name(workspace, path)
        protected = set(inputs) | {Path(__file__).resolve()}
        output = output_path(args.output, protected)
        snapshot_path = output_path(args.snapshot, protected | {output})
        observation_path = output_path(args.observations, protected | {output, snapshot_path})
        outputs = (output, snapshot_path) + ((observation_path,) if observation_path else ())
        verify_output_input_separation(outputs, inputs)
        directory = args.artifacts.resolve()
        if directory.exists() or directory in protected or directory in outputs:
            raise EvidenceError("Artifacts directory must be new and distinct from inputs/outputs")
        if any(path.is_relative_to(directory) for path in outputs):
            raise EvidenceError("Outputs cannot be descendants of the raw artifacts directory")
        if not all(path.is_relative_to(workspace) for path in (directory,) + outputs):
            raise EvidenceError("Producer artifacts and outputs must stay within the explicit workspace")
        input_hashes = {path: sha256(path) for path in inputs}
        inventory_hash = input_hashes[args.inventory.resolve()]
        inventory, plan = strict_json(args.inventory), strict_json(args.plan)
        # Validate the whole inventory, preserving strict namespaces/counts.
        list(diagnostic_rows(inventory))
        sources, seeds, targets = producer_plan(plan, workspace, args.max_sources)
        verify_output_source_separation(outputs, sources)
        if observation_path:
            if (targets != [ORIGIN_TARGET] or not args.serena_url
                    or not {ORIGIN_SOURCE, ORIGIN_MANIFEST, ORIGIN_MODULE} <= set(sources)):
                raise EvidenceError("Observations require the single authorized target, Serena, and prehashed origin contexts")
            args.observation_state = {"prehashed": set(sources), "usages": [], "origin_reasons": []}
        head = git_head(workspace)
        bound = bound_sources(binding, inventory_hash, head, sources, workspace)
        contexts = {}
        diagnostic_keys = {key for key, _, _ in diagnostic_rows(inventory)}
        for context_path in args.context:
            if context_path.suffix.lower() != ".json":
                continue  # Snapshot-bound policy text, never executable predicates.
            data = strict_json(context_path)
            if not isinstance(data, dict) or "diagnostic_key" not in data:
                continue
            key = data["diagnostic_key"]
            if key not in diagnostic_keys or key in contexts:
                raise EvidenceError("Unknown or duplicate diagnostic mapping context")
            contexts[key] = {"data": data, "reference": {
                "path": capture_name(workspace, context_path), "sha256": sha256(context_path),
                "locator": "diagnostic_key=" + key}}
        limitations = [
            "Current source hashes are fresh captures, not manufactured historical hashes.",
            "Source/index/feature/private/macro/trait/test completeness is not established.",
            "Serena source-scoped identities are not HIR crate-qualified names.",
            "Relations remain raw until coordinate conventions and both symbol endpoints are verified.",
        ]
        if args.source_equivalence:
            if sha256(args.source_equivalence) != args.source_equivalence_sha256:
                raise EvidenceError("Source equivalence proof hash mismatch")
            proof = strict_json(args.source_equivalence)
            if not isinstance(proof, dict) or not isinstance(proof.get("proofs"), list):
                raise EvidenceError("Unsupported source equivalence proof")
            limitations.append("Git tree equivalence proof is context only; not index freshness or historical file hashes.")
        configuration = {"toolchain": "unknown", "features": "unknown", "target": "unknown",
                         "lanes": "unknown", "submodules": "unknown", "index": "unknown",
                         "dirty_sources": "unknown; current participant hashes checked before/after",
                         "declared_context": plan.get("configuration", {})}
        if args.source_equivalence:
            configuration["source_equivalence"] = {
                "path": capture_name(workspace, args.source_equivalence),
                "sha256": sha256(args.source_equivalence), "locator": "proofs"}
        evidence = {"schema_version": 1, "kind": "clippy-code-evidence", "workspace": str(workspace),
                    "snapshot_sha256": None, "inventory_sha256": inventory_hash,
                     "producer": {"adapter_version": "2.0", "captures": [],
                                  "tool": "lint-workgraph",
                                  "script_sha256": sha256(Path(__file__)),
                                  "range_scanner_sha256": sha256(Path(__file__).with_name("clippy_source_ranges.py"))},
                    "mappings": [], "relations": [], "queries": [], "limitations": limitations}
        directory.mkdir(parents=False)
        symbols, refs = asyncio.run(produce(args, inventory, plan, workspace, directory,
                                           sources, seeds, targets, evidence, limitations))
        verify_output_source_separation(outputs, sources)
        verify_sources(sources)
        if head != git_head(workspace):
            raise EvidenceError("Workspace HEAD changed during collection")
        if any(sha256(path) != digest for path, digest in input_hashes.items()):
            raise EvidenceError("Producer input changed during collection")
        for query in evidence["queries"]:
            query["artifact"] = capture_name(workspace, query["artifact"])
        for ref in evidence["producer"]["captures"]:
            ref["path"] = capture_name(workspace, ref["path"])
        evidence["mappings"] = map_diagnostics(inventory, workspace, sources, symbols, refs, bound, contexts)
        proof_inputs = localization_proofs(evidence["mappings"], evidence["queries"], workspace,
                                          directory, sources, contexts, inventory)
        observed = None
        if observation_path:
            origin, origin_ref = None, None
            try:
                origin, origin_ref = build_origin_proof(workspace, directory, sources, evidence["queries"])
            except CaptureIntegrityError:
                raise
            except EvidenceError as exc:
                args.observation_state["origin_reasons"].append(str(exc))
            if origin_ref:
                proof_inputs.append({"role": "origin_binding", "path": origin_ref["path"],
                                     "sha256": origin_ref["sha256"]})
            observed = {"schema_version": 1, "kind": "clippy-file-observations", "workspace": str(workspace),
                        "snapshot_sha256": None, "evidence_sha256": None, "inventory_sha256": inventory_hash,
                        "observations": file_observations(workspace, sources, args.observation_state, origin, origin_ref),
                        "limitations": ["Candidate file observations are not hard constraints or reference closure."]
                                        + args.observation_state["origin_reasons"]
                                        + [f"{usage['query_id']}: incomplete/unsupported indexed query scope"
                                           for usage in args.observation_state["usages"]
                                           if usage["status"] != "ok" or usage["pagination"]["status"] != "complete"]}
        if not args.allow_partial and any(q["status"] != "ok" for q in evidence["queries"]):
            raise EvidenceError("Partial/error/unsupported queries retained as raw artifacts; "
                                "use --allow-partial to export explicitly partial normalized evidence")
        input_records = [{"role": "inventory" if path == args.inventory.resolve() else "source_context",
                          "path": capture_name(workspace, path), "sha256": input_hashes[path]} for path in inputs]
        input_records.extend({"role": "mcp_capture", "path": q["artifact"],
                              "sha256": q["artifact_sha256"]} for q in evidence["queries"])
        input_records.extend({"role": "producer_capture", "path": ref["path"], "sha256": ref["sha256"]}
                             for ref in evidence["producer"]["captures"])
        input_records.extend(proof_inputs)
        snapshot = {"schema_version": 1, "kind": "clippy-source-snapshot",
                    "workspace": str(workspace), "head": head,
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "files": [{"path": p, "sha256": v["sha256"]} for p, v in sorted(sources.items())],
                    "inputs": input_records, "configuration": configuration,
                    "source_binding": "partial" if bound else "unknown", "limitations": limitations}
        # Each file is atomic. The pair is hash-bound, not a multi-file transaction:
        # a failed second replace leaves a detectable mismatch, never valid proof.
        verify_sources(sources)
        verify_output_source_separation(outputs, sources)
        verify_output_input_separation(outputs, inputs)
        verify_capture_hashes(workspace, evidence)
        if any(sha256(path) != digest for path, digest in input_hashes.items()):
            raise CaptureIntegrityError("Producer input changed before publication")
        atomic_json(snapshot_path, snapshot)
        evidence["snapshot_sha256"] = sha256(snapshot_path)
        atomic_json(output, evidence)
        if observed is not None:
            observed.update(snapshot_sha256=sha256(snapshot_path), evidence_sha256=sha256(output))
            atomic_json(observation_path, observed)
        return 0
    except Exception as exc:
        print("mcp-code-evidence producer: " + (str(exc) if isinstance(exc, EvidenceError)
              else type(exc).__name__ + "; operation failed"), file=sys.stderr)
        # Fresh raw artifacts may remain for diagnosis; never replace accepted
        # snapshot/evidence on collection/validation failure.
        return 1


NATIVE_TOOLS = {
    "crate_dependency_metric", "crate_edges", "module_tree", "build_codemap",
    "who_uses", "calls_from", "who_imports",
}
NATIVE_INVENTORY_MAX_BYTES = 64 * 1024 * 1024


def read_native_inventory(path):
    """Parse and identify the same bounded bytes, regardless of path replacement."""
    with path.open("rb") as handle:
        raw = handle.read(NATIVE_INVENTORY_MAX_BYTES + 1)
    if len(raw) > NATIVE_INVENTORY_MAX_BYTES:
        raise EvidenceError("Native inventory exceeds 64 MiB")
    inventory = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               EvidenceError("Non-finite JSON number")))
    return inventory, hashlib.sha256(raw).hexdigest()


def native_selector(value):
    if (not isinstance(value, str) or not value.strip() or len(value) > 4096
            or any(c in value for c in "/\\\r\n\x00") or ".." in value or "://" in value):
        raise EvidenceError("Native selector must be a qualified graph name, not a path")
    return value


class NativeCapture:
    """Generic read-only graph capture; uses the existing SDK connection owner."""

    def __init__(self, session, tools, workspace, directory, limit, deadline):
        self.session, self.tools = session, tools
        self.workspace, self.directory = workspace, directory
        self.limit, self.deadline = limit, deadline
        self.queries, self.cache = [], {}
        self.stopped = None
        self.reused = 0
        self.requests = 0

    async def query(self, suffix, arguments):
        if suffix not in NATIVE_TOOLS or arguments.get("directory") != str(self.workspace):
            raise EvidenceError("Generic native request is not an authorized tool/root")
        key = json.dumps([suffix, arguments], sort_keys=True, separators=(",", ":"))
        if key in self.cache:
            payload, query = self.cache[key]
            query["reused_count"] += 1
            self.reused += 1
            return payload, query
        if time.monotonic() >= self.deadline:
            self.stopped = "not_attempted_deadline"
            return None, None
        if len(self.queries) >= self.limit:
            self.stopped = "not_attempted_budget"
            return None, None
        exact = "rust-code-mcp_1mcp_" + suffix
        query = {
            "id": f"nq{len(self.queries) + 1:06d}", "tool": exact,
            "arguments": arguments, "artifact": None, "artifact_sha256": None,
            "status": "pending",
            "pagination": {"status": "unknown", "pages": 1, "returned": 0, "total": None,
                           "reason": "Result not validated"},
            "limitations": [], "duration_seconds": 0.0, "reused_count": 0,
        }
        self.queries.append(query)
        artifact = self.directory / (query["id"] + ".json")
        query["artifact"] = artifact.relative_to(self.directory).as_posix()
        start, payload, raw = time.monotonic(), None, None
        try:
            matches = [t for t in self.tools if t.get("name", "").endswith("_1mcp_" + suffix)]
            if len(matches) != 1 or matches[0]["name"] != exact:
                query["status"] = "unavailable"
                raise EvidenceError("Native tool missing/ambiguous: " + suffix)
            schema = matches[0].get("inputSchema", {})
            if (not set(arguments) <= set(schema.get("properties", {}))
                    or not set(schema.get("required", [])) <= set(arguments)):
                query["status"] = "unsupported"
                raise EvidenceError("Native tool argument schema drift: " + suffix)
            self.requests += 1
            raw = as_json(await self.session.call_tool(exact, arguments=arguments))
            if len(json.dumps(raw).encode("utf-8")) > MAX_RESULT_BYTES:
                raw = None
                raise EvidenceError("Native result exceeds capture byte budget")
            atomic_json(artifact, raw)
            payload = decode_wire(raw)
            query["status"] = "ok"
        except asyncio.CancelledError:
            query["status"] = "timeout"
            query["limitations"].append("Whole-operation deadline interrupted this query")
            raise
        except Exception as exc:
            if query["status"] == "pending":
                query["status"] = "error"
            query["limitations"].append(str(exc) if isinstance(exc, EvidenceError) else type(exc).__name__)
        finally:
            if not artifact.exists():
                atomic_json(artifact, raw if raw is not None else {"failure": query["status"]})
            query["artifact_sha256"] = sha256(artifact)
            query["duration_seconds"] = max(0.0, time.monotonic() - start)
            self.cache[key] = (payload, query)
        return payload, query


async def native_pages(capture, suffix, selector, page_size, max_pages, row_budget=None):
    """Validate observed native count envelopes; no offset repair or retries."""
    shapes = {
        "crate_dependency_metric": ("metrics", None),
        "who_uses": ("usages", "target"),
        "calls_from": ("call_sites", "caller"),
        "who_imports": ("bindings", "target"),
    }
    rows_key, selector_key = shapes[suffix]
    offset, total, rows, queries, seen = 0, None, [], [], set()
    state, reason = "partial", "Page budget exhausted"
    for _ in range(max_pages):
        if row_budget is not None and len(rows) >= row_budget:
            capture.stopped = "not_attempted_budget"
            reason = "Dependency row budget exhausted; prior page retained in full"
            break
        arguments = {"directory": str(capture.workspace), "limit": page_size,
                     "offset": offset, "summary": False}
        if selector_key:
            arguments[selector_key] = native_selector(selector)
        try:
            payload, query = await capture.query(suffix, arguments)
        except asyncio.CancelledError:
            if time.monotonic() < capture.deadline:
                raise
            capture.stopped = "not_attempted_deadline"
            reason = capture.stopped
            if capture.queries and capture.queries[-1] not in queries:
                queries.append(capture.queries[-1])
            break
        if query is None:
            reason = capture.stopped
            break
        queries.append(query)
        if query["status"] != "ok":
            reason = "Backend query unavailable/error/unsupported"
            break
        try:
            if not isinstance(payload, dict) or not isinstance(payload.get(rows_key), list):
                raise EvidenceError("Unsupported native page envelope: " + suffix)
            values = payload[rows_key]
            count, current_total = payload.get("returned_match_count"), payload.get("total_match_count")
            if (type(count) is not int or type(current_total) is not int
                    or not 0 <= count <= page_size or current_total < 0
                    or count != len(values) or type(payload.get("offset")) is not int
                    or payload["offset"] != offset or type(payload.get("limit")) is not int
                    or payload["limit"] != page_size or payload.get("summary") is not False
                    or (selector_key and payload.get(selector_key) != selector)
                    or offset + count > current_total or (total is not None and total != current_total)):
                raise EvidenceError("Native pagination gap/total/count drift")
            total = current_total
            identities = [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in values]
            if (not all(isinstance(row, dict) for row in values)
                    or len(set(identities)) != len(identities) or seen.intersection(identities)):
                raise EvidenceError("Repeated native page/row")
            if not count and offset != total:
                raise EvidenceError("Non-progress native page")
            seen.update(identities)
            rows.extend((row, query["id"]) for row in values)
            offset += count
            if offset == total:
                state, reason = "complete", "Count-complete indexed query scope only"
                break
        except EvidenceError as exc:
            query["status"] = "unsupported"
            query["limitations"].append(str(exc))
            reason = str(exc)
            # Preserve malformed-page facts too, but never qualify them through
            # a failed envelope or silently repair their offset/total.
            if isinstance(payload, dict) and isinstance(payload.get(rows_key), list):
                rows.extend((row, query["id"]) for row in payload[rows_key] if isinstance(row, dict))
            break
    pagination = {"status": state if rows or queries else "unknown", "pages": len(queries),
                  "returned": len(rows), "total": total, "reason": reason}
    for query in queries:
        query["pagination"] = dict(pagination)
        if state != "complete" and query["status"] == "ok":
            query["status"] = "partial"
    return rows, queries, pagination


def native_location(data, node, parsed=None):
    """Current native byte/header correspondence, not a full Rust resolver."""
    span, line = node.get("span"), node.get("line")
    if (not isinstance(span, list) or len(span) != 2
            or any(type(n) is not int for n in span) or type(line) is not int
            or not 0 <= span[0] < span[1] <= len(data)):
        raise EvidenceError("Missing/invalid native byte bounds")
    start, end = span
    if data[:start].count(b"\n") + 1 != line:
        raise EvidenceError("Native line does not match current byte position")
    try:
        text, before, selected = data.decode("utf-8"), data[:start].decode("utf-8"), data[start:end].decode("utf-8")
    except UnicodeError:
        raise EvidenceError("Native span splits UTF-8 source") from None
    structure = parsed[0] if parsed else source_ranges._structure(text)
    if structure[2]:
        raise EvidenceError("Unsupported source lexical state")
    tokens = structure[0]
    name = node["qualified_name"].rsplit("::", 1)[-1].removeprefix("r#")
    kind = node.get("item_kind") or node.get("kind")
    expected = {
        "Function": "fn", "Fn": "fn", "Method": "fn", "Struct": "struct",
        "Trait": "trait", "Enum": "enum", "Union": "union", "Module": "mod",
        "TypeAlias": "type", "Type": "type", "Const": "const", "Static": "static",
    }.get(str(kind).removeprefix("Item."))
    if expected is None:
        raise EvidenceError("Unsupported native declaration kind")
    matches = []
    for declaration in (parsed[1] if parsed else source_ranges._declarations(text, structure)):
        index = declaration["token"]
        starts = declaration["doc_starts"] + [declaration["start"], declaration["code_start"]]
        if (declaration["type"] == expected and len(before) in starts
                and declaration["end"] == len(before) + len(selected)
                and index + 1 < len(tokens) and tokens[index + 1].kind == "identifier"
                and tokens[index + 1].text.removeprefix("r#") == name):
            matches.append(declaration)
    if len(matches) != 1:
        raise EvidenceError("Native span/kind/name does not identify one current declaration")
    return {"start_byte": start, "end_byte": end, "start_line": line,
            "end_line": data[:end - 1].count(b"\n") + 1, "column_unit": "utf8_byte"}


class NativeRun:
    """Small capture state; native facts remain separate from current projection."""

    def __init__(self, workspace, directory, inventory_path, protected, limits, initial_inventory_digest):
        self.workspace, self.directory, self.inventory_path = workspace, directory, inventory_path
        self.protected = protected
        self.sources, self.parsed, self.tree, self.by_native, self.by_selector = {}, {}, {}, {}, {}
        self.source_bytes = 0
        self.limits, self.item_queries, self.relation_rows = limits, {}, {}
        self.capture = {
            "schema_version": 1, "kind": "lint-native-dependency-capture", "status": "pending",
            "workspace": str(workspace), "artifact_root": str(directory),
            "orientation": "consumer_to_provider",
            "inventory_sha256": initial_inventory_digest, "captured_at": datetime.now(timezone.utc).isoformat(),
            "target_head": git_head(workspace), "source_files": [],
            "backend": {"server_ref": None, "catalogue_ref": None,
                        "workspace_evidence": {"status": "requested_directory_only",
                                               "requested_workspace": str(workspace)},
                        "snapshot_ids": [], "warnings": [], "coverage": coverage(),
                        "scope": "direct_incoming_outgoing_imports_selected_transverse_items", "context_refs": []},
            "queries": [], "items": [], "diagnostics": [], "dependencies": [],
            "limits": dict(limits), "timing": {"total_seconds": 0.0, "stages": {},
                                             "requests": 0, "reused_queries": 0},
            "limitations": [
                "Native graph coverage/features/tests/macros and global freshness are not proved.",
                "Directory is requested explicitly; native payloads do not independently report an indexed root.",
                "Current endpoint checks do not establish historical diagnostic/source equivalence.",
                "Direct incoming/outgoing/import scopes only; not recursive exhaustive workspace closure.",
                "Candidate native dependencies are not hard co-edit constraints or dispatch authorization.",
            ],
        }
        self.start = time.monotonic()
        self.deadline = self.start + limits["timeout"]
        self.transport = None
        self.stop_reason = None

    def protect(self, path):
        if path.is_relative_to(self.directory):
            raise CaptureIntegrityError("A native source/input aliases the run-artifact directory")
        try:
            verify_output_input_separation(self.protected, [path])
        except EvidenceError as exc:
            raise CaptureIntegrityError(str(exc)) from None

    def source(self, raw):
        name, path = source_path(self.workspace, raw)
        self.protect(path)
        if name not in self.sources:
            if path.stat().st_size > MAX_RESULT_BYTES:
                raise SourcePathError("Native source exceeds per-file byte budget")
            data = path.read_bytes()
            if self.source_bytes + len(data) > MAX_SOURCE_BYTES:
                raise SourcePathError("Native aggregate source byte budget exhausted")
            self.source_bytes += len(data)
            digest = hashlib.sha256(data).hexdigest()
            self.sources[name] = {"path": name, "sha256": digest, "before_sha256": digest,
                                  "after_sha256": None, "status": "pending", "_data": data}
        return name, self.sources[name]

    def item(self, node, query_ids, snapshot):
        native_id = node.get("id")
        if (not isinstance(native_id, list) or not native_id
                or any(type(n) is not int or not 0 <= n <= 255 for n in native_id)):
            raise EvidenceError("Unsupported native ID byte array")
        selector = native_selector(node.get("qualified_name"))
        identity = (snapshot, tuple(native_id))
        if identity in self.by_native:
            current = self.by_native[identity]
            if (current["selector"] != selector
                    or current["native"] != {k: node.get(k) for k in ("file", "span", "line")}):
                current["location_status"] = "candidate"
                current["reasons"].append("Conflicting location/selector for the same native ID")
            current["evidence_refs"] = sorted(set(current["evidence_refs"] + query_ids))
            return current
        entry = {
            "id": f"ni{len(self.capture['items']) + 1:06d}", "native_id": native_id,
            "selector": selector, "kind": node.get("item_kind") or node.get("kind") or "unknown",
            "visibility": self.tree.get(selector, {}).get("visibility"),
            "path": None, "range": None, "location_status": "unknown", "source_sha256": None,
            "snapshot_id": snapshot, "native": {k: node.get(k) for k in ("file", "span", "line")},
            "evidence_refs": sorted(set(query_ids)), "reasons": [],
        }
        self.capture["items"].append(entry)
        self.by_native[identity] = entry
        self.by_selector.setdefault(selector, []).append(entry)
        try:
            name, record = self.source(node.get("file"))
            entry.update(path=name, source_sha256=record["sha256"], location_status="candidate")
            if name not in self.parsed:
                text = record["_data"].decode("utf-8")
                structure = source_ranges._structure(text)
                self.parsed[name] = (structure, source_ranges._declarations(text, structure))
            entry["range"] = native_location(record["_data"], node, self.parsed[name])
            entry["location_status"] = "verified"
        except (SourcePathError, UnicodeError, OSError) as exc:
            entry["reasons"].append(str(exc))
        except EvidenceError as exc:
            # A collision is not a weak endpoint: it is a fatal publication guard.
            if node.get("file") and isinstance(node["file"], str):
                try:
                    _, absolute = source_path(self.workspace, node["file"])
                except EvidenceError:
                    pass
                else:
                    self.protect(absolute)
            entry["reasons"].append(str(exc))
        return entry

    def unlocated(self, selector, refs, reason):
        entry = {
            "id": f"ni{len(self.capture['items']) + 1:06d}", "native_id": None, "selector": selector,
            "kind": self.tree.get(selector, {}).get("kind", "unknown"),
            "visibility": self.tree.get(selector, {}).get("visibility"), "path": None, "range": None,
            "location_status": "unknown", "source_sha256": None, "snapshot_id": None,
            "native": {"file": None, "span": None, "line": None},
            "evidence_refs": sorted(set(refs)), "reasons": [reason],
        }
        self.capture["items"].append(entry)
        return entry

    def unique(self, selector):
        matches = self.by_selector.get(selector, [])
        return matches[0] if len(matches) == 1 else None

    def diagnostic_queue(self, inventory):
        spec = importlib.util.spec_from_file_location(
            "_native_scope_router", Path(__file__).with_name("diagnostic-scope.py"))
        router = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(router)
        routed = router.route_inventory(inventory)
        spans_by_key = {key: spans for key, _, spans in diagnostic_rows(inventory)}
        self.spans = spans_by_key
        for route in routed["diagnostics"]:
            entry = {"diagnostic_key": route["diagnostic_key"], "route": route["scope"],
                     "files": [], "item_ids": [], "query_ids": [], "attempt_outcome": "pending",
                     "localization_status": "unknown", "reasons": []}
            for span in spans_by_key[route["diagnostic_key"]]:
                raw = span.get("file")
                try:
                    name, _ = self.source(raw)
                    entry["files"].append(name)
                except (SourcePathError, OSError) as exc:
                    # Root-invalid or nonexistent diagnostic nodes remain visible.
                    if isinstance(raw, str):
                        entry["files"].append(raw.replace("\\", "/"))
                    entry["reasons"].append(str(exc))
            entry["files"] = sorted(set(entry["files"]))
            if entry["route"] == "local":
                entry["attempt_outcome"] = "skipped_local"
            self.capture["diagnostics"].append(entry)

    def select(self):
        for diagnostic in self.capture["diagnostics"]:
            if diagnostic["route"] == "local":
                continue
            selected = []
            for path in diagnostic["files"]:
                candidates = [i for i in self.capture["items"] if i["path"] == path]
                # Without independent historical source equivalence an old
                # line can fall into a different current item. Keep all file
                # candidates; requests are deduplicated across diagnostics.
                selected.extend(candidates)
            diagnostic["item_ids"] = sorted({i["id"] for i in selected})
            diagnostic["query_ids"] = sorted({ref for i in selected for ref in i["evidence_refs"]})
            if selected:
                diagnostic["localization_status"] = "candidate"
                diagnostic["reasons"].append(
                    "All current file-bound native candidates; no historical source binding asserted")
            else:
                diagnostic["attempt_outcome"] = "unresolved_localization"
                diagnostic["reasons"].append("No positively file-bound native item; discovery is not absence proof")

    async def hydrate(self, selectors):
        pending = sorted({native_selector(s) for s in selectors})
        batch_size = self.limits["hydration_batch_size"]
        for at in range(0, len(pending), batch_size):
            batch = pending[at:at + batch_size]
            if len(self.capture["items"]) >= self.limits["max_items"]:
                self.transport.stopped = "not_attempted_budget"
                self.capture["limitations"].append(f"Item budget: {len(pending) - at} native selectors unexpanded")
                break
            payload, query = await self.transport.query("build_codemap", {
                "directory": str(self.workspace), "seed_qualified_names": batch,
                "depth": 0, "max_nodes": 500, "embedding_policy": "no_rerank",
                "format": "json", "include_snippets": False})
            if query is None:
                break
            refs = [query["id"]]
            found = set()
            try:
                if (query["status"] != "ok" or not isinstance(payload, dict)
                        or not isinstance(payload.get("nodes"), list)
                        or not isinstance(payload.get("edges"), list)
                        or not isinstance(payload.get("snapshot_id"), str) or not payload["snapshot_id"]):
                    raise EvidenceError("Unsupported native node hydration envelope")
                snapshot = payload["snapshot_id"]
                if snapshot not in self.capture["backend"]["snapshot_ids"]:
                    self.capture["backend"]["snapshot_ids"].append(snapshot)
                warnings = payload.get("diagnostics", [])
                if isinstance(warnings, list):
                    self.capture["backend"]["warnings"].extend(str(v) for v in warnings)
                # No edge is inferred from depth zero. Unexpected returned facts
                # are preserved for endpoint resolution rather than discarded.
                for index, node in enumerate(payload["nodes"]):
                    try:
                        if not isinstance(node, dict):
                            raise EvidenceError("Malformed native node")
                        node_refs = refs + self.tree.get(node.get("qualified_name"), {}).get("refs", [])
                        item = self.item(node, node_refs, snapshot)
                        found.add(item["selector"])
                    except CaptureIntegrityError:
                        raise
                    except EvidenceError as exc:
                        query["limitations"].append(f"Unresolved native node {index}: {exc}; raw fact retained")
                for edge in payload["edges"]:
                    self.relation_rows.setdefault(("codemap", snapshot), []).append((edge, query["id"]))
                query["pagination"] = {
                    "status": "not_applicable", "pages": 1, "returned": len(payload["nodes"]),
                    "total": None, "reason": "Depth-zero node hydration, not dependency pagination"}
                if len(payload["nodes"]) >= 500:
                    query["limitations"].append("Native node cap reached; seed correspondence may be incomplete")
            except CaptureIntegrityError:
                raise
            except EvidenceError as exc:
                query["status"] = "unsupported" if query["status"] == "ok" else query["status"]
                query["limitations"].append(str(exc))
            for selector in batch:
                self.item_queries[selector] = refs
                if selector not in found:
                    self.unlocated(selector, refs + self.tree.get(selector, {}).get("refs", []),
                                   "Seed missing/unsupported in native hydration; no guessed location")
            if self.transport.stopped:
                break

    async def discover(self):
        rows, queries, pagination = await native_pages(
            self.transport, "crate_dependency_metric", None,
            self.limits["page_size"], self.limits["max_pages"])
        if pagination["status"] != "complete":
            self.capture["limitations"].append("Crate enumeration incomplete: " + str(pagination["reason"]))
        edges, edge_query = await self.transport.query("crate_edges", {
            "directory": str(self.workspace), "offset": 0,
            "limit": self.limits["page_size"], "summary": False})
        if edge_query:
            self.capture["backend"]["context_refs"].append(edge_query["id"])
            returned = edges.get("returned_match_count") if isinstance(edges, dict) else None
            if type(returned) is not int or returned < 0:
                returned = (len(edges["edges"]) if isinstance(edges, dict)
                            and isinstance(edges.get("edges"), list) else 0)
            edge_query["pagination"] = {
                "status": "partial", "pages": 1,
                "returned": returned,
                "total": edges.get("total_match_count") if isinstance(edges, dict)
                         and type(edges.get("total_match_count")) is int else None,
                "reason": "Single bounded crate-context page; not global crate-edge enumeration",
            }
            edge_query["limitations"].append(
                "Crate edges are bounded context only; all selected item relation sequences are accounted separately")
        crates = set()
        for row, _ in rows:
            try:
                crates.add(native_selector(row.get("crate_name")))
            except EvidenceError:
                self.capture["limitations"].append("Crate metric row lacks a usable selector")
        for crate in sorted(crates):
            payload, query = await self.transport.query("module_tree", {
                "directory": str(self.workspace), "krate": crate})
            if query is None:
                break
            if (query["status"] != "ok" or not isinstance(payload, dict)
                    or not isinstance(payload.get("tree"), dict)):
                query["limitations"].append("Unusable full module tree; no fabricated children")
                continue
            stack = [payload["tree"]]
            visited = 0
            while stack:
                node = stack.pop()
                visited += 1
                if visited > self.limits["max_items"]:
                    query["limitations"].append("Module tree item budget; unexpanded subtree retained in raw capture")
                    self.transport.stopped = "not_attempted_budget"
                    break
                try:
                    selector = native_selector(node.get("qualified_name"))
                    children = node.get("children")
                    if not isinstance(children, list) or not all(isinstance(c, dict) for c in children):
                        raise EvidenceError("Unsupported native tree children")
                except EvidenceError as exc:
                    query["limitations"].append(str(exc))
                    continue
                current = self.tree.setdefault(selector, {
                    "kind": node.get("item_kind") or node.get("kind") or "unknown",
                    "visibility": node.get("visibility"), "refs": []})
                current["refs"] = sorted(set(current["refs"] + [query["id"]]))
                if current["visibility"] is None:
                    current["visibility"] = node.get("visibility")
                stack.extend(reversed(children))
            query["pagination"] = {"status": "not_applicable", "pages": 1, "returned": visited,
                                   "total": None, "reason": "Uncapped recursive tree; no cursor or completeness proof"}
    async def relations(self):
        self.pre_relation_sources = set(self.sources)
        selected_ids = {identifier for d in self.capture["diagnostics"] for identifier in d["item_ids"]}
        selected = [item for item in self.capture["items"] if item["id"] in selected_ids]
        served = {}
        for item in selected:
            selector = item["selector"]
            if selector in served:
                continue
            query_ids, attempted = [], False
            for suffix in ("who_uses", "calls_from", "who_imports"):
                kinds = {str(i["kind"]).removeprefix("Item.") for i in selected if i["selector"] == selector}
                if suffix == "calls_from" and not kinds.intersection({"Function", "Fn", "Method"}):
                    item["reasons"].append("calls_from not applicable to this non-function native kind")
                    continue
                if len(self.capture["dependencies"]) >= self.limits["max_dependencies"]:
                    self.transport.stopped = "not_attempted_budget"
                    break
                remaining = self.limits["max_dependencies"] - sum(len(rows) for rows in self.relation_rows.values())
                if remaining <= 0:
                    self.transport.stopped = "not_attempted_budget"
                    break
                rows, queries, pagination = await native_pages(
                    self.transport, suffix, selector, self.limits["page_size"], self.limits["max_pages"], remaining)
                attempted |= any(q["status"] in ("ok", "partial") for q in queries)
                query_ids.extend(q["id"] for q in queries)
                self.relation_rows[(suffix, selector)] = rows
                if pagination["status"] != "complete":
                    self.capture["limitations"].append(f"{suffix} {selector}: {pagination['reason']}")
                if self.transport.stopped:
                    break
            served[selector] = {"query_ids": query_ids, "attempted": attempted,
                                "outcome": self.transport.stopped or ("queried" if attempted else "unavailable_backend")}
            if self.transport.stopped:
                break
        # Only direct returned endpoint selectors are hydrated. This is not
        # recursive relation expansion and does not alter the diagnostic queue.
        endpoint_selectors = set()
        for (suffix, _), rows in self.relation_rows.items():
            for row, _ in rows:
                fields = (("consumer_function", "consumer_module") if suffix == "who_uses" else
                          ("callee_qualified_name",) if suffix == "calls_from" else
                          ("from_module",) if suffix == "who_imports" else ())
                for field in fields:
                    if field in row:
                        try:
                            endpoint_selectors.add(native_selector(row[field]))
                        except EvidenceError:
                            pass
        known = set(self.item_queries) | {i["selector"] for i in self.capture["items"] if i["native_id"]}
        missing = endpoint_selectors - known
        if missing and not self.transport.stopped:
            await self.hydrate(missing)
        self.dependencies()
        assigned = set()
        assignments = 0
        for diagnostic in self.capture["diagnostics"]:
            if diagnostic["route"] == "local":
                continue
            selectors = sorted({i["selector"] for i in selected if i["id"] in diagnostic["item_ids"]})
            outcomes = [served[s] for s in selectors if s in served]
            ids = sorted({q for outcome in outcomes for q in outcome["query_ids"]})
            diagnostic["query_ids"] = sorted(set(diagnostic["query_ids"] + ids))
            if not selectors:
                if self.transport.stopped:
                    diagnostic["attempt_outcome"] = self.transport.stopped
                continue
            if len(outcomes) != len(selectors) or any(o["outcome"].startswith("not_attempted") for o in outcomes):
                diagnostic["attempt_outcome"] = self.transport.stopped or "not_attempted_budget"
            elif any(o["attempted"] for o in outcomes):
                diagnostic["attempt_outcome"] = "reused_query" if set(ids) <= assigned else "queried"
            else:
                diagnostic["attempt_outcome"] = "unavailable_backend"
            for identifier in set(ids) & assigned:
                query = next(q for q in self.transport.queries if q["id"] == identifier)
                query["reused_count"] += 1
                assignments += 1
            assigned.update(ids)
        self.capture["timing"]["reused_query_assignments"] = assignments

    def dependencies(self):
        for (suffix, selector), rows in self.relation_rows.items():
            for row, query_id in rows:
                reasons, origin, destination, origin_path, destination_path = [], None, None, None, None
                native_origin, native_destination = {}, {}
                source_ok = False
                if not isinstance(row, dict):
                    row = {"unsupported_row": row}
                try:
                    if suffix == "codemap":
                        def by_id(value):
                            return self.by_native.get((selector, tuple(value))) if isinstance(value, list) else None
                        origin, destination = by_id(row.get("from")), by_id(row.get("to"))
                        native_origin, native_destination = {"id": row.get("from")}, {"id": row.get("to")}
                        source_ok = True
                        reasons.append("Unexpected depth-zero edge retained as backend context, not a paginated relation")
                    else:
                        target = self.unique(selector)
                        if suffix == "who_imports":
                            if row.get("target") != selector:
                                raise EvidenceError("Importer row target mismatch")
                            native_selector(row.get("from_module"))
                            origin, destination = self.unique(row.get("from_module")), target
                            native_origin = {"selector": row.get("from_module")}
                            native_destination = {"selector": selector}
                            source_ok = True
                        else:
                            caller = row.get("consumer_function") if suffix == "who_uses" else selector
                            callee = selector if suffix == "who_uses" else row.get("callee_qualified_name")
                            if caller is not None:
                                native_selector(caller)
                            native_selector(callee)
                            if suffix == "calls_from" and row.get("caller_qualified_name") != selector:
                                raise EvidenceError("Outgoing row caller mismatch")
                            origin, destination = self.unique(caller), self.unique(callee)
                            native_origin = {"selector": caller, "module": row.get("consumer_module"),
                                             "file": row.get("file"), "span": [row.get("start"), row.get("end")]}
                            native_destination = {"selector": callee}
                            name, source = self.source(row.get("file"))
                            origin_path = name
                            start, end = row.get("start"), row.get("end")
                            if (type(start) is not int or type(end) is not int
                                    or not 0 <= start < end <= len(source["_data"])
                                    or not isinstance(callee, str)
                                    or source["_data"][start:end].decode("utf-8") != callee.rsplit("::", 1)[-1]):
                                raise EvidenceError("Reference byte bounds/spelling mismatch; no repair")
                            if origin and (origin["path"] != name or not origin["range"]
                                           or not origin["range"]["start_byte"] <= start < end <= origin["range"]["end_byte"]):
                                reasons.append("Reference site does not establish advertised caller identity")
                                origin = None
                            source_ok = True
                    origin_path = origin_path or (origin["path"] if origin else None)
                    destination_path = destination["path"] if destination else None
                except (SourcePathError, UnicodeError) as exc:
                    reasons.append(str(exc))
                except EvidenceError as exc:
                    # Recheck protection separately: collisions are never
                    # downgraded into ordinary backend-observed endpoints.
                    if isinstance(row.get("file"), str):
                        try:
                            _, absolute = source_path(self.workspace, row["file"])
                        except EvidenceError:
                            pass
                        else:
                            self.protect(absolute)
                    reasons.append(str(exc))
                origin_path = origin_path or (origin["path"] if origin else None)
                destination_path = destination_path or (destination["path"] if destination else None)
                if any(path and path not in getattr(self, "pre_relation_sources", set())
                       for path in (origin_path, destination_path)):
                    reasons.append("Endpoint first hashed after relation queries; no pre-query source stability")
                endpoint_checks = bool(destination and destination["location_status"] == "verified"
                                       and (origin is None and suffix == "who_uses"
                                            or origin and origin["location_status"] == "verified"))
                query = next(q for q in self.transport.queries if q["id"] == query_id)
                if query["status"] not in ("ok", "partial"):
                    reasons.append("Raw relation page failed envelope/pagination validation")
                qualification = ("source_verified" if source_ok and endpoint_checks and not reasons else
                                 "backend_observed" if origin_path and destination_path else "unresolved")
                if qualification != "source_verified" and not reasons:
                    reasons.append("Native endpoint identity/current declaration is missing or ambiguous")
                kind = row.get("kind", "Uses" if suffix == "who_uses" else
                               "CallsFrom" if suffix == "calls_from" else "Imports")
                if not isinstance(kind, str) or not kind:
                    kind = "unknown"
                self.capture["dependencies"].append({
                    "id": f"nd{len(self.capture['dependencies']) + 1:06d}",
                    "kind": kind,
                    "origin_item_id": origin["id"] if origin else None,
                    "destination_item_id": destination["id"] if destination else None,
                    "origin_path": origin_path, "destination_path": destination_path,
                    "native_origin": native_origin, "native_destination": native_destination,
                    "native": row, "evidence_refs": [query_id], "qualification": qualification, "reasons": reasons,
                    "snapshot_ids": sorted({i["snapshot_id"] for i in (origin, destination)
                                             if i and i["snapshot_id"]}),
                })

    def finalize(self):
        for name, record in self.sources.items():
            try:
                _, path = source_path(self.workspace, name)
                self.protect(path)
                record["after_sha256"] = sha256(path)
                record["status"] = "verified" if record["after_sha256"] == record["before_sha256"] else "changed"
            except (SourcePathError, OSError):
                record["status"] = "missing"
            if record["status"] != "verified":
                for item in self.capture["items"]:
                    if item["path"] == name:
                        item["location_status"] = "candidate"
                        item["reasons"].append("Source changed/disappeared during capture")
                for diagnostic in self.capture["diagnostics"]:
                    if name in diagnostic["files"] and diagnostic["route"] != "local":
                        diagnostic.update(attempt_outcome="source_invalid", localization_status="source_invalid")
                for dependency in self.capture["dependencies"]:
                    if name in (dependency["origin_path"], dependency["destination_path"]):
                        dependency["qualification"] = (
                            "unresolved" if record["status"] == "missing" else "backend_observed")
                        dependency["reasons"].append("Endpoint source changed/disappeared during capture")
        self.capture["source_files"] = [{k: v for k, v in r.items() if not k.startswith("_")}
                                        for _, r in sorted(self.sources.items())]
        if self.transport:
            self.capture["queries"] = self.transport.queries
            self.capture["timing"].update(
                requests=self.transport.requests, query_records=len(self.transport.queries),
                cache_hits=self.transport.reused,
                reused_queries=self.transport.reused + self.capture["timing"].get("reused_query_assignments", 0))
        self.capture["timing"]["total_seconds"] = max(0.0, time.monotonic() - self.start)


def native_artifact_path(directory, raw):
    """Raw reference authority is the explicit run root, never a captured root."""
    if (not isinstance(raw, str) or not raw or raw.startswith(("/", "\\"))
            or "\\" in raw or ":" in raw or any(part in ("", ".", "..") for part in raw.split("/"))):
        raise EvidenceError("Native artifact reference must be a normalized relative path")
    try:
        _, path = source_path(directory, raw)
    except SourcePathError as exc:
        raise EvidenceError("Invalid run-root artifact reference: " + str(exc)) from None
    return path


async def collect_native_dependencies(
        workspace, inventory_path, artifacts, *,
        url=DEFAULT_URL, timeout=1800, max_queries=20000, max_pages=128,
        page_size=100, hydration_batch_size=400, max_items=100000,
        max_dependencies=500000, protected_paths=()):
    """Capture direct native neighborhoods for every transverse inventory record."""
    workspace = validate_workspace(workspace)
    url = validate_url(url)
    limits = {
        "timeout": timeout, "max_queries": max_queries, "max_pages": max_pages,
        "page_size": page_size, "hydration_batch_size": hydration_batch_size,
        "max_items": max_items, "max_dependencies": max_dependencies,
    }
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or not 1 <= timeout <= 86400:
        raise EvidenceError("Native deadline must be finite within 1..86400 seconds")
    for name, maximum in (("max_queries", 1000000), ("max_pages", 10000), ("page_size", 200),
                          ("hydration_batch_size", 500), ("max_items", 1000000),
                          ("max_dependencies", 5000000)):
        if type(limits[name]) is not int or not 1 <= limits[name] <= maximum:
            raise EvidenceError("Native budget outside allowed bounds: " + name)
    inventory_path = Path(inventory_path).resolve(strict=True)
    inventory, initial_inventory_digest = read_native_inventory(inventory_path)
    raw_directory = Path(artifacts).absolute()
    for ancestor in (raw_directory, *raw_directory.parents):
        if ancestor.is_symlink() or (hasattr(ancestor, "is_junction") and ancestor.is_junction()):
            raise EvidenceError("Run-artifact directory cannot use a symlink/junction alias")
    directory = raw_directory.resolve()
    protected = tuple(Path(p).resolve() for p in protected_paths)
    if (directory.exists() or workspace.is_relative_to(directory)
            or inventory_path.is_relative_to(directory)
            or any(p.is_relative_to(directory) for p in protected)):
        raise EvidenceError("Run-artifact directory must be new, distinct and not contain inputs/outputs/source root")
    verify_output_input_separation(protected, [inventory_path, Path(__file__).resolve()])
    run = NativeRun(workspace, directory, inventory_path, protected, limits, initial_inventory_digest)
    run.diagnostic_queue(inventory)
    directory.mkdir(parents=False, exist_ok=False)
    manifest_path = directory / "run-manifest.json"
    atomic_json(manifest_path, {"schema_version": 1, "kind": "lint-native-capture-run",
                               "status": "pending", "workspace": str(workspace),
                               "inventory_sha256": run.capture["inventory_sha256"],
                               "limits": limits})
    fatal = None
    try:
        async with asyncio.timeout_at(run.deadline):
            async with connect(url, timeout) as session:
                server = as_json((await session.initialize()).serverInfo)
                tools = await catalog(session)
                for name, data in (("server.json", server), ("catalogue.json", tools)):
                    path = directory / name
                    atomic_json(path, data)
                    key = "server_ref" if name == "server.json" else "catalogue_ref"
                    run.capture["backend"][key] = {"path": name, "sha256": sha256(path)}
                run.transport = NativeCapture(session, tools, workspace, directory, max_queries, run.deadline)
                async def stage(name, operation):
                    start = time.monotonic()
                    try:
                        return await operation
                    finally:
                        run.capture["timing"]["stages"][name] = time.monotonic() - start
                await stage("native_discovery", run.discover())
                if not run.transport.stopped:
                    await stage("initial_hydration", run.hydrate(run.tree))
                start = time.monotonic()
                run.select()
                run.capture["timing"]["stages"]["selection"] = time.monotonic() - start
                await stage("direct_relations", run.relations())
    except TimeoutError:
        run.stop_reason = "not_attempted_deadline"
        if run.transport:
            run.transport.stopped = run.stop_reason
        run.capture["limitations"].append("Whole-operation deadline exhausted")
    except EvidenceError as exc:
        fatal = exc
        run.capture["limitations"].append(str(exc))
    except Exception as exc:
        run.capture["limitations"].append("Backend/session unavailable: " + type(exc).__name__)
    try:
        if run.transport and run.relation_rows and not run.capture["dependencies"]:
            run.dependencies()
        for diagnostic in run.capture["diagnostics"]:
            if diagnostic["attempt_outcome"] == "pending":
                diagnostic["attempt_outcome"] = (
                    run.stop_reason or (run.transport.stopped if run.transport else None) or "unavailable_backend")
                diagnostic["reasons"].append("Capture ended before this diagnostic's relation scope completed")
        run.finalize()
        if sha256(inventory_path) != initial_inventory_digest:
            raise EvidenceError("Inventory changed during native collection")
        if git_head(workspace) != run.capture["target_head"]:
            run.capture["limitations"].append("Target HEAD changed; no current global identity is asserted")
        for query in run.capture["queries"]:
            if sha256(native_artifact_path(directory, query["artifact"])) != query["artifact_sha256"]:
                raise EvidenceError("Native query artifact changed before publication")
        for key in ("server_ref", "catalogue_ref"):
            ref = run.capture["backend"][key]
            if ref and sha256(native_artifact_path(directory, ref["path"])) != ref["sha256"]:
                raise EvidenceError("Native backend metadata changed before publication")
    except EvidenceError as exc:
        fatal = exc
        run.capture["limitations"].append(str(exc))
    incomplete = (fatal is not None or not run.transport or bool(run.transport.stopped)
                  or any(q["status"] != "ok" or q["limitations"] for q in run.capture["queries"])
                  or any(d["route"] == "transverse" and d["attempt_outcome"] not in ("queried", "reused_query")
                         for d in run.capture["diagnostics"])
                  or any(s["status"] != "verified" for s in run.capture["source_files"]))
    run.capture["status"] = "failed" if fatal else "partial" if incomplete else "complete"
    run.capture["backend"]["warnings"] = sorted(set(run.capture["backend"]["warnings"]))
    if any(i["visibility"] not in (None, "pub") for i in run.capture["items"]):
        run.capture["backend"]["coverage"]["private"] = "observed"
    run.capture["limits"].update(
        observed_items=len(run.capture["items"]), observed_dependencies=len(run.capture["dependencies"]),
        max_source_file_bytes=MAX_RESULT_BYTES, max_source_bytes=MAX_SOURCE_BYTES,
        pending_diagnostics=sum(d["attempt_outcome"].startswith("not_attempted") for d in run.capture["diagnostics"]))
    if directory.resolve() != directory or directory.is_symlink():
        raise CaptureIntegrityError("Run-artifact root changed into an alias during collection")
    atomic_json(directory / "native-capture.json", run.capture)
    atomic_json(manifest_path, {"schema_version": 1, "kind": "lint-native-capture-run",
                               "status": run.capture["status"], "workspace": str(workspace),
                               "capture": {"path": "native-capture.json", "sha256": sha256(directory / "native-capture.json")},
                               "timing": run.capture["timing"]})
    if fatal:
        raise fatal
    return run.capture


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=60,
                        help="Whole-operation deadline in seconds (1..300)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("catalog", "collect"):
        command = sub.add_parser(name)
        command.add_argument("--output", help="Atomic accepted evidence JSON")
        command.add_argument("--report", help="Separate failure-only diagnostic JSON")
        if name == "collect":
            command.add_argument("--requests", required=True, type=Path)
            command.add_argument("--workspace", required=True)
    producer = sub.add_parser("produce", help="Capture source-bound planner evidence")
    producer.add_argument("--inventory", required=True, type=Path)
    producer.add_argument("--plan", required=True, type=Path)
    producer.add_argument("--workspace", required=True)
    producer.add_argument("--snapshot", required=True)
    producer.add_argument("--output", required=True)
    producer.add_argument("--observations", help="Optional separately hash-bound file observations JSON")
    producer.add_argument("--artifacts", required=True, type=Path)
    producer.add_argument("--binding", type=Path)
    producer.add_argument("--context", type=Path, action="append", default=[],
                          help="Snapshot-bind explicit local review/mapping context or policy text (repeatable)")
    producer.add_argument("--source-equivalence", type=Path)
    producer.add_argument("--source-equivalence-sha256")
    producer.add_argument("--serena-url")
    producer.add_argument("--max-queries", type=int, default=128)
    producer.add_argument("--max-sources", type=int, default=512)
    producer.add_argument("--max-pages", type=int, default=8)
    producer.add_argument("--page-size", type=int, default=50)
    producer.add_argument("--allow-partial", action="store_true",
                          help="Explicitly export partial/error query observations, never exhaustive closure")
    args = parser.parse_args(argv)
    if args.command == "produce":
        return producer_main(args)
    evidence = {"format_version": 1, "status": "pending",
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "server": None, "workspace": None, "requests": []}
    report = None
    try:
        args.url = validate_url(args.url)
        if not math.isfinite(args.timeout) or not 1 <= args.timeout <= 300:
            raise EvidenceError("timeout must be finite and within 1..300 seconds")
        protected = {Path(__file__).resolve()}
        if args.command == "collect":
            protected.add(args.requests.resolve())
        output = output_path(args.output, protected)
        report = output_path(args.report, protected | ({output} if output else set()))
        manifest = read_manifest(args.requests, validate_workspace(args.workspace)) if args.command == "collect" else None
        evidence.update(url=args.url, workspace=manifest["workspace"] if manifest else None)
        asyncio.run(run(args, manifest, evidence))
        if output:
            atomic_json(output, evidence)
        else:
            print(json.dumps(evidence, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as exc:
        # Exception strings from untrusted servers can contain secrets or arbitrary
        # text. Retain raw tool errors in the explicit report, not stderr.
        evidence.update(status="failed", failure={
            "type": type(exc).__name__,
            "message": str(exc) if isinstance(exc, EvidenceError) else
            "Operation failed; inspect server availability, permissions, and deadline",
        })
        print(f"mcp-code-evidence: {evidence['failure']['message']}", file=sys.stderr)
        if report:
            try:
                atomic_json(report, evidence)
            except Exception:
                print("mcp-code-evidence: could not write failure report", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
