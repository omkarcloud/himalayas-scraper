# 🏔️ Himalayas Scraper

Himalayas Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Himalayas remote jobs data for free.

## ✨ What Can I Get?

- 💼 **Full details on 128K+ remote jobs** — salary ranges, full descriptions, skills, seniority, location & timezone limits
- 🏢 **Profiles of 33K+ remote companies** — size, founding year, CEO, tech stack, benefits & open jobs
- 💰 **Pay data from 22K+ reported salaries in 112 countries** — min, median & max by role, seniority & country
- 👩‍💻 **540K+ remote candidates** — headlines, expected salary, work history, education & skills

## 🎥 Example: A Full Himalayas Job

```json
{
  "id": "netflix/ai-research-scientist-4-5-generative-models-recommender-systems",
  "title": "AI Research Scientist 4/5 - Generative Models, Recommender Systems",
  "link": "https://himalayas.app/companies/netflix/jobs/ai-research-scientist-4-5-generative-models-recommender-systems",
  "company": {
    "name": "Netflix",
    "slug": "netflix",
    "link": "https://himalayas.app/companies/netflix",
    "logo_link": "https://cdn-images.himalayas.app/6gtq4bkamlky0cuwvxi3m3t60689"
  },
  "employment_type": "full-time",
  "seniority": ["senior"],
  "salary": { "min": 300000, "max": 537000, "currency": "USD", "period": "annual" },
  "location": { "countries": ["United States"], "is_worldwide": false, "timezone_offsets": [-10, -9, -8] },
  "categories": [
    { "name": "AI Research Scientist", "slug": "ai-research-scientist" },
    { "name": "Machine Learning Scientist", "slug": "machine-learning-scientist" }
  ],
  "skills": ["LLM", "Generative Models", "Deep Learning", "Recommendation Systems", "Model Evaluation"],
  "excerpt": "At Netflix, our mission is to entertain the world.",
  "description_text": "At Netflix, our mission is to entertain the world. Together, we are writing the next episode - pushing the boundaries of storytelling, global fandom and making the unimaginable a reality...",
  "published_at": "2026-10-10T13:46:25Z",
  "expires_at": "2026-12-09T13:46:24Z"
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Himalayas Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/himalayas-scraper
cd himalayas-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/jobs/details?job=netflix/ai-research-scientist-4-5-generative-models-recommender-systems"
```

```json
{
  "id": "netflix/ai-research-scientist-4-5-generative-models-recommender-systems",
  "title": "AI Research Scientist 4/5 - Generative Models, Recommender Systems",
  "link": "https://himalayas.app/companies/netflix/jobs/ai-research-scientist-4-5-generative-models-recommender-systems",
  "company": { "name": "Netflix", "slug": "netflix", "link": "https://himalayas.app/companies/netflix" },
  "employment_type": "full-time",
  "seniority": ["senior"],
  "salary": { "min": 300000, "max": 537000, "currency": "USD", "period": "annual" },
  "location": { "countries": ["United States"], "is_worldwide": false },
  "skills": ["LLM", "Generative Models", "Deep Learning", "Natural Language Processing"],
  "published_at": "2026-10-10T13:46:25Z",
  "expires_at": "2026-12-09T13:46:24Z"
}
```

All 15 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

15 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Job Details | `/jobs/details` | One job in full: salary, description, skills, location limits |
| Search Jobs | `/jobs/search` | 20 jobs per page; filter by country, seniority, type, salary |
| Latest Jobs | `/jobs/latest` | Every remote job, newest first, with full descriptions |
| Related Jobs | `/jobs/related` | Up to 10 similar jobs for any job |
| Jobs in Bulk | `/jobs/batch` | Up to 10 full jobs in one call |
| Company Details | `/companies/details` | Size, CEO, tech stack, benefits and socials for one company |
| Search Companies | `/companies/search` | 20 companies per page; filter by country, benefits, tech stack |
| Company Jobs | `/companies/jobs` | Every open job at one company, in full |
| Salary Benchmarks | `/salaries/benchmarks` | Min, median and max pay for a role, with sample sizes |
| Salaries by Country / Across Countries | `/salaries/country` · `/salaries/countries` | Pay per role in one country, or every country compared |
| Remote Work Statistics | `/statistics` | Top skills, categories, countries and industries, ranked |
| Talent Profile | `/talent/profile` | One candidate in full: salary, work history, education, links |
| Search Talent | `/talent/search` | 20 candidates per page by job title, skill and country |
| Countries | `/countries` | Every country the `country` params accept |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-himalayas-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-himalayas-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-himalayas-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/jobs/search",
    params={"query": "software engineer", "country": "United States", "seniority": "senior"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Himalayas Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Himalayas%20Scraper%20API.)

[![Ask Us by Email about Himalayas Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Himalayas%20Scraper%20API&body=I%20need%20help%20using%20the%20Himalayas%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/himalayas-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/himalayas-scraper)
