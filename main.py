"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from himalayas import companies, jobs, refs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # one job in full — '<company>/<job>' or any himalayas.app job link
    save("job_netflix_ai_research_scientist.json", jobs.details(
        refs.resolve_job("netflix/ai-research-scientist-4-5-generative-models-recommender-systems")))

    # 20 jobs per page, filtered by keyword, country and seniority
    save("search_senior_software_engineer_us.json", jobs.search(
        query="software engineer", country=refs.resolve_country("US"), seniority=["Senior"]))

    # a full company profile: size, CEO, tech stack, benefits, socials
    save("company_stripe.json", companies.details(refs.resolve_company("stripe")))
