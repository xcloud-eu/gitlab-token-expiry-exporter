#!/usr/bin/env python3
"""Expose GitLab group/project access token expiry as Prometheus metrics."""
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API = os.environ.get("GITLAB_API", "https://gitlab.com/api/v4").rstrip("/")
GROUPS = [g.strip() for g in os.environ.get("GITLAB_GROUPS", "").split(",") if g.strip()]
TOKEN = os.environ.get("GITLAB_READ_TOKEN", "")
PORT = int(os.environ.get("PORT", "3000"))
WEB = API.rsplit("/api/v4", 1)[0]
HTTP_TIMEOUT = 30

_lock = threading.Lock()
_body = None


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def refresh_seconds():
    try:
        hours = float(os.environ.get("REFRESH_HOURS", ""))
    except ValueError:
        hours = 0.0
    if not 0.25 <= hours <= 168:
        hours = 4.0
    return hours * 3600


def next_link(header):
    for part in header.split(","):
        if 'rel="next"' in part:
            start, end = part.find("<"), part.find(">")
            if 0 <= start < end:
                return part[start + 1:end]
    return ""


def paged(path):
    """Yield every item of a GitLab collection, following the Link header."""
    sep = "&" if "?" in path else "?"
    url = f"{API}/{path}{sep}per_page=100"
    while url:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            items = json.load(resp)
            link = resp.headers.get("Link", "")
        yield from items
        url = next_link(link)


def esc(value):
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return text.replace("\n", " ")


def days_remaining(expires_at, now):
    try:
        expires = datetime.strptime(expires_at, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            expires = datetime.fromisoformat(expires_at)
        except ValueError:
            return None
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    return (expires - now).days


def token_rows(prefix, kind, path, web_url, now):
    rows = []
    for token in paged(f"{prefix}/access_tokens"):
        if not token.get("expires_at"):
            continue
        days = days_remaining(token["expires_at"], now)
        if days is None:
            continue
        labels = [
            ("name", token.get("name", "")),
            ("id", token.get("id", "")),
            ("type", kind),
            (kind, path),
            ("active", str(bool(token.get("active"))).lower()),
            ("revoked", str(bool(token.get("revoked"))).lower()),
            ("scopes", ",".join(token.get("scopes") or [])),
            ("expires_at", token["expires_at"]),
            ("web_url", web_url),
        ]
        if token.get("access_level") is not None:
            labels.append(("access_level", token["access_level"]))
        rows.append((",".join(f'{k}="{esc(v)}"' for k, v in labels), days))
    return rows


def group_targets(group_path):
    """Return (targets, errors) for one top group, its subgroups and projects."""
    group = urllib.parse.quote(group_path, safe="")
    targets = [(f"groups/{group}", "group", group_path, f"{WEB}/groups/{group_path}")]
    errors = 0
    try:
        for sub in paged(f"groups/{group}/descendant_groups"):
            targets.append((f"groups/{sub['id']}", "group", sub["full_path"], sub["web_url"]))
    except Exception as exc:
        log(f"WARN: subgroup listing failed for {group_path}: {exc}")
        errors += 1
    projects = f"groups/{group}/projects?include_subgroups=true&archived=false&simple=true"
    try:
        for project in paged(projects):
            targets.append(
                (f"projects/{project['id']}", "project",
                 project["path_with_namespace"], project["web_url"])
            )
    except Exception as exc:
        log(f"WARN: project listing failed for {group_path}: {exc}")
        errors += 1
    return targets, errors


def scan(now):
    """Return (rows, errors) across all configured groups."""
    targets, errors = [], 0
    for group_path in GROUPS:
        group_found, group_errors = group_targets(group_path)
        targets += group_found
        errors += group_errors
    rows = []
    for prefix, kind, path, web_url in targets:
        try:
            rows += token_rows(prefix, kind, path, web_url, now)
        except Exception as exc:
            log(f"WARN: token listing failed for {path}: {exc}")
            errors += 1
    return rows, errors


def render(rows, errors, scanned_at):
    lines = ["# TYPE gitlab_token_days_remaining gauge"]
    for labels, days in sorted(rows, key=lambda row: row[1]):
        lines.append(f"gitlab_token_days_remaining{{{labels}}} {days}")
    lines += [
        "# TYPE gitlab_tokens_exporter_scan_errors gauge",
        f"gitlab_tokens_exporter_scan_errors {errors}",
        "# TYPE gitlab_tokens_exporter_last_scan_timestamp gauge",
        f"gitlab_tokens_exporter_last_scan_timestamp {scanned_at}",
    ]
    return "\n".join(lines) + "\n"


def refresh(state):
    global _body
    rows, errors = scan(datetime.now(timezone.utc))
    if errors:
        # keep the last complete result: dropping series would resolve firing
        # token alerts, and a frozen timestamp is what the Stale alert detects
        rows = state["rows"]
    else:
        state["rows"] = rows
        state["scanned_at"] = int(time.time())
    body = render(rows, errors, state["scanned_at"])
    with _lock:
        _body = body
    log(f"scan done: {len(rows)} tokens, {errors} errors")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = 15

    def do_GET(self):
        if self.path.split("?")[0] != "/metrics":
            self.respond(200, "text/plain", b"ok\n")
            return
        with _lock:
            body = _body
        if body is None:
            self.respond(503, "text/plain", b"no scan yet\n")
            return
        self.respond(200, "text/plain; version=0.0.4", body.encode())

    def respond(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def main():
    if not TOKEN:
        log("ERROR: GITLAB_READ_TOKEN is required")
        sys.exit(2)
    if not GROUPS:
        log("ERROR: GITLAB_GROUPS is required (comma-separated group paths)")
        sys.exit(2)
    interval = refresh_seconds()
    state = {"rows": [], "scanned_at": 0}

    def loop():
        while True:
            try:
                refresh(state)
            except Exception as exc:
                log(f"ERROR: scan aborted: {exc}")
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
