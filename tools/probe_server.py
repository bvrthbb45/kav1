#!/usr/bin/env python3
"""Kav1 - live server probe v2 (standalone, stdlib only, Python 3.8+).

Black-box check of a RUNNING Kav1 server. It needs no access to the server's code:
it talks to it over HTTP like a browser, so it works even when the deployed version
differs from the repository.

It answers: does the server freeze (stall) while it is being used, which endpoints are
slow, is the login check slow, and (Windows, server on this machine) is the server process
short of CPU / memory / connections.

  1. reads /openapi.json to list the endpoints (FastAPI publishes it),
  2. optionally LOGS IN (so the real pages can be measured - without a login every real
     endpoint just answers 401 "not logged in"),
  3. times a trivial request 20 times (is the server itself responsive?),
  4. times every harmless parameter-less GET endpoint (heavy / risky ones such as backup,
     export, download, logout are never called),
  5. WATCHES the server for 60 seconds while YOU use the system normally: one probe checks
     the server's responsiveness, a second one times a real data page; every slow answer
     is recorded as a stall.

The result is shown as console pages (photograph each one). Only GET requests are sent,
apart from the one login request you agree to. Nothing is written to the database
except what a login normally writes (a session row / audit entry).

Your password is typed hidden, sent only to the server address you typed, never printed
and never saved. A pasted header (--header) is not saved either.

Usage:
  python probe_server.py                         # asks for the address, offers a login
  python probe_server.py --url localhost:3000 --seconds 90 --user myuser
  python probe_server.py --header "Authorization: Bearer ..."
  python probe_server.py --include-heavy         # also call backup/export-like endpoints (not advised)
"""

import argparse
import getpass
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

TOOL_VERSION = "2.0"
WIDTH = 100
STALL_MS = 1000.0
TIMEOUT_S = 15
# Endpoints whose name suggests side effects or heavy work are skipped unless --include-heavy
HEAVY_WORDS = (
    "backup",
    "export",
    "download",
    "restore",
    "reset",
    "logout",
    "delete",
    "shutdown",
    "restart",
    "purge",
    "clear",
    "import",
    "excel",
    "pdf",
    "zip",
)
SWEEP_BUDGET_S = 75


# --------------------------------------------------------------------------- console
def setup_console():
    if os.name == "nt":
        try:
            os.system("chcp 65001 >nul 2>nul")
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def interactive():
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def say(line=""):
    print(line)
    sys.stdout.flush()


def ask(prompt, default=""):
    if not interactive():
        return default
    try:
        return input(prompt).strip() or default
    except EOFError:
        return default


def clear_screen():
    if interactive():
        os.system("cls" if os.name == "nt" else "clear")


def bar(char="="):
    return char * WIDTH


def wrap(text, indent="", first=""):
    return textwrap.wrap(
        text, WIDTH, initial_indent=first, subsequent_indent=indent
    ) or [""]


def ascii_only(text):
    return "".join(ch if ord(ch) < 128 else "?" for ch in str(text))


# --------------------------------------------------------------------------- http
JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))


def normalize_url(text):
    text = text.strip().rstrip("/")
    if not text:
        text = "localhost:3000"
    if not re.match(r"^https?://", text, re.I):
        text = "http://" + text
    return text


def fetch(base, path, headers, timeout=TIMEOUT_S, data=None, method=None):
    """(status, ms, bytes, error, body). Never raises. Cookies are kept (login)."""
    req = urllib.request.Request(base + path, headers=headers, data=data, method=method)
    t0 = time.perf_counter()
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, (time.perf_counter() - t0) * 1000, len(body), None, body
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, (time.perf_counter() - t0) * 1000, len(body), None, body
    except Exception as e:  # timeout, refused, reset ...
        return None, (time.perf_counter() - t0) * 1000, 0, str(e)[:60], b""


def pct(values, p):
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(round((len(v) - 1) * p / 100.0)))]


# --------------------------------------------------------------------------- login
def _schema_props(spec, schema):
    """Property names of a (possibly $ref) request-body schema."""
    if not schema:
        return []
    if "$ref" in schema:
        node = spec
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node.get(part, {})
        schema = node
    return list(schema.get("properties", {}).keys())


def find_login(spec):
    """(path, content_type, user_field, pass_field) from the OpenAPI document."""
    best = None
    for path, item in (spec or {}).get("paths", {}).items():
        op = item.get("post")
        if not op or "login" not in path.lower():
            continue
        content = (op.get("requestBody") or {}).get("content", {})
        for ctype in (
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        ):
            if ctype in content:
                props = _schema_props(spec, content[ctype].get("schema"))
                user = next(
                    (
                        p
                        for p in props
                        if p.lower() in ("username", "user", "email", "login", "name")
                    ),
                    "username",
                )
                pw = next((p for p in props if "pass" in p.lower()), "password")
                cand = (path, ctype, user, pw)
                if best is None or path.lower().endswith("/auth/login"):
                    best = cand
                break
    return best


def do_login(base, headers, spec, username, password):
    """Log in. Returns (ok, note). Updates `headers` with a token when the answer has one."""
    found = find_login(spec)
    if not found:
        return False, "no login endpoint found in the API description"
    path, ctype, ufield, pfield = found
    if ctype == "application/json":
        data = json.dumps({ufield: username, pfield: password}).encode()
    else:
        data = urllib.parse.urlencode({ufield: username, pfield: password}).encode()
    h = dict(headers)
    h["Content-Type"] = ctype
    status, ms, _, err, body = fetch(base, path, h, data=data, method="POST")
    password = None
    if err:
        return False, "login request failed: %s" % err
    if status is None or status >= 400:
        return False, "login refused (HTTP %s)" % status
    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        payload = {}
    token = None
    if isinstance(payload, dict):
        for key in ("access_token", "token", "jwt", "session_token"):
            if isinstance(payload.get(key), str):
                token = payload[key]
                break
    if token:
        headers["Authorization"] = "Bearer " + token
    return True, "logged in via %s (%s, %.0f ms)%s" % (
        path,
        "token" if token else "cookie",
        ms,
        "",
    )


# --------------------------------------------------------------------------- process sampling (Windows)
def run_cmd(args, timeout=10):
    try:
        out = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.stdout
    except Exception:
        return ""


def find_server_pid(port):
    if os.name != "nt":
        return None
    for line in run_cmd(["netstat", "-ano", "-p", "tcp"]).splitlines():
        parts = line.split()
        if (
            len(parts) >= 5
            and parts[3] == "LISTENING"
            and parts[1].endswith(":%d" % port)
        ):
            try:
                return int(parts[4])
            except ValueError:
                pass
    return None


def connection_counts(port):
    counts = {}
    if os.name != "nt":
        return counts
    for line in run_cmd(["netstat", "-ano", "-p", "tcp"]).splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1].endswith(":%d" % port):
            counts[parts[3]] = counts.get(parts[3], 0) + 1
    return counts


def sample_process(pid):
    """(cpu_seconds, working_set_bytes, threads, handles) or None."""
    if os.name != "nt" or not pid:
        return None
    ps = (
        "$p=Get-Process -Id %d -ErrorAction Stop;"
        "[string]::Join(';',@($p.CPU,$p.WorkingSet64,$p.Threads.Count,$p.HandleCount))"
        % pid
    )
    out = (
        run_cmd(["powershell", "-NoProfile", "-Command", ps]).strip().replace(",", ".")
    )
    try:
        cpu, mem, thr, hnd = out.split(";")
        return float(cpu), int(float(mem)), int(float(thr)), int(float(hnd))
    except ValueError:
        return None


class Sampler(threading.Thread):
    def __init__(self, port, pid):
        super().__init__(daemon=True)
        self.port, self.pid = port, pid
        self.rows, self.conn_max, self.stop_flag = [], {}, threading.Event()

    def run(self):
        last = None
        while not self.stop_flag.is_set():
            t = time.time()
            s = sample_process(self.pid)
            if s:
                cpu_pct = None
                if last:
                    dt = t - last[0]
                    cpu_pct = (s[0] - last[1]) / dt * 100.0 if dt > 0 else None
                last = (t, s[0])
                self.rows.append(
                    {
                        "t": t,
                        "cpu_pct": cpu_pct,
                        "mem": s[1],
                        "threads": s[2],
                        "handles": s[3],
                    }
                )
            for state, n in connection_counts(self.port).items():
                self.conn_max[state] = max(self.conn_max.get(state, 0), n)
            self.stop_flag.wait(2.0)


# --------------------------------------------------------------------------- watch
class Watcher(threading.Thread):
    def __init__(self, base, headers, path, interval):
        super().__init__(daemon=True)
        self.base, self.headers, self.path, self.interval = (
            base,
            headers,
            path,
            interval,
        )
        self.samples, self.stop_flag = [], threading.Event()

    def run(self):
        t_start = time.time()
        while not self.stop_flag.is_set():
            status, ms, _, err, _ = fetch(self.base, self.path, self.headers)
            self.samples.append(
                {
                    "at": time.time() - t_start,
                    "ms": ms,
                    "ok": err is None and status is not None and status < 500,
                    "status": status,
                    "err": err
                    or ("HTTP %s" % status if status and status >= 500 else None),
                }
            )
            self.stop_flag.wait(self.interval)


# --------------------------------------------------------------------------- the probe
def is_heavy(path):
    low = path.lower()
    return any(w in low for w in HEAVY_WORDS)


def probe(args, R):
    base = normalize_url(args.url or ask("Server address (Enter = localhost:3000): "))
    R["base"] = base
    headers = {"User-Agent": "kav1-probe/%s" % TOOL_VERSION}
    for h in args.header or []:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    R["header_supplied"] = bool(args.header)

    say("[1/6] Contacting %s ..." % base)
    status, ms, size, err, body = fetch(base, "/openapi.json", headers)
    R["openapi"] = {"status": status, "ms": ms, "size": size, "err": err}
    if err:
        R["unreachable"] = err
        return
    endpoints, spec = [], None
    try:
        spec = json.loads(body.decode("utf-8", "replace"))
        for path, item in spec.get("paths", {}).items():
            for method, op in item.items():
                if method.lower() not in ("get", "post", "put", "delete", "patch"):
                    continue
                required_q = any(
                    p.get("required") and p.get("in") == "query"
                    for p in op.get("parameters", [])
                )
                endpoints.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "simple_get": method.lower() == "get"
                        and "{" not in path
                        and not required_q,
                    }
                )
    except Exception:
        R["no_openapi"] = True
    R["endpoints"] = endpoints
    host_port = base.split("//", 1)[1]
    m = re.search(r":(\d+)", host_port)
    port = int(m.group(1)) if m else (443 if base.startswith("https") else 80)
    R["port"] = port

    # --- optional login
    R["logged_in"] = False
    user = args.user
    wants_login = bool(user or args.password_env)
    if not wants_login and not args.header and interactive() and spec:
        say("")
        say("Without a login every real page answers 401 and cannot be measured.")
        if ask("Log in so the real pages are measured? (y/N): ").lower() == "y":
            wants_login = True
            user = ask("Username: ")
    if wants_login and spec:
        password = (
            os.environ.get(args.password_env or "", "") if args.password_env else ""
        )
        if not password:
            if not user:
                user = ask("Username: ")
            password = getpass.getpass("Password (hidden): ") if interactive() else ""
        ok, note = do_login(base, headers, spec, user or "", password)
        password = None
        R["login_note"] = note
        R["logged_in"] = ok
        say("      %s" % note)

    say("[2/6] Timing a trivial request 20 times ...")
    lat = []
    for _ in range(20):
        _, ms, _, err, _ = fetch(base, "/openapi.json", headers)
        if err is None:
            lat.append(ms)
        time.sleep(0.05)
    R["baseline"] = lat

    say("[3/6] Timing every harmless GET endpoint ...")
    rows, skipped = [], []
    t_sweep = time.time()
    for ep in [e for e in endpoints if e["simple_get"]]:
        if is_heavy(ep["path"]) and not args.include_heavy:
            skipped.append(ep["path"])
            continue
        if time.time() - t_sweep > SWEEP_BUDGET_S:
            skipped.append(ep["path"] + " (time budget)")
            continue
        times, st, sz, errs = [], None, 0, None
        for _ in range(3):
            st, ms, sz, errs, _ = fetch(base, ep["path"], headers)
            times.append(ms)
        rows.append(
            {
                "path": ep["path"],
                "status": st,
                "best": min(times),
                "avg": sum(times) / len(times),
                "size": sz,
                "err": errs,
            }
        )
    R["sweep"], R["skipped"] = rows, skipped

    # pick one real data page to time during the watch
    real = None
    ok_rows = {r["path"]: r for r in rows if r["status"] == 200}
    for cand in ("/visitors/inside", "/visitors", "/logs"):
        if cand in ok_rows:
            real = cand
            break
    if real is None:
        real = next(
            (
                r["path"]
                for r in sorted(ok_rows.values(), key=lambda r: -r["size"])
                if r["path"] != "/openapi.json" and not r["path"].startswith("/auth/")
            ),
            None,
        )
    R["real_path"] = real

    pid = (
        find_server_pid(port)
        if host_port.split(":")[0] in ("localhost", "127.0.0.1", "[::1]")
        else None
    )
    R["pid"] = pid
    seconds = args.seconds
    say("[4/6] WATCHING the server for %d seconds." % seconds)
    say(
        "      >>> NOW USE THE SYSTEM NORMALLY: log in, open lists, search, save, enter/exit... <<<"
    )
    watchers = [Watcher(base, headers, "/openapi.json", 0.2)]
    if real:
        watchers.append(Watcher(base, headers, real, 1.0))
    sampler = Sampler(port, pid)
    for w in watchers:
        w.start()
    sampler.start()
    t0 = time.time()
    while time.time() - t0 < seconds:
        left = int(seconds - (time.time() - t0))
        done = len(watchers[0].samples)
        worst = max([s["ms"] for s in watchers[0].samples] or [0])
        if not interactive():
            time.sleep(0.5)
            continue
        sys.stdout.write(
            "\r      %3d s left | %d requests | worst so far %.0f ms   "
            % (left, done, worst)
        )
        sys.stdout.flush()
        time.sleep(0.5)
    say("")
    for w in watchers:
        w.stop_flag.set()
    sampler.stop_flag.set()
    for w in watchers:
        w.join(timeout=TIMEOUT_S + 1)
    sampler.join(timeout=12)
    R["watch"] = list(watchers[0].samples)
    R["watch_real"] = list(watchers[1].samples) if real else []
    R["proc"] = list(sampler.rows)
    R["conn_max"] = dict(sampler.conn_max)


def stats_of(samples):
    lat = [s["ms"] for s in samples if s["ok"]]
    return {
        "n": len(samples),
        "p50": pct(lat, 50),
        "p95": pct(lat, 95),
        "p99": pct(lat, 99),
        "max": max(lat) if lat else 0,
        "errors": sum(1 for s in samples if not s["ok"]),
    }


def analyse(R):
    f = []

    def add(sev, text, advice):
        f.append((sev, text, advice))

    if R.get("unreachable"):
        add(
            "CRITICAL",
            "Could not reach the server at %s (%s)." % (R["base"], R["unreachable"]),
            "Check the address/port and that the Kav1 server is running.",
        )
        return f
    if R.get("no_openapi") or R["openapi"]["status"] != 200:
        add(
            "LOW",
            "No readable /openapi.json (status %s): endpoint list unavailable."
            % R["openapi"]["status"],
            "Normal if the API docs are disabled.",
        )
    sweep = R.get("sweep", [])
    locked = [r for r in sweep if r["status"] in (401, 403)]
    R["inconclusive"] = (
        bool(sweep)
        and len(locked) >= 0.7 * len(sweep)
        and not R.get("logged_in")
        and not R.get("header_supplied")
    )
    if R["inconclusive"]:
        add(
            "HIGH",
            "%d of %d endpoints answered 401/403 (login required): the real pages were NOT "
            "measured. This run only proves the server answers quickly when idle."
            % (len(locked), len(sweep)),
            "Run again and answer 'y' to the login question (or pass --user / --header), ideally "
            "while the system feels slow.",
        )
    if R.get("login_note") and not R.get("logged_in"):
        add(
            "MEDIUM",
            "Login did not work: %s." % R["login_note"],
            "Check the username / password.",
        )
    base = R.get("baseline", [])
    if base and pct(base, 95) > 150:
        add(
            "HIGH",
            "Even a trivial request (no database) takes %.0f ms at the 95th percentile "
            "(median %.0f ms): the server process itself is slow or busy."
            % (pct(base, 95), pct(base, 50)),
            "Look at CPU / antivirus on the server machine; check the server console window for errors.",
        )
    w = R.get("watch", [])
    stalls = [s for s in w if (not s["ok"]) or s["ms"] > STALL_MS]
    R["stalls"] = stalls
    if w:
        R["watch_stats"] = stats_of(w)
    if stalls:
        worst = max(s["ms"] for s in stalls)
        add(
            "CRITICAL" if worst > 3000 or any(not s["ok"] for s in stalls) else "HIGH",
            "The server FROZE %d time(s) during the watch (worst %.1f s, %d failures). While frozen it "
            "answered nobody - this is the 'not responding' you see."
            % (len(stalls), worst / 1000.0, sum(1 for s in stalls if not s["ok"])),
            "Note what you did at those moments (timeline on page 3). Typical cause: slow work "
            "(database, password hashing, big reports) running inside the server's single event loop.",
        )
    wr = R.get("watch_real", [])
    R["real_stalls"] = [s for s in wr if (not s["ok"]) or s["ms"] > STALL_MS]
    if wr:
        R["real_stats"] = stats_of(wr)
        rs = R["real_stats"]
        if rs["p95"] > 1000 or rs["max"] > 3000:
            add(
                "HIGH",
                "The real page %s was slow while you worked: median %.0f ms, 95th %.0f ms, worst %.0f ms."
                % (R["real_path"], rs["p50"], rs["p95"], rs["max"]),
                "That endpoint (database query, serialisation or page size) is the bottleneck."
                + (
                    ""
                    if stalls
                    else " The server itself stayed responsive, so it is not a frozen event loop."
                ),
            )
    for r in [r for r in sweep if r["best"] > 1000][:3]:
        add(
            "HIGH",
            "GET %s takes %.0f ms even at best (%d bytes)."
            % (r["path"], r["best"], r["size"]),
            "This endpoint is a bottleneck.",
        )
    for r in [r for r in sweep if r["size"] > 1_000_000][:2]:
        add(
            "MEDIUM",
            "GET %s returns %.1f MB per call - every refresh moves and renders that much."
            % (r["path"], r["size"] / 1e6),
            "Paging / filtering on the server would help.",
        )
    if (
        locked
        and not R["inconclusive"]
        and sum(r["avg"] for r in locked) / len(locked) > 150
    ):
        add(
            "HIGH",
            "Requests rejected as 'not logged in' still take %.0f ms on average: the auth check is slow."
            % (sum(r["avg"] for r in locked) / len(locked)),
            "Typical cause: password-hash or session lookup on every request.",
        )
    cm = R.get("conn_max", {})
    if cm.get("CLOSE_WAIT", 0) > 10:
        add(
            "HIGH",
            "%d connections stuck in CLOSE_WAIT: the server is not closing connections (leak)."
            % cm["CLOSE_WAIT"],
            "Restart the server as a workaround; the fix needs a code change.",
        )
    proc = R.get("proc", [])
    cpus = [p["cpu_pct"] for p in proc if p.get("cpu_pct") is not None]
    if cpus and max(cpus) > 85:
        add(
            "MEDIUM",
            "The server process hit %.0f%% of a CPU core: it is CPU-bound." % max(cpus),
            "Reduce per-request work; check antivirus.",
        )
    if proc and proc[-1]["mem"] > 1.5e9:
        add(
            "MEDIUM",
            "The server process uses %.1f GB of memory." % (proc[-1]["mem"] / 1e9),
            "Possible memory leak; restart periodically until fixed.",
        )
    if not f:
        add(
            "LOW",
            "No freeze and no slow endpoint was seen during this watch (%d requests)."
            % len(w),
            "The problem may only appear with the real workload: run again WHILE it is slow.",
        )
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    f.sort(key=lambda x: order[x[0]])
    return f


def verdict(R, findings):
    if R.get("unreachable"):
        return "SERVER NOT REACHABLE"
    if R.get("inconclusive") and not R.get("stalls"):
        return "INCONCLUSIVE - login needed to measure the real pages"
    c = sum(1 for s, _, _ in findings if s == "CRITICAL")
    h = sum(1 for s, _, _ in findings if s == "HIGH")
    if c:
        return "SERVER FREEZES / PROBLEMS - %d critical, %d high" % (c, h)
    if h:
        return "SLOW PARTS FOUND - %d high-priority issue(s)" % h
    return "NO FREEZE SEEN IN THIS TEST"


# --------------------------------------------------------------------------- pages
def page_overview(R, findings):
    L = ["SERVER: %s  (process id: %s)" % (R["base"], R.get("pid") or "n/a")]
    if R.get("unreachable"):
        L += ["", "Could not connect: %s" % R["unreachable"]]
    else:
        o = R["openapi"]
        L.append(
            "API description: status %s, %.0f ms, %s endpoints listed"
            % (o["status"], o["ms"], len(R.get("endpoints", [])))
        )
        b = R.get("baseline", [])
        L.append(
            "Trivial request x20: median %.1f ms | 95th pct %.1f ms | worst %.1f ms"
            % (pct(b, 50), pct(b, 95), max(b) if b else 0)
        )
        ws = R.get("watch_stats")
        if ws:
            L.append(
                "Watch (server alive?) %d requests: median %.1f | 95th %.1f | worst %.0f ms | errors %d"
                % (ws["n"], ws["p50"], ws["p95"], ws["max"], ws["errors"])
            )
            L.append(
                "Freezes (> %d ms or failed): %d" % (STALL_MS, len(R.get("stalls", [])))
            )
        rs = R.get("real_stats")
        if rs:
            L.append(
                "Real page %s: %d requests: median %.0f | 95th %.0f | worst %.0f ms"
                % (R["real_path"], rs["n"], rs["p50"], rs["p95"], rs["max"])
            )
        L.append(
            "Logged in: %s%s"
            % (
                "yes" if R.get("logged_in") else "no",
                " (header supplied)" if R.get("header_supplied") else "",
            )
        )
    L += ["", bar("-"), "VERDICT:  " + verdict(R, findings), bar("-"), "Top findings:"]
    for sev, text, _ in findings[:5]:
        L += wrap("[%s] %s" % (sev, text), indent="    ", first=" *  ")[:4]
    return "OVERVIEW", L


def page_endpoints(R):
    L = [
        "%-46s %6s %9s %9s %9s"
        % ("GET ENDPOINT", "STATUS", "BEST ms", "AVG ms", "BYTES"),
        bar("-"),
    ]
    for r in sorted(R.get("sweep", []), key=lambda r: -r["best"]):
        L.append(
            "%-46s %6s %9.1f %9.1f %9d%s"
            % (
                ascii_only(r["path"])[:46],
                r["status"] if r["status"] else "ERR",
                r["best"],
                r["avg"],
                r["size"],
                "  SLOW" if r["best"] > 1000 else "",
            )
        )
    if not R.get("sweep"):
        L.append("(no parameter-less GET endpoints found)")
    L += [
        "",
        "Status 401/403 = needs login. Skipped as heavy/risky: %s"
        % (", ".join(ascii_only(p) for p in R.get("skipped", [])) or "none"),
    ]
    other = ", ".join(
        "%s %s" % (e["method"], ascii_only(e["path"]))
        for e in R.get("endpoints", [])
        if not e["simple_get"]
    )
    L += wrap("Other endpoints (not called): " + other[:260])
    return "ENDPOINT SPEED", L


def timeline(samples, label, limit=8):
    L = []
    stalls = [s for s in samples if (not s["ok"]) or s["ms"] > STALL_MS]
    if not stalls:
        return ["%s: no freeze recorded." % label]
    L.append("%s - freezes (seconds after the watch started):" % label)
    for s in stalls[:limit]:
        L.append(
            "   at %5.1f s   waited %8.1f ms   %s"
            % (
                s["at"],
                s["ms"],
                ("FAILED: " + ascii_only(s["err"])) if not s["ok"] else "",
            )
        )
    if len(stalls) > limit:
        L.append("   ... and %d more" % (len(stalls) - limit))
    return L


def page_stalls(R):
    L = [
        "Server check every 0.2 s; real page (%s) every 1 s. A freeze = an answer slower than %d ms."
        % (R.get("real_path") or "none", STALL_MS)
    ]
    L += timeline(R.get("watch", []), "Server alive-check")
    if R.get("real_path"):
        L += timeline(R.get("watch_real", []), "Real page")
    L.append("")
    proc = R.get("proc", [])
    L.append("SERVER PROCESS (sampled every 2 s)")
    if not proc:
        L.append("   not available (needs Windows and a server on this same machine)")
    else:
        cpus = [p["cpu_pct"] for p in proc if p.get("cpu_pct") is not None]
        L.append(
            "   CPU of one core: average %.0f%%, peak %.0f%%"
            % (sum(cpus) / len(cpus) if cpus else 0, max(cpus) if cpus else 0)
        )
        L.append(
            "   Memory: %.0f MB at start -> %.0f MB at end (peak %.0f MB)"
            % (
                proc[0]["mem"] / 1e6,
                proc[-1]["mem"] / 1e6,
                max(p["mem"] for p in proc) / 1e6,
            )
        )
        L.append(
            "   Threads: %d -> %d | Handles: %d -> %d"
            % (
                proc[0]["threads"],
                proc[-1]["threads"],
                proc[0]["handles"],
                proc[-1]["handles"],
            )
        )
    cm = R.get("conn_max", {})
    if cm:
        L.append(
            "   Connections to the server port (peak): "
            + ", ".join("%s=%d" % kv for kv in sorted(cm.items()))
        )
        L.append(
            "   (TIME_WAIT is normal: this tool itself opens many short connections)"
        )
    return "FREEZES AND SERVER PROCESS", L


def page_findings(R, findings):
    L = []
    for i, (sev, text, advice) in enumerate(findings, 1):
        L += wrap("%d. [%s] %s" % (i, sev, text), indent="   ")
        L += wrap("-> %s" % advice, indent="      ", first="   ")
    L += [
        "",
        bar("-"),
        "NEXT STEP: if the freezes appear when you do a specific action, tell me which",
        "action and the time (page 3). Also photograph the SERVER's own console window (errors).",
        "Nothing was changed on the server by this tool (apart from the login you agreed to).",
    ]
    return "FINDINGS", L


def render_pages(pages, generated):
    rows = max(20, shutil.get_terminal_size((WIDTH, 30)).lines - 4)
    screens = []
    for title, lines in pages:
        lines = [x if len(x) <= WIDTH else x[: WIDTH - 1] + ">" for x in lines]
        size = rows - 3
        if size < len(lines) <= size + 3:
            size = len(lines)
        chunks = [lines[i : i + size] for i in range(0, max(len(lines), 1), size)] or [
            []
        ]
        for n, chunk in enumerate(chunks, 1):
            screens.append(
                (
                    title + ("" if len(chunks) == 1 else " (%d/%d)" % (n, len(chunks))),
                    chunk,
                )
            )
    out = []
    for i, (title, lines) in enumerate(screens, 1):
        out.append(
            [
                "KAV1 SERVER PROBE v%s | %s | PAGE %d OF %d"
                % (TOOL_VERSION, generated, i, len(screens)),
                "== " + title + " " + "=" * max(3, WIDTH - len(title) - 4),
            ]
            + lines
        )
    return out


def show_screens(screens, plain):
    for i, screen in enumerate(screens):
        if not plain:
            clear_screen()
        for line in screen:
            say(line)
        if i < len(screens) - 1 and not plain and interactive():
            say("")
            say(">>> Photograph this screen, then press Enter for the next page ...")
            ask("")
    if not plain and interactive():
        say("")
        say(">>> End of report (%d pages)." % len(screens))


def main():
    ap = argparse.ArgumentParser(
        description="Kav1 live server probe (GET only; optional login)."
    )
    ap.add_argument("--url", help="server address, e.g. localhost:3000")
    ap.add_argument(
        "--seconds", type=int, default=60, help="length of the watch (default 60)"
    )
    ap.add_argument(
        "--header", action="append", help='extra request header, e.g. "Cookie: a=b"'
    )
    ap.add_argument(
        "--user", help="log in with this username (the password is asked, hidden)"
    )
    ap.add_argument(
        "--password-env",
        help="name of an environment variable holding the password (for scripts)",
    )
    ap.add_argument(
        "--include-heavy",
        action="store_true",
        help="also call backup/export-like GET endpoints",
    )
    ap.add_argument("--plain", action="store_true", help="no screen clearing / pauses")
    ap.add_argument(
        "--no-pause", action="store_true", help="do not wait for Enter at the end"
    )
    args = ap.parse_args()
    setup_console()
    global WIDTH
    WIDTH = max(78, min(100, shutil.get_terminal_size((100, 30)).columns - 1))
    code = 0
    try:
        generated = datetime.now().strftime("%Y-%m-%d %H:%M")
        say("Kav1 server probe v%s - %s" % (TOOL_VERSION, generated))
        R = {}
        probe(args, R)
        findings = analyse(R)
        pages = [page_overview(R, findings)]
        if not R.get("unreachable"):
            pages += [page_endpoints(R), page_stalls(R)]
        pages.append(page_findings(R, findings))
        show_screens(render_pages(pages, generated), args.plain)
    except KeyboardInterrupt:
        say("\nStopped by user.")
        code = 1
    except SystemExit as e:
        if e.code not in (0, None):
            say(str(e.code))
            code = 1
    except Exception:
        say("\nUNEXPECTED ERROR - please photograph this screen:")
        say(traceback.format_exc())
        code = 1
    if interactive() and not args.plain and not args.no_pause:
        ask("\nPress Enter to close ...")
    sys.exit(code)


if __name__ == "__main__":
    main()
