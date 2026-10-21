"""/himalayas/countries — the reference tables: every country Himalayas
lists (code / name / slug, as the `country` params take them) and the
filter vocabularies."""
from himalayas import refdata


def countries():
    return {
        "countries": [{"code": c["code"], "name": c["name"], "slug": c["slug"],
                       "jobs_link": f"{refdata.SITE}/jobs/countries/{c['slug']}" if c.get("slug") else None}
                      for c in refdata.COUNTRIES],
        "count": len(refdata.COUNTRIES),
        "seniorities": list(refdata.SENIORITY_VALUES),
        "employment_types": list(refdata.EMPLOYMENT_TYPE_VALUES),
        "job_sorts": list(refdata.JOB_SORTS),
        "company_sorts": list(refdata.COMPANY_SORTS),
        "talent_sorts": list(refdata.TALENT_SORTS),
        "statistic_records": list(refdata.STAT_RECORDS),
        "statistic_types": list(refdata.STAT_TYPES),
        "page_size": refdata.PAGE_SIZE,
        "max_keyword_search_results": refdata.FEED_SEARCH_MAX_RESULTS,
    }
