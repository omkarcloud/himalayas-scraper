"""Configuration for the Himalayas Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT               port the API listens on (default 8000)
    HIMALAYAS_PROXY    proxy URL for every request, e.g. http://user:pass@host:port
                       (default: none — direct). Jobs, companies, salaries and
                       statistics come from Himalayas' open JSON feed and its
                       public MCP server, so you very likely don't need this.
                       The talent search pages sit behind Cloudflare: the
                       scraper clears it once with a real Chrome (patchright)
                       on the same connection and carries on over plain HTTP.
                       Use a STICKY proxy here, never a rotating one — the
                       clearance is bound to the IP.
    HIMALAYAS_API_KEY  a free Himalayas API key (himalayas.app/api) for the
                       per-account feed allowance of 60 calls/minute and
                       10,000/day instead of the shared anonymous one
                       (default: none)

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

HIMALAYAS_MAX_ATTEMPTS = MAX_RETRIES
# The hosted service never contacts Himalayas from its own IP and fails
# without a proxy; on your own machine going direct is fine.
HIMALAYAS_REQUIRE_PROXY = False
HIMALAYAS_BATCH_WORKERS = 6            # parallel upstream calls in multi-call routes (/jobs/batch)
HIMALAYAS_API_KEY = os.environ.get("HIMALAYAS_API_KEY") or None
# Only read by docs in himalayas/fetch.py; the proxy itself is HIMALAYAS_PROXY.
HIMALAYAS_PROXY_COUNTRY = None

# Cloudflare fallback for the talent pages: clear the challenge once with a
# real Chrome, then replay its cookie + user agent over plain HTTP until
# Cloudflare asks again or HIMALAYAS_IDENTITY_TTL passes. Set
# HIMALAYAS_CF_FALLBACK to False to fail fast on a challenged profile instead.
HIMALAYAS_CF_FALLBACK = True
HIMALAYAS_IDENTITY_TTL = 1500          # seconds a clearance is reused
HIMALAYAS_HARVEST_TIMEOUT = 75         # seconds Chrome waits for the challenge to clear
HIMALAYAS_HARVEST_ATTEMPTS = 2
HIMALAYAS_HARVEST_COOLDOWN = 120       # seconds to wait after a failed clearance


def himalayas_proxy():
    """The proxy every request goes through (None = direct)."""
    return os.environ.get("HIMALAYAS_PROXY") or None


def himalayas_talent_proxy():
    """The connection the Cloudflare clearance is minted and replayed on."""
    return os.environ.get("HIMALAYAS_PROXY") or None


def resolve_timezone(proxy, timezone=None, geoip_timezone=None, label="driver"):
    """The JS timezone the clearance browser gets on `proxy`: the exit IP's own
    zone (looked up through the proxy), else `timezone` (None = system TZ)."""
    if isinstance(geoip_timezone, str) and geoip_timezone:
        return geoip_timezone
    if not (geoip_timezone and proxy):
        return timezone
    try:
        from curl_cffi import requests
        geo = requests.get("http://ip-api.com/json/?fields=status,timezone",
                           proxies={"http": proxy, "https": proxy}, timeout=12).json()
        if geo.get("status") == "success" and geo.get("timezone"):
            return geo["timezone"]
    except Exception:
        pass
    print(f"{label}: exit geo lookup failed; keeping timezone={timezone}")
    return timezone
