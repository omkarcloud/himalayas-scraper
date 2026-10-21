"""Offline tests: refs resolvers, marshmallow schemas, value helpers, parsers
and the endpoint functions with the transport monkeypatched to serve
fixtures (himalayas/fixtures/*.json.gz, raw payloads captured 2026-10-19)
— no network.

    python -m pytest himalayas/test_parsers.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from himalayas import (companies, fetch, jobs, lookups, parsers as P, refs, salaries,  # noqa: E402
                       schemas, shared as S, talent, talent_html as TH)
from schema_fields import load_query  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    with gzip.open(os.path.join(FX, name + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


def md(name):
    """The markdown text of a captured MCP answer."""
    return fetch._mcp_text(fx(name)["body"])[0]


# ---- refs ------------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("US", "United States"), ("us", "United States"), ("United States", "United States"),
    ("united-states", "United States"), ("USA", "United States"), ("UK", "United Kingdom"),
    ("https://himalayas.app/jobs/countries/germany", "Germany"), ("ivory coast", "Côte d'Ivoire"),
    ("Czech Republic", "Czechia"), ("south korea", "South Korea"), ("Kosovo", "Kosovo"),
])
def test_resolve_country(value, expected):
    assert refs.resolve_country(value) == expected


@pytest.mark.parametrize("value", ["", "Atlantis", "https://example.com/x", "XX"])
def test_resolve_country_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_country(value)


@pytest.mark.parametrize("value", [
    "acme/dev", "acme/jobs/dev", "/companies/acme/jobs/dev", "https://himalayas.app/companies/acme/jobs/dev?utm_source=api",
    "himalayas.app/companies/acme/jobs/dev#x", "ACME/Dev",
])
def test_resolve_job(value):
    assert refs.resolve_job(value) == {"company_slug": "acme", "job_slug": "dev"}


@pytest.mark.parametrize("value", ["", "abc", "a/b/c", "https://himalayas.app/companies/acme", "https://example.com/companies/a/jobs/b"])
def test_resolve_job_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_job(value)


@pytest.mark.parametrize("value,expected", [
    ("stripe", "stripe"), ("Stripe Inc", "stripe-inc"), ("https://himalayas.app/companies/stripe/tech-stack", "stripe"),
    ("himalayas.app/companies/gitlab?x=1", "gitlab"),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


def test_resolve_company_list():
    assert refs.resolve_company_list("stripe, https://himalayas.app/companies/gitlab, stripe") == ["stripe", "gitlab"]
    with pytest.raises(ValueError):
        refs.resolve_company_list(" , ")


@pytest.mark.parametrize("value,expected", [
    ("debleenasarkar", "debleenasarkar"), ("@debleenasarkar", "debleenasarkar"),
    ("https://himalayas.app/@debleenasarkar?utm=x", "debleenasarkar"), ("https://himalayas.app/@abc.d", "abc.d"),
])
def test_resolve_talent(value, expected):
    assert refs.resolve_talent(value) == expected


@pytest.mark.parametrize("value", ["", "@", "a b", "https://himalayas.app/companies/stripe"])
def test_resolve_talent_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_talent(value)


@pytest.mark.parametrize("value,expected", [
    ("-5", "-5"), ("UTC-5", "-5"), ("UTC+05:30", "UTC+05:30"), ("+5.5", "+5.5"), ("5", "+5"), ("gmt+8", "+8"),
])
def test_resolve_timezone(value, expected):
    assert refs.resolve_timezone(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "+15", "UTC"])
def test_resolve_timezone_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_timezone(value)


def test_resolve_role():
    assert refs.resolve_role("Software Engineer") == "software-engineer"
    assert refs.resolve_role("https://himalayas.app/salaries/countries/india/entry-level-account-executive") == "account-executive"
    with pytest.raises(ValueError):
        refs.resolve_role("")


# ---- shared helpers ------------------------------------------------------------------------------

@pytest.mark.parametrize("label,expected", [
    ("$75,000 - $95,000 USD", {"min": 75000, "max": 95000, "currency": "USD", "period": None}),
    ("50,400 - 79,200 EUR", {"min": 50400, "max": 79200, "currency": "EUR", "period": None}),
    ("$4,500 - $4,500 USD per month (about $54,000 - $54,000 USD a year)",
     {"min": 4500, "max": 4500, "currency": "USD", "period": "monthly"}),
    ("From 70,000 (INR)", {"min": 70000, "max": None, "currency": "INR", "period": None}),
    ("$25 - $40 USD per hour", {"min": 25, "max": 40, "currency": "USD", "period": "hourly"}),
    ("💰 Competitive salary", None), ("", None), (None, None),
])
def test_salary_from_label(label, expected):
    assert S.salary_from_label(label) == expected


def test_links_and_dates():
    assert S.clean_link("https://stripe.com?utm_source=himalayas.app&ref=x&source=y&a=1") == "https://stripe.com?a=1"
    assert S.clean_link("linkedin.com/in/debleena-sarkar") == "https://linkedin.com/in/debleena-sarkar"
    assert S.clean_link("") is None
    assert S.epoch_to_iso(1792399742) == "2026-10-19T08:49:02Z"
    assert S.epoch_to_iso("junk") is None and S.epoch_to_iso(0) is None
    assert S.slugs_from_job_link("https://himalayas.app/companies/acme/jobs/dev?x") == ("acme", "dev")
    assert S.category("Benefits-Coordinator") == {"name": "Benefits Coordinator", "slug": "benefits-coordinator"}
    assert S.more_count("a • b +12 more") == 12 and S.without_more("a • b +12 more") == "a • b"
    assert S.found_total("Found 302 jobs matching 'x' (showing page 2)") == 302
    assert S.shown_page("Found 302 jobs matching 'x' (showing page 2)") == 2
    assert S.found_total("## Remote Talent — Page 1 (95 total)") == 95


def test_markdown_readers():
    text = "# T\n\n**Type:** Full-time\n🎓 **Education:** required\n\n## About\nhello\n\n## Links\n🔗 **Company Page:** https://x.y/a?utm_source=m\n**Social:** Twitter: https://t.co/a • LinkedIn: https://l.in/b"
    parts = S.sections(text)
    assert set(parts) == {"", "About", "Links"} and parts["About"] == "hello"
    assert S.kv_lines(parts[""]) == {"Type": "Full-time", "Education": "required"}
    links = S.md_links(parts["Links"])
    assert links["company_page"] == "https://x.y/a" and links["social"] == {"twitter": "https://t.co/a", "linkedin": "https://l.in/b"}


# ---- schemas ----------------------------------------------------------------------------------------

def test_job_search_schema():
    data, err = load_query(schemas.JobSearchSchema, {"query": "python", "country": "in", "seniority": "senior, Manager",
                                                    "employment_type": "full_time,contract", "company": "stripe",
                                                    "timezone": "UTC+05:30", "sort": "salary_desc", "page": "2"})
    assert err is None
    assert data["country"] == "India" and data["seniority"] == ["Senior", "Manager"]
    assert data["employment_type"] == ["Full Time", "Contractor"] and data["company"] == ["stripe"]
    assert data["timezone"] == "UTC+05:30" and data["sort"] == "salaryDesc" and data["page"] == 2
    assert data["worldwide"] is None and data["salary_min"] is None and data["markets"] is None
    _, err = load_query(schemas.JobSearchSchema, {"exclude_worldwide": "true"})
    assert "exclude_worldwide" in err["errors"]
    _, err = load_query(schemas.JobSearchSchema, {"salary_min": "200000", "salary_max": "100000"})
    assert "salary_max" in err["errors"]
    _, err = load_query(schemas.JobSearchSchema, {"salary_min": "100000", "seniority": "senior,manager"})
    assert "seniority" in err["errors"]
    _, err = load_query(schemas.JobSearchSchema, {"query": "x", "page": "251"})
    assert "page" in err["errors"]
    _, err = load_query(schemas.JobSearchSchema, {"bogus": "1"})
    assert "bogus" in err["errors"]
    data, _ = load_query(schemas.JobSearchSchema, {"markets": "SaaS, Fintech", "benefits": "401k"})
    assert data["markets"] == ["saas", "fintech"] and data["benefits"] == ["401k"]


def test_other_schemas():
    data, err = load_query(schemas.JobSchema, {"job": "https://himalayas.app/companies/acme/jobs/dev"})
    assert err is None and data["job"] == {"company_slug": "acme", "job_slug": "dev"}
    data, err = load_query(schemas.JobBatchSchema, {"jobs": "acme/dev, acme/dev, b/c"})
    assert err is None and len(data["jobs"]) == 2
    _, err = load_query(schemas.JobBatchSchema, {"jobs": ",".join(f"c{i}/j" for i in range(11))})
    assert "jobs" in err["errors"]
    data, err = load_query(schemas.LatestSchema, {"limit": "20"})
    assert err is None and data["cursor"] is None
    _, err = load_query(schemas.LatestSchema, {"limit": "21"})
    assert "limit" in err["errors"]
    data, err = load_query(schemas.CompanySearchSchema, {"query": "payments", "tech_stack": "React, TypeScript", "sort": "name_asc"})
    assert err is None and data["tech_stack"] == ["react", "typescript"] and data["sort"] == "nameAToZ"
    data, err = load_query(schemas.SalaryBenchmarkSchema, {"role": "Software Engineer", "seniority": "entry-level", "country": "US"})
    assert err is None and data == {"role": "software-engineer", "seniority": "Entry-level", "country": "United States"}
    _, err = load_query(schemas.SalaryCountrySchema, {})
    assert "country" in err["errors"]
    _, err = load_query(schemas.StatisticsSchema, {"type": "industries"})
    assert "type" in err["errors"]
    data, err = load_query(schemas.StatisticsSchema, {"record": "companies", "type": "industries"})
    assert err is None and data["country"] is None
    data, err = load_query(schemas.TalentSchema, {"talent": "@abc"})
    assert err is None and data["talent"] == "abc"


# ---- parsers: feed ----------------------------------------------------------------------------------------

def test_feed_job():
    result = P.feed_search_result(fx("feed_search_python_india"), 1, max_results=5000)
    assert result["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 26, "total_count": 513}
    assert result["updated_at"] and len(result["jobs"]) == 20
    job = result["jobs"][0]
    assert job["id"] == "ithr-technologies-consulting-llc/senior-python-developer-9627617409"
    assert job["link"] == "https://himalayas.app/companies/ithr-technologies-consulting-llc/jobs/senior-python-developer-9627617409"
    assert job["company"]["slug"] == "ithr-technologies-consulting-llc" and job["company"]["logo_link"].startswith("https://")
    assert job["employment_type"] == "full-time" and job["seniority"] == ["senior"]
    assert job["location"] == {"countries": ["India"], "is_worldwide": False, "timezone_offsets": [5.5],
                               "has_timezone_restriction": True}
    assert job["categories"][0] == {"name": "Python Developer", "slug": "python-developer"}
    assert job["description_html"].startswith("<") and job["description_text"] and "<" not in job["description_text"]
    assert job["published_at"].endswith("Z") and job["expires_at"] > job["published_at"]
    assert job["skills"] is None and job["requirements"] is None
    browse = P.feed_browse_result(fx("feed_browse"), 20)["jobs"]
    howden = P.feed_search_result(fx("feed_search_howden"), 1)["jobs"]
    with_salary = [j for j in result["jobs"] + browse + howden if j["salary"]]
    assert with_salary and all(j["salary"]["currency"] and j["salary"]["period"] in ("annual", "hourly")
                               for j in with_salary)
    stripe = P.feed_search_result(fx("feed_search_company_stripe"), 1)["jobs"]
    worldwide = [j for j in result["jobs"] + browse + howden + stripe if j["location"]["is_worldwide"]]
    assert worldwide and all(j["location"]["countries"] == [] for j in worldwide)


def test_feed_browse_and_empty():
    result = P.feed_browse_result(fx("feed_browse"), 20)
    assert result["count"] == 20 and result["next_cursor"] and result["total_count"] > 100000
    empty = P.feed_search_result(fx("feed_search_empty"), 1)
    assert empty["jobs"] == [] and empty["pagination"]["total_pages"] == 0
    assert P.feed_job({})["id"] is None and P.feed_job(None)["location"]["is_worldwide"] is True


# ---- parsers: MCP ---------------------------------------------------------------------------------------------

def test_mcp_job_cards():
    result = P.mcp_job_list(md("mcp_search_jobs"), 1)
    assert result["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 16, "total_count": 302}
    job = result["jobs"][0]
    assert job["id"] == "kombo-medical-solutions-ug/full-stack-developer-m-w-d"
    assert job["employment_type"] == "full-time" and job["location"]["is_worldwide"] is True
    assert job["skills"] and job["categories"] and job["published_at"] == "2026-10-19"
    assert job["company"]["is_verified"] is False and job["description_html"] is None
    rich = P.mcp_job_list(md("mcp_search_jobs_salary"), 1)["jobs"][0]
    assert rich["salary"] == {"min": 356500, "max": 356500, "currency": "USD", "period": "annual"}
    assert rich["location"]["countries"][0] == "Burkina Faso" and rich["company"]["is_verified"] is True
    assert rich["skills_more_count"] == 13
    page2 = P.mcp_job_list(md("mcp_get_jobs"), 2)
    assert page2["pagination"]["page"] == 2 and "contractor" in {j["employment_type"] for j in page2["jobs"]}
    hourly = next(j for j in page2["jobs"] if j["salary"] and j["salary"]["period"] == "hourly")
    assert hourly["salary"]["min"] < 1000
    assert P.mcp_job_list(md("mcp_search_jobs_empty"), 1)["jobs"] == []
    assert P.mcp_job_list("", 1)["pagination"]["total_count"] == 0


def test_mcp_job_details():
    job = P.mcp_job_details(md("mcp_job_details"))
    assert job["id"] == "howden-group-holdings/benefits-operations-and-leave-coordinator"
    assert job["employment_type"] == "full-time" and job["seniority"] == ["mid-level"]
    assert job["salary"] == {"min": 75000, "max": 95000, "currency": "USD", "period": "annual"}
    assert job["location"] == {"countries": ["United States"], "is_worldwide": False}
    assert "Workday" in job["skills"] and job["requirements"]["experience_years_min"] == 3
    assert job["requirements"]["education_required"] is True
    assert job["description_markdown"].startswith("## Who are we?") and len(job["description_markdown"]) > 5000
    assert "Reasonable adjustments" in job["description_text"] and "**" not in job["description_text"]
    assert job["published_at"] == "2026-10-19" and job["extra_sections"] is None
    assert set(job["links"]) == {"tech_stack", "benefits"}
    assert P.mcp_job_details("") is None


def test_mcp_related_jobs():
    related = P.mcp_related_jobs(md("mcp_related_jobs"))
    assert len(related) == 10
    assert related[0]["id"] == "ingenovis-health/benefits-and-hr-administrator"
    assert related[0]["company"]["name"] == "Ingenovis Health" and related[0]["salary"]["max"] == 98300
    assert related[0]["location"]["countries"] == ["United States"]


def test_mcp_companies():
    result = P.mcp_company_list(md("mcp_search_companies"), 1)
    assert result["pagination"]["total_count"] == 169 and len(result["companies"]) == 20
    affirm = result["companies"][0]
    assert affirm["slug"] == "affirm" and affirm["open_positions_count"] == 206
    assert affirm["markets"][0]["slug"] == "ecommerce" and affirm["markets_more_count"] == 2
    assert affirm["tech_stack_count"] == 60 and affirm["benefits_count"] == 10 and affirm["salary_insights_count"] == 298
    assert affirm["location"]["is_hiring_worldwide"] is True and affirm["about"]
    directory = P.mcp_company_list(md("mcp_get_companies"), 1)
    assert directory["pagination"]["total_count"] == 2517
    assert any(c["badges"] == ["4-day work week"] for c in directory["companies"])


def test_mcp_company_details():
    company = P.mcp_company_details(md("mcp_company_details"))
    assert company["name"] == "Stripe" and company["slug"] == "stripe"
    assert company["company_size"] == {"label": "1001-5000", "min": 1001, "max": 5000}
    assert company["founded_year"] == 2009 and company["ceo"] == "Patrick Collison"
    assert "India" in company["locations"] and company["markets"][0]["slug"] == "payments"
    assert company["open_positions_count"] == 95 and len(company["tech_stack"]) == 14
    assert company["tech_stack"][0] == {"category": "Data Stores", "tools": ["Apache Spark", "Presto", "Pig", "Hadoop", "NSQ", "Apache Impala"]}
    assert {"name": "Healthcare benefits", "description": "Inclusive coverage"} in company["benefits"]
    assert company["website_link"] == "https://stripe.com"
    assert company["social_links"]["linkedin"] == "https://linkedin.com/company/stripe"
    assert set(company["links"]) == {"open_jobs", "tech_stack", "benefits", "salaries"}
    assert P.mcp_company_details("") is None


def test_mcp_salary_data():
    rows = P.mcp_salary_data(md("mcp_salary_data"))
    assert rows == [{"role": "Software Engineer", "seniority": "senior", "country": "United States", "min": 50000,
                     "median": 221700, "max": 393400, "currency": "USD", "period": "annual", "data_points": 1463}]
    rows = P.mcp_salary_data(md("mcp_salary_data_all"))
    assert len(rows) == 20 and {r["seniority"] for r in rows} >= {"senior", "mid-level"}
    # best-supported first: the 1,463-sample US row, not the 1-sample Costa Rica one
    assert rows[0]["country"] == "United States" and rows[0]["data_points"] == 1463
    assert [r["data_points"] for r in rows] == sorted((r["data_points"] for r in rows), reverse=True)
    assert P.mcp_salary_data("") == []


def test_mcp_statistics():
    stats = P.mcp_statistics(md("mcp_stats_countries"))
    assert stats["total_entries"] == 250 and stats["count"] == 30
    assert stats["items"][0] == {"rank": 1, "name": "United States", "slug": "united-states", "region": "NA",
                                 "count": 68431, "unit": "jobs"}
    industries = P.mcp_statistics(md("mcp_stats_industries"))
    assert industries["items"][0]["name"] == "SaaS" and industries["items"][0]["unit"] == "companies"
    skills = P.mcp_statistics(md("mcp_stats_skills_country"))
    assert skills["items"][0]["name"] == "Python" and skills["items"][0]["region"] is None


def test_talent_search_pages():
    result = TH.search_page(fx("page_talent_role_country")["html"], 1)
    assert result["pagination"] == {"page": 1, "items_per_page": 20, "total_pages": 6, "total_count": 118}
    card = result["talent"][0]
    assert card["slug"] == "vincentsteven" and card["link"] == "https://himalayas.app/@vincentsteven"
    assert card["headline"].startswith("Senior React Dev") and card["country"] == {"name": "United States",
                                                                                   "slug": "united-states", "code": "US"}
    assert card["expected_salary"] == {"min": 0, "max": 1000000, "currency": "USD", "period": "annual"}
    assert {"name": "Front End Developer", "slug": "front-end-developer"} in card["job_categories"]
    assert card["skills"] == ["React", "Redux"] and card["avatar_link"].startswith("https://cdn-images.himalayas.app/")
    assert card["recent_experience"][0] == {"title": "Senior React Developer", "company": "Trinetix, Inc.",
                                            "started_at": "2022-02", "ended_at": "2025-06", "is_current": False,
                                            "duration": "3 years 4 months"}
    everyone = TH.search_page(fx("page_talent_all")["html"], 1)
    assert everyone["pagination"]["total_count"] == 544574 and len(everyone["talent"]) == 20
    assert everyone["talent"][0]["is_id_verified"] is True
    assert all(t["headline"] and t["country"] for t in everyone["talent"])
    deep = TH.search_page(fx("page_talent_country_recent")["html"], 3)
    assert deep["pagination"]["total_count"] == 97568 and deep["pagination"]["page"] == 3
    assert TH.search_page("", 1)["talent"] == []


def test_talent_profile_pages():
    rich = TH.profile_page(fx("page_profile_rich")["html"])
    assert rich["name"] == "Jason Head" and rich["slug"] == "jasonhead" and rich["role"] == "Lead UX Designer"
    assert rich["availability"] == "actively_searching" and rich["location"]["code"] == "RO"
    assert [c["code"] for c in rich["authorized_to_work_in"]] == ["US", "RO"]
    assert rich["expected_salary"] == {"min": 145000, "max": 200000, "currency": "USD", "period": "annual"}
    assert rich["looking_for"].startswith("I seek senior design roles") and rich["about"].startswith("I am a Design Lead")
    assert len(rich["experience"]) == 6 and rich["experience"][0]["is_current"] is True
    mastercard = rich["experience"][1]
    assert mastercard["company"]["name"] == "Mastercard" and mastercard["company"]["slug"] == "mastercard"
    assert mastercard["started_at"] == "2019-10" and mastercard["ended_at"] == "2020-05"
    assert mastercard["duration"] == "7 months" and "Prototyping" in mastercard["skills"]
    assert mastercard["description"].startswith("Drove UX strategy")
    assert rich["education"] == [{"school": "Northern Virginia community college",
                                  "logo_link": rich["education"][0]["logo_link"], "degree": "Associate",
                                  "field_of_study": "Electronic Graphic Design", "grade": "3.9",
                                  "started_at": None, "ended_at": None, "description": None}]
    assert len(rich["tech_stack"]) == 30 and rich["tech_stack"][0]["name"] == "Gmail"
    assert rich["social_links"] == {"linkedin": "https://www.linkedin.com/in/jasonhead/",
                                    "behance": "https://www.behance.net/Jason_Head"}
    assert rich["portfolio_link"] == "https://behance.net/Jason_Head" and len(rich["skills"]) > 40
    assert rich["avatar_link"].startswith("https://cdn-images") and rich["cover_image_link"].startswith("https://cdn-images")
    basic = TH.profile_page(fx("page_profile_basic")["html"])
    assert basic["availability"] == "open_to_roles" and basic["education"] == [] and basic["expected_salary"] is None
    assert basic["experience"][0]["company"]["name"] == "TATA CONSULTANCY SERVICES"
    assert TH.profile_page(fx("page_profile_missing")["html"]) is None
    assert TH.profile_page("") is None


@pytest.mark.parametrize("value,expected", [
    ("May 2020 - Present ( 6 years 5 months )", {"started_at": "2020-05", "ended_at": None, "is_current": True,
                                                "duration": "6 years 5 months"}),
    ("Oct 2019 - May 2020 ( 7 months )", {"started_at": "2019-10", "ended_at": "2020-05", "is_current": False,
                                          "duration": "7 months"}),
    ("", {"started_at": None, "ended_at": None, "is_current": None, "duration": None}),
])
def test_date_range(value, expected):
    assert TH.date_range(value) == expected

# ---- parsers: salary pages ----------------------------------------------------------------------------------

def test_salary_pages():
    rows = P.salary_countries_table(fx("page_salaries")["html"])
    assert len(rows) == 112
    assert rows[0] == {"country": {"code": "AF", "name": "Afghanistan", "slug": "afghanistan",
                                   "link": "https://himalayas.app/salaries/countries/afghanistan"},
                       "min": 30000, "max": 50000, "average": 39000, "salaries_count": 4}
    page = P.salary_country_page(fx("page_salaries_india")["html"], "india")
    assert page["summary"] == {"min": 0, "max": 410000, "average": 39000, "salaries_count": 329}
    assert len(page["roles"]) == 172
    assert page["roles"][1] == {"role": "Account Executive", "seniority": "entry-level",
                                "slug": "entry-level-account-executive",
                                "link": "https://himalayas.app/salaries/countries/india/entry-level-account-executive",
                                "min": 200000, "max": 200000, "average": 200000, "salaries_count": 1}
    assert P.salary_countries_table("") == [] and P.k_money("$1.2k") == 1200


# ---- transport classification ----------------------------------------------------------------------------------

def test_mcp_text_and_errors(monkeypatch):
    text, is_error = fetch._mcp_text(fx("mcp_job_details")["body"])
    assert text.startswith("# Benefits Operations") and is_error is False
    _, is_error = fetch._mcp_text(fx("mcp_talent_profile_missing")["body"])
    assert is_error is True

    class Resp:
        def __init__(self, body):
            self.status_code, self.headers, self.text = 200, {}, body

    class Sess:
        def __init__(self, body):
            self.body = body

        def post(self, *a, **k):
            return Resp(self.body)

    monkeypatch.setattr(fetch, "_session", lambda key, proxy: Sess(fx("mcp_job_details_missing")["body"]))
    with pytest.raises(fetch.HimalayasNotFound):
        fetch.mcp("get_job_details", {"company_slug": "stripe", "job_slug": "x"})
    monkeypatch.setattr(fetch, "_session", lambda key, proxy: Sess(fx("mcp_country_bad")["body"]))
    with pytest.raises(fetch.HimalayasBadRequest):
        fetch.mcp("get_jobs", {"country": "Atlantis"})
    monkeypatch.setattr(fetch, "_session", lambda key, proxy: Sess(fx("mcp_search_jobs_empty")["body"]))
    assert fetch.mcp("search_jobs", {"keyword": "zzzz"}) == ""
    monkeypatch.setattr(fetch, "_session", lambda key, proxy: Sess(fx("mcp_salary_data_missing")["body"]))
    assert fetch.mcp("get_salary_data", {"job_title": "zzzz"}) == ""


# ---- endpoint functions over fixtures ----------------------------------------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    """Serve every transport call from the fixtures."""
    def feed_search(params, label=None):
        if params.get("company") == "stripe":
            return fx("feed_search_company_stripe")
        if params.get("company") == "howden-group-holdings":
            return fx("feed_search_howden")
        if params.get("company"):
            raise fetch.HimalayasBadRequest("Invalid company")
        if params.get("q") == "zzzz":
            return fx("feed_search_empty")
        return fx("feed_search_python_india")

    answers = {
        "search_jobs": "mcp_search_jobs_salary", "get_jobs": "mcp_get_jobs", "get_job_details": "mcp_job_details",
        "get_related_jobs": "mcp_related_jobs", "search_companies": "mcp_search_companies",
        "get_companies": "mcp_get_companies", "get_company_details": "mcp_company_details",
        "get_salary_data": "mcp_salary_data", "get_remote_work_statistics": "mcp_stats_categories",
    }

    def mcp(tool, arguments, label=None):
        if tool == "get_job_details" and arguments.get("job_slug") == "missing":
            raise fetch.HimalayasNotFound("Himalayas has no job")
        return md(answers[tool])

    def page(path, label=None, missing_on_500=False):
        if path == "/salaries":
            return fx("page_salaries")["html"]
        if path.endswith("/india"):
            return fx("page_salaries_india")["html"]
        raise fetch.HimalayasNotFound("no data")

    monkeypatch.setattr(fetch, "feed_search", feed_search)
    monkeypatch.setattr(fetch, "feed", lambda cursor=None, limit=20, label=None: fx("feed_browse"))
    monkeypatch.setattr(fetch, "mcp", mcp)
    monkeypatch.setattr(fetch, "page", page)

    def talent_page(path, label=None):
        if "zzz" in path:
            raise fetch.HimalayasNotFound("no page")
        seen.append(path)
        return fx("page_talent_role_country")["html"]

    def profile_page(slug):
        if slug == "missing":
            return fx("page_profile_missing")["html"]
        return fx("page_profile_rich")["html"]

    seen = []
    monkeypatch.setattr(fetch, "talent_page", talent_page)
    monkeypatch.setattr(fetch, "profile_page", profile_page)
    return seen
    monkeypatch.setattr(fetch, "shared_raw", lambda name, params, build, ttl: build())


def test_jobs_search_feed(offline):
    result = jobs.search(query="python developer", country="India", seniority=["Senior"], page=1)
    assert result["filters_source"] == "feed" and result["query"] == "python developer"
    assert result["pagination"]["total_count"] == 513 and len(result["jobs"]) == 20
    assert jobs.search(query="zzzz")["jobs"] == []


def test_jobs_search_mcp_hydrated(offline):
    result = jobs.search(query="python", salary_min=150000, markets=["fintech"], sort="salaryDesc", page=1)
    assert result["filters_source"] == "mcp" and result["pagination"]["total_count"] == 315
    first = result["jobs"][0]
    assert first["skills"] and first["skills_more_count"] == 13
    # no fixture feed page lists these companies -> card-only objects keep null descriptions
    assert first["description_html"] is None and first["salary"]["min"] == 356500


def test_jobs_latest(offline):
    result = jobs.latest(limit=20)
    assert result["count"] == 20 and result["next_cursor"]


def test_jobs_details_merged(offline):
    job = jobs.details({"company_slug": "howden-group-holdings", "job_slug": "benefits-operations-and-leave-coordinator"})
    assert job["description_html"].startswith("<") and job["description_markdown"].startswith("## Who are we?")
    assert job["skills"][0] == "Workday" and job["requirements"]["experience_years_min"] == 3
    assert job["company"]["logo_link"] and job["company"]["is_verified"] is False
    assert job["location"]["timezone_offsets"] == [-10, -9, -8, -7, -6, -5, 14] and job["expires_at"]
    assert list(job)[:4] == ["id", "title", "link", "company"]
    assert "skills_more_count" not in job


def test_jobs_details_mcp_only_and_missing(offline, monkeypatch):
    monkeypatch.setattr(jobs, "_feed_record", lambda c, j: None)
    job = jobs.details({"company_slug": "howden-group-holdings", "job_slug": "benefits-operations-and-leave-coordinator"})
    assert job["description_html"] is None and job["description_markdown"] and job["skills"]
    assert job["location"]["timezone_offsets"] is None
    with pytest.raises(fetch.HimalayasNotFound):
        jobs.details({"company_slug": "stripe", "job_slug": "missing"})


def test_jobs_batch_and_related(offline):
    result = jobs.batch([{"company_slug": "howden-group-holdings", "job_slug": "benefits-operations-and-leave-coordinator"},
                         {"company_slug": "stripe", "job_slug": "missing"}])
    assert result["count"] == 1 and result["errors"] == {"stripe/missing": "not found"}
    # the feed's 400 "Invalid company" for an unknown slug is a 404, not a 400 that sinks the batch
    with pytest.raises(fetch.HimalayasNotFound):
        jobs.details({"company_slug": "no-such-company", "job_slug": "missing"})
    assert jobs.batch([{"company_slug": "no-such-company", "job_slug": "missing"}])["errors"] == \
        {"no-such-company/missing": "not found"}
    related = jobs.related({"company_slug": "howden-group-holdings", "job_slug": "benefits-operations-and-leave-coordinator"})
    assert related["count"] == 10 and related["job"]["id"].startswith("howden")


def test_companies(offline):
    assert companies.search(query="payments")["pagination"]["total_count"] == 169
    assert companies.search()["pagination"]["total_count"] == 2517
    assert companies.details("stripe")["ceo"] == "Patrick Collison"
    result = companies.open_jobs("stripe", page=1)
    assert result["company"]["slug"] == "stripe" and all(j["company"]["slug"] == "stripe" for j in result["jobs"])
    with pytest.raises(fetch.HimalayasNotFound):
        companies.open_jobs("no-such-company")


def test_salaries_and_statistics(offline):
    result = salaries.benchmarks("software-engineer", seniority="Senior", country="United States")
    assert result["country"]["code"] == "US" and result["seniority"] == "senior" and result["count"] == 1
    assert salaries.countries()["count"] == 112
    india = salaries.country("India")
    assert india["country"]["slug"] == "india" and india["count"] == 172
    with pytest.raises(fetch.HimalayasNotFound):
        salaries.country("Tuvalu")
    stats = salaries.statistics("jobs", "categories")
    assert stats["record"] == "jobs" and stats["items"][0]["name"] == "Software Engineer"


def test_talent_and_lookups(offline):
    result = talent.search(query="React Developer", country="United States", sort="recent", page=2)
    assert result["pagination"]["total_count"] == 118 and result["category"]["slug"] == "react-developer"
    assert offline[-1] == "/talent/react-developer?country=United+States&sort=recent&page=2"
    talent.search()
    assert offline[-1] == "/talent"
    with pytest.raises(fetch.HimalayasNotFound):
        talent.search(query="zzz unknown")
    assert talent.profile("jasonhead")["name"] == "Jason Head"
    with pytest.raises(fetch.HimalayasNotFound):
        talent.profile("missing")
    table = lookups.countries()
    assert table["count"] == 250 and table["countries"][0]["code"] == "AF"


# ---- egress: never the server's own IP -------------------------------------------------------------

def test_no_direct_egress(monkeypatch):
    import config
    monkeypatch.setattr(config, "himalayas_proxy", lambda: None)
    monkeypatch.setattr(config, "HIMALAYAS_REQUIRE_PROXY", True, raising=False)
    monkeypatch.setattr(fetch._local, "exit_ready", False, raising=False)
    with pytest.raises(fetch.HimalayasUpstreamError, match="never contacted from the server's IP"):
        fetch._thread_exit()
    monkeypatch.setattr(config, "himalayas_proxy", lambda: "http://u:p@exit.example:1")
    assert fetch._thread_exit(fresh=True) == "http://u:p@exit.example:1"
    assert fetch._thread_exit() == "http://u:p@exit.example:1"      # sticky per thread
    monkeypatch.setattr(config, "HIMALAYAS_REQUIRE_PROXY", False)    # the open-source kit
    monkeypatch.setattr(config, "himalayas_proxy", lambda: None)
    assert fetch._thread_exit(fresh=True) is None
