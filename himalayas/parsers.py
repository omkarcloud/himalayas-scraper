"""Raw Himalayas payloads -> clean API objects. Pure functions, no network;
every parser tolerates missing / null / wrong-typed fields and never raises
on a partial payload.

Three upstream formats:
  * the public JSON feed (feed_job / feed_search_result / feed_browse_result)
  * the MCP server's MARKDOWN answers (mcp_* parsers) — job cards, job
    details, related jobs, company cards, company details, salary
    benchmarks, statistics (talent pages are HTML: talent_html.py)
  * the salary overview pages' HTML tables (salary_countries_table /
    salary_country_page)

Intentionally dropped everywhere: utm_* / ref / source tracking params on
every link, the feed's `applicationLink` (always the job link + utm), the
MCP answers' "Explore more" / "To apply: call get_apply_link" footers and
their per-card "Apply on Himalayas" link (the job link again), the `comments`
changelog string of the feed envelope, and the pages' chrome. Nothing with
information content is left out; where the MCP server truncates a list
("+12 more") the omitted count is kept (`*_more_count`).
"""
import re
from math import ceil

from himalayas import refdata
from himalayas import shared as S
from himalayas.shared import as_dict, as_list, text

# ---- small shared pieces ---------------------------------------------------------------------------

def employment_type(label):
    """'Full Time' / 'Full-time' -> 'full-time' (the public value)."""
    label = text(label)
    if not label:
        return None
    return refdata.EMPLOYMENT_TYPE_PUBLIC.get(label) or S.slugify(label)


def seniority(label):
    label = text(label)
    if not label:
        return None
    return refdata.SENIORITY_PUBLIC.get(label) or S.slugify(label)


def seniorities(values):
    out = []
    for item in as_list(values) if isinstance(values, list) else S.split_commas(values):
        value = seniority(item)
        if value and value not in out:
            out.append(value)
    return out


def _salary(low, high, currency, period):
    low, high = S.amount(low), S.amount(high)
    if low is None and high is None:
        return None
    return {"min": low, "max": high, "currency": text(currency), "period": text(period) or "annual"}


def _salary_from_label(label, default_period="annual"):
    out = S.salary_from_label(label)
    if out and not out.get("period"):
        out["period"] = default_period
    return out


def _location(countries, worldwide=None):
    countries = [c for c in (text(c) for c in as_list(countries)) if c]
    if worldwide is None:
        worldwide = not countries
    return {"countries": countries, "is_worldwide": bool(worldwide)}


def _company_ref(name, slug, logo=None, verified=None):
    slug = text(slug)
    return {"name": text(name), "slug": slug, "link": S.company_link(slug),
            "logo_link": S.clean_link(logo), "is_verified": verified}


_UNKNOWN = {"unknown", "n/a", "na", "none", "not specified", "unspecified", "-"}


def _known(value):
    """text(value), with Himalayas' 'unknown' / 'N/A' placeholders -> None."""
    value = text(value)
    return None if not value or value.lower() in _UNKNOWN else value


def _bool_required(value):
    """'required' / 'required (3+ years)' -> True; 'not required' / 'optional' -> False."""
    value = _known(value)
    if not value:
        return None
    low = value.lower()
    if low.startswith(("not required", "optional", "no")):
        return False
    return True if "required" in low else None


def _years(value):
    match = re.search(r"(\d+)\s*\+?\s*(?:years?|yrs?)", str(value or ""), re.I)
    return int(match.group(1)) if match else None


# ---- the public JSON feed -----------------------------------------------------------------------------------

def feed_job(raw):
    """One feed job object -> the API job (the shape every job route shares)."""
    raw = as_dict(raw)
    link = S.clean_link(raw.get("guid")) or S.clean_link(raw.get("applicationLink"))
    company_slug, job_slug = S.slugs_from_job_link(link)
    company_slug = text(raw.get("companySlug")) or company_slug
    offsets = []
    for value in as_list(raw.get("timezoneRestrictions")):
        number = S.num(value)
        if number is not None:
            offsets.append(int(number) if float(number).is_integer() else number)
    location = _location(raw.get("locationRestrictions"))
    location["timezone_offsets"] = offsets
    location["has_timezone_restriction"] = bool(offsets) and len(offsets) < 30
    description = raw.get("description") if isinstance(raw.get("description"), str) else None
    return {
        "id": f"{company_slug}/{job_slug}" if company_slug and job_slug else None,
        "title": text(raw.get("title")),
        "link": link or S.job_link(company_slug, job_slug),
        "company": _company_ref(raw.get("companyName"), company_slug, raw.get("companyLogo")),
        "employment_type": employment_type(raw.get("employmentType")),
        "seniority": seniorities(raw.get("seniority")),
        "salary": _salary(raw.get("minSalary"), raw.get("maxSalary"), raw.get("currency"), raw.get("salaryPeriod")),
        "location": location,
        "categories": S.categories(raw.get("categories")),
        "parent_categories": S.categories(raw.get("parentCategories")),
        "skills": None,
        "requirements": None,
        "excerpt": text(raw.get("excerpt")),
        "description_html": description.strip() if description else None,
        "description_text": S.html_to_text(description),
        "published_at": S.epoch_to_iso(raw.get("pubDate")),
        "expires_at": S.epoch_to_iso(raw.get("expiryDate")),
    }


def feed_search_result(raw, page, page_size=refdata.PAGE_SIZE, max_results=None):
    raw = as_dict(raw)
    jobs = [feed_job(j) for j in as_list(raw.get("jobs"))]
    total = S.to_int(raw.get("totalCount")) or 0
    reachable = min(total, max_results) if max_results else total
    return {
        "jobs": jobs,
        "pagination": {"page": page, "items_per_page": page_size,
                       "total_pages": min(ceil(reachable / page_size), refdata.MCP_MAX_PAGE) if reachable and page_size else 0,
                       "total_count": total},
        "updated_at": S.epoch_to_iso(raw.get("updatedAt")),
    }


def feed_browse_result(raw, limit):
    raw = as_dict(raw)
    jobs = [feed_job(j) for j in as_list(raw.get("jobs"))]
    return {
        "jobs": jobs,
        "count": len(jobs),
        "limit": limit,
        "next_cursor": text(raw.get("nextCursor")),
        "total_count": S.to_int(raw.get("totalCount")),
        "updated_at": S.epoch_to_iso(raw.get("updatedAt")),
    }


# ---- MCP: job cards (search_jobs / get_jobs) ------------------------------------------------------------------

_TYPE_WORDS = r"Full[- ]time|Part[- ]time|Contractor|Temporary|Intern(?:ship)?|Volunteer|Other"
_CARD_TYPE_RE = re.compile(rf"^(?:🕘\s*)?({_TYPE_WORDS})\s*(?:•\s*(.*))?$", re.I)
_SLUGS_RE = re.compile(r'company_slug\s*"([^"]+)",?\s*job_slug\s*"([^"]+)"')


def _card_lines(block):
    return [line.strip() for line in str(block or "").splitlines() if line.strip()]


def mcp_job_card(block):
    """One '---'-separated card of a search_jobs / get_jobs answer -> job."""
    title = company_name = verified = posted = salary_label = None
    etype, countries, worldwide, cats, skills, more = None, [], None, [], [], None
    company_slug = job_slug = None
    for line in _card_lines(block):
        if line.startswith("🚀"):
            title = S.strip_md(line)
        elif line.startswith("🏢") and "**" not in line and company_name is None:
            verified = S.is_verified(line)
            company_name = S.strip_md(line)
        elif line.startswith("📅"):
            posted = S.iso_date(re.sub(r"^posted\s*", "", S.strip_md(line) or "", flags=re.I))
        elif line.startswith("💵"):
            salary_label = line
        elif line.startswith("📂"):
            cats = S.split_bullets(S.strip_md(line), sep=r"\s*•\s*")
        elif line.startswith("🛠"):
            body = line.split(":", 1)[1] if ":" in line else line
            more = S.more_count(body)
            skills = S.split_bullets(S.strip_md(S.without_more(body)), sep=r"\s*•\s*")
        elif line.startswith("🆔"):
            match = _SLUGS_RE.search(line)
            if match:
                company_slug, job_slug = match.group(1), match.group(2)
        else:
            match = _CARD_TYPE_RE.match(line)
            if match and etype is None:
                etype = employment_type(match.group(1).replace("-", " ").title())
                where = S.strip_md(match.group(2)) or ""
                if re.search(r"worldwide|global", where, re.I):
                    worldwide = True
                else:
                    countries = S.split_commas(where)
                    worldwide = not countries if countries else None
    links = S.md_links(block)
    if not company_slug:
        company_slug, job_slug = S.slugs_from_job_link(links.get("apply_on_himalayas"))
    company_slug = company_slug or S.slug_from_company_link(links.get("company_page"))
    return {
        "id": f"{company_slug}/{job_slug}" if company_slug and job_slug else None,
        "title": title,
        "link": S.job_link(company_slug, job_slug) or links.get("apply_on_himalayas"),
        "company": _company_ref(company_name, company_slug, None, verified),
        "employment_type": etype,
        "seniority": [],
        "salary": _salary_from_label(salary_label),
        "location": dict(_location(countries, worldwide), timezone_offsets=None, has_timezone_restriction=None),
        "categories": S.categories(cats),
        "parent_categories": None,
        "skills": skills or None,
        "skills_more_count": more,
        "requirements": None,
        "excerpt": None,
        "description_html": None,
        "description_text": None,
        "published_at": posted,
        "expires_at": None,
    }


def mcp_job_list(markdown, page, page_size=refdata.PAGE_SIZE):
    """A search_jobs / get_jobs answer -> {jobs, pagination}."""
    entries = S.md_entries(markdown)
    jobs = [mcp_job_card(e) for e in entries if "🚀" in e]
    total = S.found_total(markdown)
    if total is None:
        total = len(jobs) if jobs else 0
    return {
        "jobs": jobs,
        "pagination": {"page": S.shown_page(markdown) or page, "items_per_page": page_size,
                       "total_pages": min(ceil(total / page_size), refdata.MCP_MAX_PAGE) if total and page_size else 0,
                       "total_count": total},
    }


# ---- MCP: job details ----------------------------------------------------------------------------------------

_DESCRIPTION_RE = re.compile(r"^## Job Description[ \t]*\n(.*?)(?:\n## Links[ \t]*\n.*)?\Z", re.S | re.M)


def mcp_job_details(markdown):
    """A get_job_details answer -> the detail-only fields (merged over the
    feed object by jobs.details); None for an empty answer."""
    body = str(markdown or "").strip()
    if not body:
        return None
    head, _, _ = body.partition("\n## ")
    kv = S.kv_lines(head)
    title_line = next((line for line in body.splitlines() if line.startswith("# ")), "")
    company_line = next((line for line in body.splitlines() if line.startswith("🏢")), "")
    match = _DESCRIPTION_RE.search(body)
    description = match.group(1).strip() if match else None
    links = S.md_links(body.rsplit("\n## Links", 1)[-1]) if "\n## Links" in body else {}
    company_slug, job_slug = S.slugs_from_job_link(links.get("job_page"))
    company_slug = company_slug or S.slug_from_company_link(links.get("company_page"))
    where = kv.get("Location") or ""
    worldwide = bool(re.search(r"worldwide|global", where, re.I))
    education = _known(kv.get("Education"))
    experience = _known(kv.get("Experience"))
    extra = {}
    for name, section in S.sections(body).items():
        if name and name not in ("Job Description", "Links") and not _in_description(description, name):
            extra[name] = section
    return {
        "id": f"{company_slug}/{job_slug}" if company_slug and job_slug else None,
        "title": S.strip_md(title_line[2:]) if title_line else None,
        "link": S.job_link(company_slug, job_slug) or links.get("job_page"),
        "company": _company_ref(S.strip_md(company_line), company_slug, None, S.is_verified(company_line)),
        "employment_type": employment_type((kv.get("Type") or "").replace("-", " ").title()),
        "seniority": seniorities(kv.get("Seniority")),
        "salary": _salary_from_label(kv.get("Salary")),
        "location": _location([] if worldwide else S.split_commas(where), worldwide),
        "categories": S.categories(S.split_commas(kv.get("Categories"))),
        "skills": S.split_commas(kv.get("Skills")) or None,
        "requirements": {
            "education_required": _bool_required(education),
            "education": text(education),
            "experience_required": _bool_required(experience),
            "experience_years_min": _years(experience),
            "experience": text(experience),
        } if (education or experience) else None,
        "description_markdown": description,
        "description_text": S.multiline(re.sub(r"^#{1,6}\s*|\*\*", "", description, flags=re.M)) if description else None,
        "published_at": S.iso_date(kv.get("Posted")),
        "extra_sections": extra or None,
        "links": {k: v for k, v in links.items() if k not in ("job_page", "to_apply", "company_page")} or None,
    }


def _in_description(description, heading):
    return bool(description) and f"## {heading}" in description


# ---- MCP: related jobs -------------------------------------------------------------------------------------

def mcp_related_jobs(markdown):
    out = []
    for block in S.md_entries(markdown):
        lines = _card_lines(block)
        start = next((i for i, line in enumerate(lines) if line.startswith("🚀")), None)
        if start is None:
            continue
        lines = lines[start:]          # the first entry carries the "Found N related jobs" header
        head = S.strip_md(lines[0]) or ""
        title, _, company = head.rpartition(" at ")
        if not title:
            title, company = head, None
        etype, where, salary_label = None, "", None
        link = None
        for line in lines[1:]:
            if line.startswith("💵"):
                salary_label = line
            elif line.startswith("🔗"):
                link = S.clean_link(re.sub(r"^🔗\s*", "", line))
            else:
                match = _CARD_TYPE_RE.match(line)
                if match:
                    etype = employment_type(match.group(1).replace("-", " ").title())
                    where = S.strip_md(match.group(2)) or ""
        company_slug, job_slug = S.slugs_from_job_link(link)
        worldwide = bool(re.search(r"worldwide|global", where, re.I))
        out.append({
            "id": f"{company_slug}/{job_slug}" if company_slug and job_slug else None,
            "title": title,
            "link": link,
            "company": {"name": company, "slug": company_slug, "link": S.company_link(company_slug)},
            "employment_type": etype,
            "salary": _salary_from_label(salary_label),
            "location": _location([] if worldwide else S.split_commas(where), worldwide),
        })
    return out


# ---- MCP: company cards (search_companies / get_companies) -------------------------------------------------

_COUNT_RE = re.compile(r"([\d,]+)\s+([a-z][a-z ]+?)(?:\s*•|$)", re.I)


def mcp_company_card(block):
    lines = _card_lines(block)
    name = verified = about = None
    badges, locations, worldwide, markets, more = [], [], None, [], None
    open_positions = tech_count = benefits_count = salary_count = None
    for index, line in enumerate(lines):
        if line.startswith("🏢") and "**" in line and ":**" not in line and name is None:
            name = S.strip_md(line)
            verified = S.is_verified(line)
            # the badges / location line follows the name
            if index + 1 < len(lines) and not lines[index + 1].startswith(("🔥", "🏷", "📊", "💡", "🔗")):
                for item in re.split(r"\s*•\s*", lines[index + 1]):
                    item = item.strip()
                    if not item:
                        continue
                    if item.startswith("🌍"):
                        where = S.strip_md(item) or ""
                        if re.search(r"^global$|worldwide", where, re.I):
                            worldwide = True
                        else:
                            locations.extend(S.split_commas(where))
                    else:
                        badge = S.strip_md(item)
                        if badge:
                            badges.append(badge)
        elif line.startswith("🔥"):
            open_positions = S.to_int(re.search(r"\d+", line).group(0)) if re.search(r"\d+", line) else None
        elif line.startswith("🏷"):
            body = line.split(":", 1)[1] if ":" in line else line
            more = S.more_count(body)
            markets = S.split_bullets(S.strip_md(S.without_more(body)), sep=r"\s*•\s*")
        elif line.startswith("📊"):
            for count, label in _COUNT_RE.findall(S.strip_md(line) or ""):
                value = S.to_int(count.replace(",", ""))
                label = label.strip().lower()
                if "tech" in label:
                    tech_count = value
                elif "benefit" in label:
                    benefits_count = value
                elif "salar" in label:
                    salary_count = value
        elif line.startswith("💡"):
            about = text(S.strip_md(line.split(":", 1)[1] if ":**" in line else line))   # 'R&amp;D' -> 'R&D'
    links = S.md_links(block)
    slug = S.slug_from_company_link(links.get("company_page"))
    return {
        "name": name,
        "slug": slug,
        "link": S.company_link(slug),
        "is_verified": verified,
        "about": about,
        "location": {"countries": locations, "is_hiring_worldwide": worldwide if worldwide is not None else (not locations or None)},
        "badges": badges,
        "markets": S.categories(markets),
        "markets_more_count": more,
        "open_positions_count": open_positions,
        "tech_stack_count": tech_count,
        "benefits_count": benefits_count,
        "salary_insights_count": salary_count,
    }


def mcp_company_list(markdown, page, page_size=refdata.PAGE_SIZE):
    entries = S.md_entries(markdown)
    companies = [mcp_company_card(e) for e in entries if "🏢" in e]
    total = S.found_total(markdown)
    if total is None:
        total = len(companies)
    return {
        "companies": companies,
        "pagination": {"page": S.shown_page(markdown) or page, "items_per_page": page_size,
                       "total_pages": min(ceil(total / page_size), refdata.MCP_MAX_PAGE) if total and page_size else 0,
                       "total_count": total},
    }


# ---- MCP: company details ---------------------------------------------------------------------------------

def _size_range(label):
    label = text(label)
    if not label:
        return None
    numbers = [S.to_int(n.replace(",", "")) for n in re.findall(r"[\d,]+", label)]
    return {"label": label, "min": numbers[0] if numbers else None,
            "max": numbers[1] if len(numbers) > 1 else (None if "+" in label else numbers[0] if numbers else None)}


def mcp_company_details(markdown):
    body = str(markdown or "").strip()
    if not body:
        return None
    parts = S.sections(body)
    head = parts.get("", "")
    kv = S.kv_lines(head)
    title_line = next((line for line in head.splitlines() if line.startswith("# ")), "")
    links = S.md_links(parts.get("Links", ""))
    slug = S.slug_from_company_link(links.get("company_page"))
    tech = [{"category": key, "tools": S.split_commas(value)} for key, value in S.kv_pairs(parts.get("Tech Stack", ""))]
    benefits = [{"name": key, "description": text(value) if text(value) and text(value).lower() != key.lower() else None}
                for key, value in S.kv_pairs(parts.get("Benefits & Perks", "") or parts.get("Benefits", ""))]
    known = {"", "About", "Tech Stack", "Benefits & Perks", "Benefits", "Links"}
    extra = {name: section for name, section in parts.items() if name not in known and section}
    return {
        "name": S.strip_md(title_line[2:]) if title_line else None,
        "slug": slug,
        "link": S.company_link(slug),
        "is_verified": S.is_verified(title_line),
        "about": S.multiline(parts.get("About")) or None,
        "company_size": _size_range(kv.get("Size")),
        "founded_year": S.to_int(kv.get("Founded")),
        "ceo": text(kv.get("CEO")),
        "locations": S.split_commas(kv.get("Location")),
        "markets": S.categories(S.split_commas(kv.get("Markets"))),
        "open_positions_count": S.to_int(kv.get("Open Positions")),
        "tech_stack": tech,
        "benefits": benefits,
        "website_link": links.get("website"),
        "social_links": links.get("social") or {},
        "links": {k: v for k, v in links.items() if k not in ("company_page", "website", "social")},
        "extra_sections": extra or None,
    }


# ---- MCP: salary benchmarks -------------------------------------------------------------------------------------

_BENCH_HEAD_RE = re.compile(r"^\*\*(.+?)\*\*\s*(?:\(([^)]*)\))?\s*(?:—|-)\s*(.*?)\s*$")
_BENCH_FIGURES_RE = re.compile(r"Min:\s*\$?([\d,.]+)\s*\|\s*Median:\s*\$?([\d,.]+)\s*\|\s*Max:\s*\$?([\d,.]+)\s*([A-Z]{3})?(?:/(\w+))?")
_BENCH_POINTS_RE = re.compile(r"Based on\s+([\d,]+)\s+data points?")


def mcp_salary_data(markdown):
    """A get_salary_data answer -> [{role, seniority, country, min, median,
    max, currency, period, data_points}]."""
    out = []
    current = None
    for line in str(markdown or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("💰 **Explore") or not stripped:
            continue
        head = _BENCH_HEAD_RE.match(stripped)
        if head and not stripped.startswith(("💰", "📊")):
            current = {"role": text(head.group(1)), "seniority": seniority(head.group(2)),
                       "country": text(head.group(3)), "min": None, "median": None, "max": None,
                       "currency": "USD", "period": "annual", "data_points": None}
            out.append(current)
            continue
        if current is None:
            continue
        figures = _BENCH_FIGURES_RE.search(stripped)
        if figures:
            current["min"] = S.amount(figures.group(1).replace(",", ""))
            current["median"] = S.amount(figures.group(2).replace(",", ""))
            current["max"] = S.amount(figures.group(3).replace(",", ""))
            if figures.group(4):
                current["currency"] = figures.group(4)
            if figures.group(5):
                current["period"] = "annual" if figures.group(5).lower().startswith("year") else figures.group(5).lower()
            continue
        points = _BENCH_POINTS_RE.search(stripped)
        if points:
            current["data_points"] = S.to_int(points.group(1).replace(",", ""))
    # the MCP lists rows in no useful order (a 1-sample row before a 1,463-sample
    # one); the best-supported benchmarks first
    out.sort(key=lambda row: -(row["data_points"] or 0))
    return out


# ---- MCP: statistics ----------------------------------------------------------------------------------------------

_STAT_ROW_RE = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*(?:\(([^)]*)\))?\s*(?:—|-)\s*([\d,]+)\s+(\w+)")


def mcp_statistics(markdown):
    body = str(markdown or "")
    total = re.search(r"Total:\s*([\d,]+)\s+entries", body)
    items = []
    for line in body.splitlines():
        match = _STAT_ROW_RE.match(line.strip())
        if not match:
            continue
        rank, name, region, count, unit = match.groups()
        items.append({"rank": int(rank), "name": " ".join(name.replace("-", " ").split()), "slug": S.slugify(name),
                      "region": text(region), "count": S.to_int(count.replace(",", "")), "unit": unit.lower()})
    heading = re.search(r"^## (.+)$", body, re.M)
    return {"title": S.strip_md(heading.group(1)) if heading else None,
            "total_entries": S.to_int(total.group(1).replace(",", "")) if total else None,
            "count": len(items), "items": items}


# ---- salary overview pages (HTML tables) -------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_HREF_RE = re.compile(r'href="(/salaries/[^"]+)"')


def k_money(value):
    """'$30k' / '$1.2k' / '$410k' / '4' -> 30000 / 1200 / 410000 / 4; '' -> None."""
    value = text(_TAG_RE.sub("", str(value or "")))
    if not value:
        return None
    match = re.fullmatch(r"\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?", value)
    if not match:
        return None
    number = S.num(match.group(1).replace(",", ""))
    if number is None:
        return None
    if match.group(2):
        number *= 1000 if match.group(2).lower() == "k" else 1_000_000
    return S.amount(number)


def _table_rows(html):
    for row in _ROW_RE.findall(html or ""):
        cells = _CELL_RE.findall(row)
        if len(cells) < 5:
            continue
        href = _HREF_RE.search(cells[0])
        label = text(_TAG_RE.sub("", cells[0]))
        yield href.group(1) if href else None, label, cells[1:5]


def salary_countries_table(html):
    """/salaries -> [{country: {code, name, slug, link}, min, max, average, salaries_count}] (USD, rounded)."""
    out = []
    for href, label, cells in _table_rows(html):
        if not href or "/salaries/countries/" not in href:
            continue
        slug = href.rsplit("/", 1)[-1]
        record = refdata.COUNTRY_BY_SLUG.get(slug)
        out.append({
            "country": {"code": record["code"] if record else None, "name": label or (record or {}).get("name"),
                        "slug": slug, "link": f"{refdata.SITE}{href}"},
            "min": k_money(cells[0]), "max": k_money(cells[1]), "average": k_money(cells[2]),
            "salaries_count": S.to_int(_TAG_RE.sub("", cells[3])),
        })
    return out


_SENIORITY_PREFIX_RE = re.compile(r"^(Entry-level|Mid-level|Senior|Manager|Director|Executive|Lead|Junior)\s+(.+)$", re.I)


def salary_country_page(html, country_slug):
    """/salaries/countries/<slug> -> {summary, roles: [{role, seniority, ...}]}."""
    body = html or ""
    plain = text(_TAG_RE.sub(" ", re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", " ", body, flags=re.S))) or ""
    span = re.search(r"spans from \$?([\d,.]+k?) to \$?([\d,.]+k?) USD per year", plain, re.I)
    salaries = re.search(r"aggregate of ([\d,]+) salaries", plain, re.I)
    average = re.search(r"average salary for a remote employee(?: in [^$]*?)? is \$?([\d,.]+k?) USD", plain, re.I)
    roles = []
    for href, label, cells in _table_rows(body):
        if not href or f"/salaries/countries/{country_slug}/" not in href:
            continue
        match = _SENIORITY_PREFIX_RE.match(label or "")
        roles.append({
            "role": text(match.group(2)) if match else label,
            "seniority": seniority(match.group(1)) if match else None,
            "slug": href.rsplit("/", 1)[-1],
            "link": f"{refdata.SITE}{href}",
            "min": k_money(cells[0]), "max": k_money(cells[1]), "average": k_money(cells[2]),
            "salaries_count": S.to_int(_TAG_RE.sub("", cells[3])),
        })
    return {
        "summary": {"min": k_money(span.group(1)) if span else None, "max": k_money(span.group(2)) if span else None,
                    "average": k_money(average.group(1)) if average else None,
                    "salaries_count": S.to_int(salaries.group(1).replace(",", "")) if salaries else None},
        "roles": roles,
    }
