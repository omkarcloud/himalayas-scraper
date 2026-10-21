"""Live endpoint smoke tests: one call per /himalayas/* route against a
running service, with example values proven to return data (2026-10-19).
The listing tooling reads each route's FIRST call from this file's AST as
its working example, so the values stay literals.

Skipped unless HIMALAYAS_BASE points at a running service:

    SCRAPERS_PORT=6073 ONLY_SCRAPER=himalayas python run.py
    HIMALAYAS_BASE=http://127.0.0.1:6073 python -m pytest himalayas/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("HIMALAYAS_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set HIMALAYAS_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_job_search():
    body = call("/himalayas/jobs/search", query="python developer", country="India", seniority="senior")
    assert body["count"] > 50 and len(body["jobs"]) == 20 and body["next"] and body["filters_source"] == "feed"
    job = body["jobs"][0]
    assert job["id"] and job["title"] and job["link"].startswith("https://himalayas.app/companies/")
    assert job["description_html"] and job["published_at"] and job["company"]["slug"]
    assert all("senior" in j["seniority"] for j in body["jobs"])
    page2 = call("/himalayas/jobs/search", query="python developer", country="India", seniority="senior", page=2)
    assert page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    body = call("/himalayas/jobs/search", query="engineer", worldwide="true", employment_type="contractor,part-time",
                sort="salary_desc")
    assert body["jobs"] and all(j["location"]["is_worldwide"] for j in body["jobs"])
    assert all(j["employment_type"] in ("contractor", "part-time") for j in body["jobs"])
    body = call("/himalayas/jobs/search", query="python", salary_min=150000, markets="fintech", sort="salary_desc")
    assert body["filters_source"] == "mcp" and body["jobs"] and body["jobs"][0]["skills"]
    assert all(j["salary"] for j in body["jobs"])
    body = call("/himalayas/jobs/search", country="India", exclude_worldwide="true", timezone="UTC+05:30")
    assert body["count"] > 100 and all(j["location"]["countries"] for j in body["jobs"])
    assert status("/himalayas/jobs/search", query="x", exclude_worldwide="true") == 400
    assert status("/himalayas/jobs/search", country="Atlantis") == 400


def test_jobs_latest():
    body = call("/himalayas/jobs/latest", limit=5)
    assert body["count"] == 5 and body["next_cursor"] and body["total_count"] > 100000
    page2 = call("/himalayas/jobs/latest", limit=5, cursor=body["next_cursor"])
    assert page2["jobs"] and page2["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    assert status("/himalayas/jobs/latest", limit=21) == 400


def test_job_details():
    # the job examples expire with the posting (this one 2026-12-09) — swap in a fresh one after that
    body = call("/himalayas/jobs/details", job="netflix/ai-research-scientist-4-5-generative-models-recommender-systems")
    assert body["title"].startswith("AI Research Scientist") and body["salary"]["max"] >= 300000
    assert body["skills"] and body["company"]["name"] == "Netflix"
    listing = call("/himalayas/jobs/search", query="software engineer", country="United States")
    job_id = listing["jobs"][0]["id"]
    body = call("/himalayas/jobs/details", job=f"https://himalayas.app/companies/{job_id.split('/')[0]}/jobs/{job_id.split('/')[1]}")
    assert body["id"] == job_id and body["description_html"] and body["description_text"]
    assert body["description_markdown"] and body["company"]["logo_link"] and body["published_at"]
    assert body["location"]["timezone_offsets"] is not None
    assert status("/himalayas/jobs/details", job="stripe/no-such-job-xyz") == 404
    assert status("/himalayas/jobs/details", job="abc") == 400


def test_job_related_and_batch():
    body = call("/himalayas/jobs/related", job="netflix/ai-research-scientist-4-5-generative-models-recommender-systems")
    assert body["count"] >= 1
    body = call("/himalayas/jobs/batch", jobs="netflix/ai-research-scientist-4-5-generative-models-recommender-systems,reddit/machine-learning-engineer-answers-relevance,airbnb/senior-software-engineer-native-mobile")
    assert body["count"] == 3 and body["errors"] is None
    listing = call("/himalayas/jobs/search", query="account executive", country="United States")
    ids = [j["id"] for j in listing["jobs"][:2]]
    body = call("/himalayas/jobs/related", job=ids[0])
    assert body["job"]["id"] == ids[0] and body["count"] >= 1 and body["jobs"][0]["link"]
    body = call("/himalayas/jobs/batch", jobs=",".join(ids + ["stripe/no-such-job-xyz"]))
    assert body["count"] == 2 and body["errors"] == {"stripe/no-such-job-xyz": "not found"}


def test_company_search_and_details():
    body = call("/himalayas/companies/search", query="payments", tech_stack="react", sort="jobs")
    assert body["count"] > 20 and body["companies"][0]["slug"] and body["companies"][0]["open_positions_count"] >= 1
    body = call("/himalayas/companies/search", country="Germany")
    assert body["count"] > 100 and body["next"]
    body = call("/himalayas/companies/details", company="https://himalayas.app/companies/stripe")
    assert body["name"] == "Stripe" and body["founded_year"] == 2009 and body["tech_stack"] and body["benefits"]
    assert body["website_link"] == "https://stripe.com" and body["social_links"]["linkedin"]
    assert status("/himalayas/companies/details", company="no-such-company-xyz") == 404


def test_company_jobs():
    body = call("/himalayas/companies/jobs", company="Stripe", sort="recent")
    assert body["count"] > 10 and all(j["company"]["slug"] == "stripe" for j in body["jobs"]) and body["next"]
    assert status("/himalayas/companies/jobs", company="no-such-company-xyz") == 404


def test_salaries():
    body = call("/himalayas/salaries/benchmarks", role="Software Engineer", seniority="senior", country="US")
    assert body["benchmarks"][0]["median"] > 100000 and body["benchmarks"][0]["data_points"] > 100
    body = call("/himalayas/salaries/benchmarks", role="product-manager")
    assert body["count"] > 5 and {r["country"] for r in body["benchmarks"]} >= {"United States"}
    assert status("/himalayas/salaries/benchmarks", role="zzzz-nonexistent") == 404
    body = call("/himalayas/salaries/countries")
    assert body["count"] > 100 and body["countries"][0]["country"]["code"] and body["is_rounded_to_thousands"]
    body = call("/himalayas/salaries/country", country="United States")
    assert body["country"]["code"] == "US" and body["summary"]["salaries_count"] > 1000 and body["count"] > 500
    body = call("/himalayas/salaries/country", country="India")
    assert body["summary"]["salaries_count"] > 100 and body["roles"][0]["role"] and body["count"] > 50
    assert status("/himalayas/salaries/country", country="Tuvalu") == 404


def test_statistics():
    body = call("/himalayas/statistics", record="companies", type="industries")
    assert body["total_entries"] > 1000 and body["items"][0]["name"] and body["items"][0]["count"] > 100
    body = call("/himalayas/statistics", type="skills", country="India")
    assert body["country"] == "India" and body["items"][0]["unit"] == "jobs"
    assert status("/himalayas/statistics", type="industries") == 400


def test_talent():
    body = call("/himalayas/talent/search", query="react developer", country="United States")
    assert body["count"] > 10 and len(body["talent"]) == 20 and body["next"]
    card = body["talent"][0]
    assert card["slug"] and card["link"].startswith("https://himalayas.app/@") and card["headline"]
    # the site's country filter = lives in OR is authorized to work in that country
    assert sum(t["country"]["code"] == "US" for t in body["talent"]) >= 5
    body = call("/himalayas/talent/search", country="United States", sort="recent", page=2)
    assert body["current_page"] == 2 and body["talent"]
    assert status("/himalayas/talent/search", query="zzzqq nonexistent role") == 404
    body = call("/himalayas/talent/profile", talent="@jasonhead")
    assert body["name"] and body["skills"] and body["experience"] and body["education"]
    assert body["expected_salary"]["currency"] == "USD" and body["availability"] and body["tech_stack"]
    assert status("/himalayas/talent/profile", talent="no-such-user-xyz") == 404


def test_countries():
    body = call("/himalayas/countries")
    assert body["count"] >= 240 and {"code": "US", "name": "United States", "slug": "united-states",
                                     "jobs_link": "https://himalayas.app/jobs/countries/united-states"} in body["countries"]
    assert "senior" in body["seniorities"]
