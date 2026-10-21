"""Himalayas transport: plain curl_cffi (patchright only to clear Cloudflare
on the talent pages), no cookies; surfaces validated 2026-10-19/20.

Surfaces:

  feed(params)             GET himalayas.app/jobs/api — the public JSON feed
                           (every job, 20 per page, cursor pagination, full
                           HTML description). Documented at himalayas.app/api.
  feed_search(params)      GET himalayas.app/jobs/api/search — the filtered
                           feed: q, country, worldwide, exclude_worldwide,
                           seniority, employment_type, company, timezone,
                           sort, page (the only params it honours — verified
                           by total-count changes; salary / markets / benefits
                           / categories are silently ignored there).
  mcp(tool, arguments)     POST mcp.himalayas.app/mcp — the site's public MCP
                           server (JSON-RPC over HTTP, no auth, no session):
                           search_jobs (adds salary / markets / benefits /
                           companies filters), get_job_details (skills,
                           education / experience requirements), get_related_
                           jobs, search_companies, get_companies,
                           get_company_details, get_salary_data, get_remote_
                           work_statistics, search_talent, get_talent_profile.
                           It answers in MARKDOWN (parsers.py reads it).
  page(path)               GET a server-rendered page — only the salary
                           overview pages (/salaries, /salaries/countries/<x>),
                           which are NOT behind the challenge.

NOT used: the /jobs*, /companies* and /talent* HTML pages — Cloudflare
answers every scripted client (curl_cffi Chrome TLS included) with a managed
challenge. The feed + MCP cover everything those pages show. The patchright
click-through (indeed/fetch.py _browser_page) is the escalation if the feed
or MCP ever start challenging — not built while plain HTTP works.

Egress: Himalayas is never contacted from the server's own IP. Every call —
feed, MCP, pages, the Cloudflare mint — leaves through a sticky residential
exit (config.himalayas_proxy(), country config.HIMALAYAS_PROXY_COUNTRY); each
worker thread keeps its exit until a call on it fails, then takes a fresh
one. With config.HIMALAYAS_REQUIRE_PROXY (the hosted service) a missing
proxy fails the call instead of going direct; the open-source kit sets it
False so it runs on the user's own connection. The feed's anonymous
allowance is shared by every caller; set HIMALAYAS_API_KEY (free key from
himalayas.app/api) for the per-account 60/min, 10k/day allowance.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  HimalayasUpstreamError  transport failure / 5xx / unexpected body — retryable
  HimalayasBlocked        Cloudflare challenge / 403 / 429            — retryable on a new exit
  HimalayasBadRequest     Himalayas rejected the params                — never retried
  HimalayasNotFound       no such job / company / talent / salary page — never retried
"""
import json
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from himalayas import refdata

IMPERSONATE = "chrome"
TIMEOUT = (10, 60)            # (connect, read); MCP searches take up to ~5 s

JSON_HEADERS = {"accept": "application/json, text/plain, */*", "accept-language": "en-US,en;q=0.9"}
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json",
               "accept-language": "en-US,en;q=0.9"}
PAGE_HEADERS = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9"}
CF_MARKERS = ("just a moment", "challenge-error-text", "cf-chl", "challenge-platform", "attention required")


class HimalayasUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class HimalayasBlocked(HimalayasUpstreamError, Blocked):
    """Cloudflare challenge / 403 / 429 — retryable on a fresh exit."""


class HimalayasBadRequest(BadRequest):
    """Himalayas rejected the params — never retried."""


class HimalayasNotFound(NotFound):
    """No such job / company / talent / page — never retried."""


def dump_debug(name, text):
    """Write a raw response to $HIMALAYAS_DEBUG_DIR/<name>.txt for post-mortems."""
    dbg = os.environ.get("HIMALAYAS_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- exits + curl sessions (per thread) ---------------------------------------------------------

_local = threading.local()


def _new_exit(source):
    """A fresh exit from `source` (a config function) -> proxy URL, or None
    (direct) only where the deployment allows it."""
    proxy = source()
    if not proxy and getattr(config, "HIMALAYAS_REQUIRE_PROXY", True):
        raise HimalayasUpstreamError("no Himalayas proxy configured "
                                     "(Himalayas is never contacted from the server's IP)")
    return proxy or None


def _thread_exit(fresh=False):
    """This worker thread's sticky exit; `fresh` swaps it for a new one."""
    if fresh or not getattr(_local, "exit_ready", False):
        _local.exit = _new_exit(config.himalayas_proxy)
        _local.exit_ready = True
    return _local.exit


def _sessions():
    store = getattr(_local, "sessions", None)
    if store is None:
        store = _local.sessions = OrderedDict()
    return store


def _session(key, proxy):
    from curl_cffi import requests as curl_requests
    store = _sessions()
    sess = store.get(key)
    if sess is None:
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        store[key] = sess
        while len(store) > 4:
            _, old = store.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
    else:
        store.move_to_end(key)
    return sess


def _drop_session(key):
    sess = _sessions().pop(key, None)
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _attempts(label, send):
    """Run send(session) under the retry policy: HimalayasUpstreamError
    (incl. Blocked) retries on a fresh exit up to config.HIMALAYAS_MAX_ATTEMPTS
    times; BadRequest / NotFound surface at once."""
    attempts = max(1, int(config.HIMALAYAS_MAX_ATTEMPTS))
    last = None
    for attempt in range(1, attempts + 1):
        proxy = _thread_exit(fresh=attempt > 1)
        key = f"exit:{proxy or 'direct'}"
        sess = _session(key, proxy)
        try:
            return send(sess)
        except (HimalayasBadRequest, HimalayasNotFound):
            raise
        except HimalayasUpstreamError as e:
            last = e
        except Exception as e:
            last = HimalayasUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
        _drop_session(key)
        print(f"himalayas: attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(0.5 * attempt)
    raise last


def is_challenged(status, headers, text):
    if (headers or {}).get("cf-mitigated") == "challenge":
        return True
    head = (text or "")[:4000].lower()
    return status in (403, 429, 503) and any(m in head for m in CF_MARKERS)


def _classify(resp, label, json_body=True):
    """Raise the failure a response represents, else return its JSON (or text)."""
    status = resp.status_code
    headers = dict(resp.headers)
    text = resp.text or ""
    if is_challenged(status, headers, text):
        dump_debug("challenged", text)
        raise HimalayasBlocked(f"Cloudflare challenge (HTTP {status}) on {label}")
    if status == 429:
        retry = headers.get("retry-after")
        raise HimalayasBlocked(f"rate limited (HTTP 429{', retry after ' + retry + 's' if retry else ''}) on {label}")
    if status == 403:
        raise HimalayasBlocked(f"HTTP 403 on {label}")
    if status in (404, 410):
        raise HimalayasNotFound(f"Himalayas has no page for {label}")
    if status == 400:
        raise HimalayasBadRequest(f"Himalayas rejected the request on {label}: {_error_message(text)}")
    if status >= 500:
        raise HimalayasUpstreamError(f"HTTP {status} on {label}")
    if status != 200:
        raise HimalayasUpstreamError(f"HTTP {status} on {label}")
    if not json_body:
        return text
    try:
        return json.loads(text)
    except ValueError:
        dump_debug("non_json", text)
        raise HimalayasUpstreamError(f"non-JSON answer on {label}")


def _error_message(text):
    try:
        body = json.loads(text)
    except ValueError:
        return (text or "")[:200]
    if isinstance(body, dict):
        return str(body.get("error") or body.get("message") or body)[:200]
    return str(body)[:200]


# ---- the public JSON feed -----------------------------------------------------------------------------

def _feed_headers():
    headers = dict(JSON_HEADERS)
    key = getattr(config, "HIMALAYAS_API_KEY", None)
    if key:
        headers["authorization"] = f"Bearer {key}"
    return headers


def _feed_get(path, params, label):
    query = {k: v for k, v in (params or {}).items() if v not in (None, "", [])}
    url = f"{refdata.SITE}{path}" + (f"?{urlencode(query, doseq=True)}" if query else "")

    def send(sess):
        resp = sess.get(url, headers=_feed_headers(), timeout=TIMEOUT)
        body = _classify(resp, label)
        if not isinstance(body, dict) or not isinstance(body.get("jobs"), list):
            dump_debug("feed_unexpected", resp.text)
            raise HimalayasUpstreamError(f"unexpected feed payload on {label}")
        return body
    return _attempts(label, send)


def feed(cursor=None, limit=refdata.PAGE_SIZE, label="jobs feed"):
    """One page of the full feed -> {jobs, nextCursor, totalCount, updatedAt, ...}."""
    return _feed_get(refdata.FEED_PATH, {"cursor": cursor, "limit": limit}, label)


def feed_search(params, label="job search"):
    """GET the search feed with `params` (the feed's own names) -> its JSON."""
    return _feed_get(refdata.FEED_SEARCH_PATH, params, label)


# ---- the MCP server -----------------------------------------------------------------------------------------

_NOT_FOUND_RE = re.compile(r"\bnot found\b|\bno such\b|\bcould not find\b", re.I)
_BAD_INPUT_RE = re.compile(r"^unknown country|invalid|must be|is required|cannot be", re.I)
_EMPTY_RE = re.compile(r"^no (?:jobs|companies|talent|candidates|results|related jobs|salary data)\b", re.I)


def _mcp_text(body):
    """The text content of a JSON-RPC tools/call answer (SSE or plain JSON)
    -> (text, is_error); raises for a protocol error."""
    raw = body if isinstance(body, str) else ""
    frames = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
    payload = None
    for frame in reversed(frames or [raw]):
        try:
            payload = json.loads(frame)
            break
        except ValueError:
            continue
    if not isinstance(payload, dict):
        dump_debug("mcp_unexpected", raw)
        raise HimalayasUpstreamError("unexpected MCP answer")
    if payload.get("error"):
        err = payload["error"]
        message = err.get("message") if isinstance(err, dict) else str(err)
        raise HimalayasUpstreamError(f"MCP error: {message}")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise HimalayasUpstreamError("MCP answer without result")
    parts = [c.get("text", "") for c in (result.get("content") or []) if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(parts).strip(), bool(result.get("isError"))


def mcp(tool, arguments, label=None):
    """Call one public MCP tool -> its markdown text ('' for an empty
    result). Error texts are mapped: '... not found' -> NotFound, 'Unknown
    country' / invalid input -> BadRequest, the rest -> UpstreamError."""
    label = label or tool
    args = {k: v for k, v in (arguments or {}).items() if v not in (None, "", [])}
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}

    def send(sess):
        resp = sess.post(refdata.MCP_URL, headers=MCP_HEADERS, data=json.dumps(payload), timeout=TIMEOUT)
        body = _classify(resp, label, json_body=False)
        text, is_error = _mcp_text(body)
        head = text[:300]
        # an empty list first: its header echoes the keyword ("No jobs found matching 'not found'")
        if not is_error and _EMPTY_RE.match(head) and len(text) < 400:
            return ""
        if _NOT_FOUND_RE.search(head) and (is_error or len(text) < 400):
            raise HimalayasNotFound(f"Himalayas has no {label} ({head.splitlines()[0][:200]})")
        if is_error:
            if _BAD_INPUT_RE.search(head):
                raise HimalayasBadRequest(head.splitlines()[0][:300])
            dump_debug("mcp_error", text)
            raise HimalayasUpstreamError(f"MCP {tool} failed: {head[:200]}")
        return text
    return _attempts(label, send)


# ---- pages -------------------------------------------------------------------------------------------------

def page(path, label=None, missing_on_500=False):
    """GET a server-rendered page -> HTML (salary overview pages only).
    `missing_on_500`: the site answers a salary page it has no data for
    with its 500 page — treat that as NotFound instead of retrying."""
    url = f"{refdata.SITE}{path}"
    label = label or path

    def send(sess):
        resp = sess.get(url, headers=PAGE_HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if missing_on_500 and resp.status_code == 500:
            raise HimalayasNotFound(f"Himalayas has no data for {label}")
        return _classify(resp, label, json_body=False)
    return _attempts(label, send)


# ---- talent pages: a patchright-minted Cloudflare identity replayed over curl ---------------------------
#
# The /talent search pages answer every scripted client with a Cloudflare
# managed challenge (curl_cffi Chrome TLS included, from residential IPs too).
# One throwaway headful patchright Chrome on the talent egress loads the page,
# clicks the Turnstile checkbox when shown (validated 2026-10-20: 1 click,
# 23 s) and hands back its cf_clearance cookie + user agent; curl_cffi then
# replays them on the SAME exit (the clearance is bound to IP + UA) for every
# talent page until Cloudflare challenges again or the identity ages out.
# The letterboxd/fetch.py pattern. A failed mint backs off for
# config.HIMALAYAS_HARVEST_COOLDOWN seconds instead of relaunching Chrome on
# every request.

TALENT_SEED_PATH = "/talent"
_identity = None
_identity_lock = threading.Lock()
_harvest_failed_until = 0.0


def _click_turnstile(page):
    """Real mouse click on the Cloudflare Turnstile checkbox, when shown."""
    import random
    for frame in page.frames:
        if not frame.url.startswith("https://challenges.cloudflare.com"):
            continue
        try:
            box = frame.frame_element().bounding_box()
        except Exception:
            box = None
        if not box or box.get("width", 0) < 50:
            continue
        x = box["x"] + box["width"] / 9 + random.uniform(-4, 4)
        y = box["y"] + box["height"] / 2 + random.uniform(-4, 4)
        page.mouse.move(x, y, steps=random.randint(10, 25))
        page.wait_for_timeout(random.randint(100, 300))
        page.mouse.down()
        page.wait_for_timeout(random.randint(50, 150))
        page.mouse.up()
        return True
    return False


def _harvest_identity(proxy, seed_path=TALENT_SEED_PATH):
    """One headful patchright Chrome on `proxy` clears the challenge on
    `seed_path` -> {proxy, ua, cookies, minted}, validated over curl."""
    from chrome_manager import create_scope
    from patchright_driver import PatchrightDriver

    where = "direct" if not proxy else proxy.rsplit("@", 1)[-1]
    print(f"himalayas: minting a Cloudflare identity on {seed_path} via patchright ({where})...")
    start = time.monotonic()
    with create_scope():
        driver = PatchrightDriver(proxy_url=proxy, headless=False, geoip_timezone=True)
    try:
        driver.goto(refdata.SITE + seed_path, referer="https://www.google.com/")
        clicks, last_click = 0, None
        while True:
            cookies = driver.call(lambda page: page.context.cookies(refdata.SITE))
            title = (driver.title() or "").lower()
            if any(c.get("name") == "cf_clearance" for c in cookies) and "just a moment" not in title:
                break
            elapsed = time.monotonic() - start
            if elapsed > float(config.HIMALAYAS_HARVEST_TIMEOUT):
                raise RuntimeError(f"Cloudflare challenge did not clear (clicks={clicks})")
            due = (last_click is None and elapsed >= 3) or (last_click is not None and time.monotonic() - last_click >= 8)
            if due and clicks < 6 and driver.call(_click_turnstile):
                clicks += 1
                last_click = time.monotonic()
            time.sleep(1.0)
        ua = driver.evaluate("navigator.userAgent")
        jar = {c["name"]: c["value"] for c in cookies}
    finally:
        try:
            driver.close()
        except Exception:
            pass
    identity = {"proxy": proxy, "ua": ua, "cookies": jar, "minted": time.monotonic()}
    resp = _talent_send(identity, refdata.SITE + seed_path)
    if is_challenged(resp.status_code, dict(resp.headers), resp.text):
        raise RuntimeError(f"identity replay was challenged (HTTP {resp.status_code})")
    print(f"himalayas: Cloudflare identity ready ({len(jar)} cookies, clicks={clicks}, "
          f"{time.monotonic() - start:.0f}s)")
    return identity


def _get_identity(stale=None):
    """The current identity, minting one when there is none, it aged out,
    or the caller saw `stale` get challenged."""
    global _identity, _harvest_failed_until
    with _identity_lock:
        current = _identity
        fresh_enough = current is not None and \
            time.monotonic() - current["minted"] < float(config.HIMALAYAS_IDENTITY_TTL)
        if fresh_enough and current is not stale:
            return current
        if time.time() < _harvest_failed_until:
            raise HimalayasBlocked("Cloudflare challenge on the talent pages; a recent identity mint failed, "
                                   "retrying after the cooldown")
        last = None
        for attempt in range(1, int(config.HIMALAYAS_HARVEST_ATTEMPTS) + 1):
            try:
                _identity = _harvest_identity(_new_exit(config.himalayas_talent_proxy))
                return _identity
            except Exception as e:
                last = e
                print(f"himalayas: identity mint {attempt}/{config.HIMALAYAS_HARVEST_ATTEMPTS} failed: {e}")
        _identity = None
        _harvest_failed_until = time.time() + float(config.HIMALAYAS_HARVEST_COOLDOWN)
        raise HimalayasBlocked(f"Cloudflare challenge on the talent pages; identity mint failed ({last})")


def _talent_send(identity, url):
    key = f"talent:{identity['proxy'] or 'direct'}"
    sess = _session(key, identity["proxy"])
    headers = dict(PAGE_HEADERS, **{"user-agent": identity["ua"]})
    return sess.get(url, headers=headers, cookies=identity["cookies"], timeout=TIMEOUT, allow_redirects=True)


def talent_page(path, label=None):
    """GET a Cloudflare-challenged talent page -> HTML, through the replayed
    identity; one fresh identity when the current one gets challenged."""
    url = f"{refdata.SITE}{path}"
    label = label or path
    stale = None
    for attempt in (1, 2):
        identity = _get_identity(stale)
        try:
            resp = _talent_send(identity, url)
        except Exception as e:
            _drop_session(f"talent:{identity['proxy'] or 'direct'}")
            if attempt == 2:
                raise HimalayasUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
            continue
        if is_challenged(resp.status_code, dict(resp.headers), resp.text):
            print(f"himalayas: talent identity challenged on {label}; minting a fresh one")
            stale = identity
            continue
        return _classify(resp, label, json_body=False)
    raise HimalayasBlocked(f"Cloudflare challenge on {label} survived a fresh identity")


def profile_page(slug):
    """A public /@<slug> profile -> HTML: plain curl on the thread's exit
    first (profiles are usually not challenged), the talent identity when
    they are."""
    path = f"/@{slug}"
    label = f"talent profile @{slug}"
    proxy = _thread_exit()
    key = f"exit:{proxy or 'direct'}"
    try:
        resp = _session(key, proxy).get(f"{refdata.SITE}{path}", headers=PAGE_HEADERS, timeout=TIMEOUT,
                                        allow_redirects=True)
        if not is_challenged(resp.status_code, dict(resp.headers), resp.text):
            return _classify(resp, label, json_body=False)
    except (HimalayasNotFound, HimalayasBadRequest):
        raise
    except Exception:
        _drop_session(key)
        _thread_exit(fresh=True)
    if not config.HIMALAYAS_CF_FALLBACK:
        raise HimalayasBlocked(f"Cloudflare challenge on {label}")
    return talent_page(path, label)


# ---- memo / cache / parallel ---------------------------------------------------------------------------

_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 600
MEMO_MAX = 256


def memoized(key, fn, ttl=MEMO_TTL):
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < ttl:
            _memo.move_to_end(key)
            return hit[1]
    value = fn()
    with _memo_lock:
        _memo[key] = (now, value)
        _memo.move_to_end(key)
        while len(_memo) > MEMO_MAX:
            _memo.popitem(last=False)
    return value


def shared_raw(name, params, build, ttl):
    """An upstream payload shared by several routes: in-process memo, then
    the service's response cache (pods share it) when one is installed,
    then build()."""
    try:
        from cache import cached_call
    except ImportError:
        cached_call = None
    seconds = ttl.total_seconds() if hasattr(ttl, "total_seconds") else ttl
    key = (name, json.dumps(params, sort_keys=True))
    if cached_call is None:
        return memoized(key, build, ttl=min(seconds, MEMO_TTL))
    return memoized(key, lambda: cached_call(f"himalayas.raw.{name}", params, lambda **_: build(), ttl),
                    ttl=min(seconds, MEMO_TTL))


def run_parallel(fns, workers):
    """Run zero-arg callables in parallel; results align with `fns`. Each
    result is ("ok", value) or ("error", exception)."""
    def guard(fn):
        try:
            return ("ok", fn())
        except Exception as e:
            return ("error", e)
    if not fns:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(fns)))) as ex:
        return list(ex.map(guard, fns))


if __name__ == "__main__":
    # Smoke test: python himalayas/fetch.py
    body = feed_search({"q": "python", "country": "India"})
    print("search:", body.get("totalCount"), [j.get("title") for j in body["jobs"][:3]])
    text = mcp("get_company_details", {"company_slug": "stripe"})
    print("company:", text.splitlines()[0])
    print("salary:", mcp("get_salary_data", {"job_title": "software-engineer", "country": "united-states"})[:200])
