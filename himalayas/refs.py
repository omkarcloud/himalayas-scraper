"""Himalayas input parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention, never a sibling `url`/`id` pair).
Every resolver returns plain JSON values (usable as a response-cache key)
and raises ValueError with a user-facing message.

  job       acme/senior-developer | acme/jobs/senior-developer
            | https://himalayas.app/companies/acme/jobs/senior-developer?utm_source=api
                                          -> {"company_slug": "acme", "job_slug": "senior-developer"}
  company   stripe | Stripe Inc | https://himalayas.app/companies/stripe/tech-stack   -> "stripe"
  talent    debleenasarkar | @debleenasarkar | https://himalayas.app/@debleenasarkar -> "debleenasarkar"
  country   US | us | United States | united-states | USA | UK
            | https://himalayas.app/jobs/countries/united-states          -> "United States"
  role      software-engineer | Software Engineer | https://himalayas.app/salaries/.../senior-software-engineer
                                          -> "software-engineer"
  timezone  -5 | UTC-5 | UTC+05:30 | +5.5                                 -> "-5" / "UTC+05:30" (as the feed takes it)
"""
import re
from urllib.parse import unquote, urlparse

from himalayas import refdata
from himalayas import shared as S

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _parse_url(value):
    """-> (path, query) for a himalayas.app link, None for plain text;
    ValueError for another site's link."""
    raw = (value or "").strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif not low.startswith(("http://", "https://")):
        if not low.split("/", 1)[0].endswith("himalayas.app"):
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host != "himalayas.app" and not host.endswith(".himalayas.app"):
        raise ValueError("Must be a himalayas.app link.")
    return unquote(parsed.path), parsed.query


# ---- jobs ---------------------------------------------------------------------------------------------

JOB_HINT = ("Must be a Himalayas job: '<company-slug>/<job-slug>' or the job link "
            "https://himalayas.app/companies/<company-slug>/jobs/<job-slug>.")


def resolve_job(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(JOB_HINT)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(JOB_HINT)
    if url:
        company, job = S.slugs_from_job_link(url[0])
        if company and job:
            return {"company_slug": company, "job_slug": job}
        raise ValueError(JOB_HINT)
    parts = [p for p in raw.strip("/").lower().split("/") if p]
    if len(parts) == 4 and parts[0] == "companies" and parts[2] == "jobs":
        parts = [parts[1], parts[3]]
    if len(parts) == 3 and parts[1] == "jobs":
        parts = [parts[0], parts[2]]
    if len(parts) == 2 and SLUG_RE.match(parts[0]) and SLUG_RE.match(parts[1]):
        return {"company_slug": parts[0], "job_slug": parts[1]}
    raise ValueError(JOB_HINT)


# ---- companies --------------------------------------------------------------------------------------------

COMPANY_HINT = ("Must be a Himalayas company slug (e.g. stripe), a company name, "
                "or a https://himalayas.app/companies/<slug> link.")


def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(COMPANY_HINT)
    if url:
        slug = S.slug_from_company_link(url[0])
        if slug:
            return slug
        raise ValueError(COMPANY_HINT)
    slug = S.slugify(raw)
    if not slug:
        raise ValueError(COMPANY_HINT)
    return slug


def resolve_company_list(value):
    """'stripe, https://himalayas.app/companies/gitlab' -> ['stripe', 'gitlab']."""
    out = []
    for item in str(value or "").split(","):
        item = item.strip()
        if not item:
            continue
        slug = resolve_company(item)
        if slug not in out:
            out.append(slug)
    if not out:
        raise ValueError("Must list at least one company slug or link (comma-separated).")
    return out


# ---- talent ---------------------------------------------------------------------------------------------------

TALENT_HINT = ("Must be a Himalayas talent slug (e.g. @janedoe or janedoe) "
               "or a https://himalayas.app/@<slug> profile link.")


def resolve_talent(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(TALENT_HINT)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(TALENT_HINT)
    if url:
        slug = S.slug_from_talent_link(url[0])
        if slug:
            return slug
        raise ValueError(TALENT_HINT)
    slug = raw.lstrip("@").strip()
    if re.fullmatch(r"[A-Za-z0-9][\w.-]*", slug):
        return slug
    raise ValueError(TALENT_HINT)


# ---- countries ------------------------------------------------------------------------------------------------

COUNTRY_HINT = ("Must be a country Himalayas lists: an ISO code (US), a name (United States) or a slug "
                "(united-states) — see /himalayas/countries.")


def _country(code):
    return refdata.COUNTRY_BY_CODE.get(code) if code else None


def resolve_country(value):
    """-> the canonical Himalayas country name ('United States')."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COUNTRY_HINT)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(COUNTRY_HINT)
    if url:
        match = re.search(r"/countries/([a-z0-9-]+)", url[0])
        hit = refdata.COUNTRY_BY_SLUG.get(match.group(1)) if match else None
        if hit:
            return hit["name"]
        raise ValueError(COUNTRY_HINT)
    low = " ".join(raw.lower().split())
    hit = (refdata.COUNTRY_BY_NAME.get(low) or _country(refdata.COUNTRY_ALIASES.get(low))
           or refdata.COUNTRY_BY_SLUG.get(S.slugify(low) or ""))
    if hit is None and len(low) == 2 and low.isalpha():
        hit = _country(low.upper())
    if hit is None:
        slugged = S.slugify(low) or ""
        hit = refdata.COUNTRY_BY_NAME.get(slugged.replace("-", " "))
    if hit is None:
        raise ValueError(f"Himalayas lists no country '{raw}'. " + COUNTRY_HINT)
    return hit["name"]


def country_record(name):
    """The table row of a canonical name -> {code, name, slug} or None."""
    return refdata.COUNTRY_BY_NAME.get((name or "").lower())


# ---- roles (salary benchmarks) ------------------------------------------------------------------------------------

ROLE_HINT = "Must be a job title (Software Engineer / software-engineer)."


def resolve_role(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(ROLE_HINT)
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(ROLE_HINT)
    if url:
        raw = url[0].rstrip("/").rsplit("/", 1)[-1]
        raw = re.sub(r"^(entry-level|mid-level|senior|manager|director|executive)-", "", raw)
    slug = S.slugify(raw)
    if not slug:
        raise ValueError(ROLE_HINT)
    return slug


# ---- timezones ------------------------------------------------------------------------------------------------------

TIMEZONE_HINT = "Must be a UTC offset such as -5, +5.5, UTC-5 or UTC+05:30."


def resolve_timezone(value):
    """-> the offset as the feed's `timezone` param takes it ('-5', 'UTC+05:30')."""
    raw = (value or "").strip().upper().replace(" ", "")
    if not raw:
        raise ValueError(TIMEZONE_HINT)
    match = re.fullmatch(r"(?:UTC|GMT)?([+-]?)(\d{1,2})(?::(\d{2})|\.(\d{1,2}))?", raw)
    if not match:
        raise ValueError(TIMEZONE_HINT)
    sign, hours, minutes, decimal = match.groups()
    hours = int(hours)
    if hours > 14:
        raise ValueError(TIMEZONE_HINT)
    if minutes:
        return f"UTC{sign or '+'}{hours:02d}:{minutes}"
    if decimal:
        frac = float("0." + decimal)
        return f"{sign or '+'}{hours + frac:g}"
    return f"{sign}{hours}" if sign == "-" else f"+{hours}"
