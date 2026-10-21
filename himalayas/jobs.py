"""/himalayas/jobs/* — job search, the latest-jobs feed, job details, related
jobs and batch lookup.

Search runs on the public search feed (JSON, full descriptions) for the
filters the feed honours (keyword, country, worldwide, seniority,
employment type, company, timezone, sort). The filters only the MCP server
knows (salary range, markets, benefits) switch the call to its search_jobs
tool, whose markdown cards are then hydrated from the feed (one cached
company-scoped feed page per company) so the objects keep the same shape;
a card whose job is not on that page keeps null description fields.

Details merge the feed's record (HTML description, logo, timezones, expiry)
with the MCP get_job_details answer (skills, education / experience
requirements, markdown description)."""
import config
from himalayas import fetch, refdata
from himalayas import cache_config as ttl
from himalayas import parsers as P
from himalayas import shared as S

MAX_BATCH = 10
DETAILS_FEED_PAGES = 5     # company feed pages scanned for a job the keyword lookup missed


# ---- search --------------------------------------------------------------------------------------------

def _feed_params(query, country, worldwide, exclude_worldwide, seniority, employment_type, company, timezone, sort,
                 page):
    return {
        "q": query,
        "country": country,
        "worldwide": "true" if worldwide else None,
        "exclude_worldwide": "true" if exclude_worldwide else None,
        "seniority": ",".join(seniority) if seniority else None,
        "employment_type": ",".join(employment_type) if employment_type else None,
        "company": ",".join(company) if company else None,
        "timezone": timezone,
        "sort": sort,
        "page": page,
    }


def search(query=None, country=None, worldwide=None, exclude_worldwide=None, seniority=None, employment_type=None,
           company=None, timezone=None, salary_min=None, salary_max=None, markets=None, benefits=None, sort=None,
           page=1):
    """One page (20) of jobs. `seniority` / `employment_type` arrive as the
    feed's tokens, `country` as the canonical name, `sort` as the upstream
    token (the schema maps the public values)."""
    advanced = salary_min is not None or salary_max is not None or bool(markets) or bool(benefits)
    if not advanced:
        params = _feed_params(query, country, worldwide, exclude_worldwide, seniority, employment_type, company,
                              timezone, sort, page)
        raw = fetch.feed_search(params, label=f"job search {query!r} p{page}")
        result = P.feed_search_result(raw, page, max_results=refdata.FEED_SEARCH_MAX_RESULTS if query else None)
    else:
        args = {
            "keyword": query, "page": page, "country": country,
            "worldwide": True if worldwide else None,
            "exclude_worldwide": True if exclude_worldwide else None,
            "experience": refdata.MCP_EXPERIENCE.get(seniority[0]) if seniority else None,
            "type": refdata.MCP_TYPE.get(employment_type[0]) if employment_type else None,
            "salary_min": salary_min, "salary_max": salary_max,
            "markets": ",".join(markets) if markets else None,
            "benefits": ",".join(benefits) if benefits else None,
            "companies": ",".join(company) if company else None,
            "sort": sort,
        }
        text = fetch.mcp("search_jobs", args, label=f"job search {query!r} p{page}")
        result = P.mcp_job_list(text, page)
        result["jobs"] = _hydrate(result["jobs"])
        result["updated_at"] = None
    result["query"] = query
    result["filters_source"] = "mcp" if advanced else "feed"
    return result


def _company_feed_page(slug, page=1):
    """{guid -> feed job} of one company-scoped feed page (cached: the
    details lookups and the hydration of MCP cards share it)."""
    def build():
        try:
            return fetch.feed_search({"company": slug, "page": page}, label=f"company feed {slug} p{page}")
        except fetch.HimalayasBadRequest as e:
            # the feed answers an unknown slug with 400 {"errors": "Invalid company"} (companies.open_jobs)
            if "invalid company" in str(e).lower():
                raise fetch.HimalayasNotFound(f"Himalayas has no company '{slug}'")
            raise
    raw = fetch.shared_raw("company_feed", {"company": slug, "page": page}, build, ttl.COMPANY_FEED_CACHE)
    return {P.feed_job(j)["id"]: j for j in (raw or {}).get("jobs") or []}


def _hydrate(cards):
    """Merge each MCP card with its feed record (same job id) when the
    company's first feed page has it."""
    slugs = []
    for card in cards:
        slug = (card.get("company") or {}).get("slug")
        if slug and slug not in slugs:
            slugs.append(slug)
    pages = {}
    results = fetch.run_parallel([lambda s=s: _company_feed_page(s) for s in slugs], config.HIMALAYAS_BATCH_WORKERS)
    for slug, (status, value) in zip(slugs, results):
        pages[slug] = value if status == "ok" else {}
    out = []
    for card in cards:
        raw = pages.get((card.get("company") or {}).get("slug"), {}).get(card.get("id"))
        out.append(_merge(P.feed_job(raw), card) if raw else card)
    return out


def _merge(job, card):
    """A feed job + the MCP card / details of the same job -> one object."""
    merged = dict(job)
    for key in ("skills", "skills_more_count", "requirements", "description_markdown", "extra_sections", "links"):
        if card.get(key) is not None:
            merged[key] = card[key]
    for key in ("seniority", "salary", "published_at", "employment_type", "title"):
        if not merged.get(key) and card.get(key):
            merged[key] = card[key]
    if not merged["location"]["countries"] and not merged["location"]["is_worldwide"]:
        merged["location"].update({k: v for k, v in (card.get("location") or {}).items() if v is not None})
    company = dict(merged.get("company") or {})
    for key, value in (card.get("company") or {}).items():
        if company.get(key) is None and value is not None:
            company[key] = value
    merged["company"] = company
    if not merged.get("categories") and card.get("categories"):
        merged["categories"] = card["categories"]
    return merged


# ---- latest ------------------------------------------------------------------------------------------------

def latest(cursor=None, limit=refdata.PAGE_SIZE):
    """One page of the full feed, newest first; pass `next_cursor` back as
    `cursor` to continue (never repeats a job)."""
    raw = fetch.feed(cursor, limit, label=f"jobs feed cursor={cursor!r}")
    return P.feed_browse_result(raw, limit)


# ---- details ----------------------------------------------------------------------------------------------------

def _feed_record(company_slug, job_slug):
    """The feed's object for one job: the company's first feed page, then a
    keyword-narrowed company search, then the next company pages."""
    job_id = f"{company_slug}/{job_slug}"
    raw = _company_feed_page(company_slug).get(job_id)
    if raw:
        return P.feed_job(raw)
    words = " ".join(w for w in job_slug.split("-") if not w.isdigit())[:120]
    try:
        hit = fetch.feed_search({"q": words, "company": company_slug}, label=f"job lookup {job_id}")
    except fetch.HimalayasUpstreamError:
        hit = {}
    for item in (hit or {}).get("jobs") or []:
        job = P.feed_job(item)
        if job["id"] == job_id:
            return job
    for page in range(2, DETAILS_FEED_PAGES + 1):
        page_jobs = _company_feed_page(company_slug, page)
        if not page_jobs:
            break
        raw = page_jobs.get(job_id)
        if raw:
            return P.feed_job(raw)
    return None


def _mcp_details(company_slug, job_slug):
    try:
        text = fetch.mcp("get_job_details", {"company_slug": company_slug, "job_slug": job_slug},
                         label=f"job {company_slug}/{job_slug}")
    except fetch.HimalayasNotFound:
        return None
    return P.mcp_job_details(text)


def details(job):
    """The full job: the feed record merged with the MCP details. 404 when
    neither source knows the job."""
    company_slug, job_slug = job["company_slug"], job["job_slug"]
    results = fetch.run_parallel([lambda: _feed_record(company_slug, job_slug),
                                  lambda: _mcp_details(company_slug, job_slug)], 2)
    (feed_status, feed_value), (mcp_status, mcp_value) = results
    feed_obj = feed_value if feed_status == "ok" else None
    mcp_obj = mcp_value if mcp_status == "ok" else None
    if feed_obj is None and mcp_obj is None:
        for status, value in results:
            if status == "error" and not isinstance(value, fetch.HimalayasNotFound):
                raise value
        raise fetch.HimalayasNotFound(f"Himalayas has no job {company_slug}/{job_slug}")
    if feed_obj is None:
        out = dict(mcp_obj)
        out.setdefault("parent_categories", None)
        out.setdefault("excerpt", None)
        out.setdefault("description_html", None)
        out.setdefault("expires_at", None)
        out["location"] = dict(out["location"], timezone_offsets=None, has_timezone_restriction=None)
        out["company"] = dict(out["company"])
        return _ordered(out)
    if mcp_obj is None:
        return _ordered(dict(feed_obj, description_markdown=None, extra_sections=None, links=None))
    return _ordered(_merge(feed_obj, mcp_obj))


_ORDER = ("id", "title", "link", "company", "employment_type", "seniority", "salary", "location", "categories",
          "parent_categories", "skills", "skills_more_count", "requirements", "excerpt", "description_html",
          "description_markdown", "description_text", "published_at", "expires_at", "links", "extra_sections")


def _ordered(job):
    out = {key: job.get(key) for key in _ORDER if key in job or key in ("skills", "requirements")}
    out.update({k: v for k, v in job.items() if k not in out})
    if out.get("skills_more_count") is None:
        out.pop("skills_more_count", None)
    return out


def batch(jobs):
    """Up to MAX_BATCH jobs by '<company>/<job>' or link, fetched in
    parallel. Jobs Himalayas no longer has are listed under `errors`."""
    results = fetch.run_parallel([lambda j=j: details(j) for j in jobs], config.HIMALAYAS_BATCH_WORKERS)
    out, errors = [], {}
    for job, (status, value) in zip(jobs, results):
        job_id = f"{job['company_slug']}/{job['job_slug']}"
        if status == "ok":
            out.append(value)
        elif isinstance(value, fetch.HimalayasNotFound):
            errors[job_id] = "not found"
        else:
            raise value
    return {"jobs": out, "count": len(out), "errors": errors or None}


# ---- related ----------------------------------------------------------------------------------------------------

def related(job):
    """Jobs similar to one job (skills, location, category) — the MCP
    get_related_jobs tool, up to 10 light cards."""
    company_slug, job_slug = job["company_slug"], job["job_slug"]
    text = fetch.mcp("get_related_jobs", {"company_slug": company_slug, "job_slug": job_slug},
                     label=f"related jobs of {company_slug}/{job_slug}")
    jobs = P.mcp_related_jobs(text)
    return {"job": {"id": f"{company_slug}/{job_slug}", "link": S.job_link(company_slug, job_slug)},
            "jobs": jobs, "count": len(jobs)}
