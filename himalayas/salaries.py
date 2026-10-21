"""/himalayas/salaries/* and /himalayas/statistics — salary benchmarks by
role (the MCP get_salary_data tool: min / median / max in USD per year with
the sample size, per seniority and country), the salary overview pages
(/salaries and /salaries/countries/<slug>: per-country and per-role tables,
rounded to the nearest thousand USD by the site) and the remote-work
statistics (MCP get_remote_work_statistics: top skills / categories /
countries / industries by job or company count)."""
from himalayas import fetch, refdata, refs
from himalayas import parsers as P

SALARIES_PATH = "/salaries"


def benchmarks(role, seniority=None, country=None):
    """Salary benchmarks for a role, optionally one seniority and country.
    `seniority` arrives as the feed token ('Senior'), `country` as the
    canonical name; the MCP tool takes their lower-case / slug forms."""
    record = refs.country_record(country) if country else None
    args = {"job_title": role,
            "seniority": refdata.MCP_EXPERIENCE.get(seniority, seniority.lower() if seniority else None),
            "country": (record or {}).get("slug") if country else None}
    text = fetch.mcp("get_salary_data", args, label=f"salaries for {role}")
    rows = P.mcp_salary_data(text)
    if not rows:
        raise fetch.HimalayasNotFound(f"Himalayas has no salary data for '{role}'"
                                      + (f" ({seniority})" if seniority else "") + (f" in {country}" if country else ""))
    return {
        "role": {"slug": role, "name": " ".join(role.split("-")).title()},
        "seniority": refdata.SENIORITY_PUBLIC.get(seniority) if seniority else None,
        "country": _country_ref(record) if record else None,
        "currency": "USD",
        "period": "annual",
        "benchmarks": rows,
        "count": len(rows),
    }


def _country_ref(record):
    return {"code": record["code"], "name": record["name"], "slug": record["slug"],
            "link": f"{refdata.SITE}/salaries/countries/{record['slug']}" if record.get("slug") else None}


def countries():
    """The per-country remote salary table (/salaries): min / max / average
    in USD per year and the number of reported salaries. The site rounds
    the figures to the nearest thousand."""
    html = fetch.page(SALARIES_PATH, label="salary overview")
    rows = P.salary_countries_table(html)
    if not rows:
        raise fetch.HimalayasUpstreamError("the salary overview page has no country table")
    return {"currency": "USD", "period": "annual", "is_rounded_to_thousands": True,
            "countries": rows, "count": len(rows)}


def country(country):
    """One country's remote salary page: the summary and the per-role /
    per-seniority table (rounded to the nearest thousand USD)."""
    record = refs.country_record(country)
    if not record or not record.get("slug"):
        raise fetch.HimalayasNotFound(f"Himalayas has no salary page for {country}")
    try:
        # a country without salary data answers with the site's 500 page
        html = fetch.page(f"{SALARIES_PATH}/countries/{record['slug']}", label=f"salaries in {country}",
                          missing_on_500=True)
    except fetch.HimalayasNotFound:
        raise fetch.HimalayasNotFound(f"Himalayas has no salary data for {country}")
    parsed = P.salary_country_page(html, record["slug"])
    if not parsed["roles"] and parsed["summary"]["salaries_count"] is None:
        raise fetch.HimalayasNotFound(f"Himalayas has no salary data for {country}")
    return {"country": _country_ref(record), "currency": "USD", "period": "annual", "is_rounded_to_thousands": True,
            "summary": parsed["summary"], "roles": parsed["roles"], "count": len(parsed["roles"])}


def statistics(record="jobs", type="skills", country=None):
    """Top skills / categories / countries (jobs or companies) or industries
    (companies) by count, optionally within one country."""
    text = fetch.mcp("get_remote_work_statistics", {"record": record, "type": type, "country": country},
                     label=f"{record} statistics by {type}")
    result = P.mcp_statistics(text)
    result.update({"record": record, "type": type, "country": country})
    return {k: result[k] for k in ("record", "type", "country", "title", "total_entries", "count", "items")}
