"""Himalayas reference data: hosts, the filter vocabularies the public feed
and the MCP server accept (public value -> upstream token), page sizes and
the country table (countries.py, generated 2026-10-19 from the site's
sitemap slugs + the MCP get_correct_country_name resolver)."""
from himalayas.countries import COUNTRIES

SITE = "https://himalayas.app"
HOST = "himalayas.app"
MCP_URL = "https://mcp.himalayas.app/mcp"
FEED_PATH = "/jobs/api"
FEED_SEARCH_PATH = "/jobs/api/search"
RSS_PATH = "/jobs/rss"

PAGE_SIZE = 20                 # both the feed and the MCP lists serve 20 per page
FEED_SEARCH_MAX_RESULTS = 5000  # a keyword search's totalCount is capped at 5,000
MCP_MAX_PAGE = 500

# ---- jobs -------------------------------------------------------------------------------------------

# public value -> the feed's `seniority` token (also the MCP `experience` value lower-cased)
SENIORITIES = {
    "entry-level": "Entry-level", "entry_level": "Entry-level", "junior": "Entry-level",
    "mid-level": "Mid-level", "mid_level": "Mid-level", "mid": "Mid-level",
    "senior": "Senior", "manager": "Manager", "director": "Director", "executive": "Executive",
}
SENIORITY_VALUES = ["entry-level", "mid-level", "senior", "manager", "director", "executive"]
# the six public values -> feed token (the salary benchmark's single `seniority`)
SENIORITY_CHOICES = {"entry-level": "Entry-level", "mid-level": "Mid-level", "senior": "Senior",
                     "manager": "Manager", "director": "Director", "executive": "Executive"}
MCP_EXPERIENCE = {"Entry-level": "entry-level", "Mid-level": "mid-level", "Senior": "senior",
                  "Manager": "manager", "Director": "director", "Executive": "executive"}

# public value -> the feed's `employment_type` token
EMPLOYMENT_TYPES = {
    "full-time": "Full Time", "full_time": "Full Time", "fulltime": "Full Time",
    "part-time": "Part Time", "part_time": "Part Time", "parttime": "Part Time",
    "contractor": "Contractor", "contract": "Contractor", "freelance": "Contractor",
    "temporary": "Temporary", "temp": "Temporary",
    "intern": "Intern", "internship": "Intern",
    "volunteer": "Volunteer", "other": "Other",
}
EMPLOYMENT_TYPE_VALUES = ["full-time", "part-time", "contractor", "temporary", "intern", "volunteer", "other"]
MCP_TYPE = {"Full Time": "full-time", "Part Time": "part-time", "Contractor": "contractor", "Temporary": "temporary",
            "Intern": "intern", "Volunteer": "volunteer", "Other": "other"}
# upstream label -> public value (the feed's employmentType / the MCP card's type)
EMPLOYMENT_TYPE_PUBLIC = {**{v: k for k, v in MCP_TYPE.items()},
                          "Full-time": "full-time", "Part-time": "part-time", "Internship": "intern"}
SENIORITY_PUBLIC = dict(MCP_EXPERIENCE)

JOB_SORTS = {"relevant": "relevant", "recent": "recent", "salary_asc": "salaryAsc", "salary_desc": "salaryDesc"}
COMPANY_SORTS = {"relevant": "relevant", "recent": "recent", "jobs": "jobs", "name_asc": "nameAToZ",
                 "name_desc": "nameZToA"}
TALENT_SORTS = {"relevant": "relevant", "recent": "recent"}

SALARY_PERIODS = ("hourly", "daily", "weekly", "fortnightly", "monthly", "annual")
CURRENCIES = ["USD", "AUD", "EUR", "JPY", "GBP", "CAD", "CHF", "CNY", "HKD", "NZD", "SGD", "SEK", "KRW", "NOK", "INR",
              "MXN", "TWD", "ZAR", "BRL", "IDR", "PHP", "THB", "CLP", "CZK", "DKK", "HUF", "ILS", "TRY", "PLN"]

# ---- statistics ----------------------------------------------------------------------------------------

STAT_RECORDS = ["jobs", "companies"]
STAT_TYPES = ["skills", "categories", "countries", "industries"]

# ---- countries ---------------------------------------------------------------------------------------------

COUNTRY_BY_CODE = {c["code"]: c for c in COUNTRIES}
COUNTRY_BY_NAME = {c["name"].lower(): c for c in COUNTRIES}
COUNTRY_BY_SLUG = {c["slug"]: c for c in COUNTRIES if c.get("slug")}
COUNTRY_ALIASES = {
    "uk": "GB", "great britain": "GB", "england": "GB", "britain": "GB",
    "usa": "US", "u.s.": "US", "u.s.a.": "US", "united states of america": "US", "america": "US",
    "uae": "AE", "emirates": "AE",
    "south korea": "KR", "korea": "KR", "republic of korea": "KR",
    "north korea": "KP",
    "russia": "RU", "russian federation": "RU",
    "vietnam": "VN", "viet nam": "VN",
    "czech republic": "CZ", "czechia": "CZ",
    "turkiye": "TR", "türkiye": "TR", "turkey": "TR",
    "iran": "IR", "syria": "SY", "laos": "LA", "bolivia": "BO", "venezuela": "VE", "tanzania": "TZ",
    "moldova": "MD", "macau": "MO", "macao": "MO", "taiwan": "TW", "palestine": "PS",
    "ivory coast": "CI", "cote d'ivoire": "CI", "côte d'ivoire": "CI",
    "the netherlands": "NL", "holland": "NL", "the bahamas": "BS", "the gambia": "GM",
    "drc": "CD", "congo-kinshasa": "CD", "congo-brazzaville": "CG",
    "brunei": "BN", "cape verde": "CV", "swaziland": "SZ", "eswatini": "SZ", "burma": "MM", "myanmar": "MM",
    "east timor": "TL", "timor-leste": "TL", "vatican": "VA", "vatican city": "VA", "holy see": "VA",
    "micronesia": "FM", "saint martin": "MF", "st. lucia": "LC", "st lucia": "LC",
    "hong kong sar": "HK", "philippines": "PH", "the philippines": "PH",
}
