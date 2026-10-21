"""Cache TTL per /himalayas/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so an omitted param and its
default share a row).

The feed is rebuilt daily by Himalayas (its docs: "The data refreshes
daily, so there is no benefit to polling") but new jobs enter the search
index within the hour; one job changes rarely once posted; company
profiles, salary benchmarks and statistics move daily at most; the
salary overview pages are regenerated daily; talent profiles change
whenever the candidate edits them."""
from datetime import timedelta

# --- raw upstream payloads shared by several routes (fetch.shared_raw) ----------
COMPANY_FEED_CACHE = timedelta(hours=1)     # company-scoped feed pages (details lookups)

# --- jobs -----------------------------------------------------------------------------
SEARCH_CACHE = timedelta(hours=1)
LATEST_CACHE = timedelta(minutes=30)
JOB_CACHE = timedelta(hours=6)
RELATED_CACHE = timedelta(hours=12)

# --- companies ----------------------------------------------------------------------------
COMPANY_SEARCH_CACHE = timedelta(hours=12)
COMPANY_CACHE = timedelta(days=1)
COMPANY_JOBS_CACHE = timedelta(hours=1)

# --- salaries / statistics -------------------------------------------------------------------
SALARY_CACHE = timedelta(days=1)
SALARY_PAGES_CACHE = timedelta(days=1)
STATISTICS_CACHE = timedelta(days=1)

# --- talent ------------------------------------------------------------------------------
TALENT_SEARCH_CACHE = timedelta(hours=6)
TALENT_PROFILE_CACHE = timedelta(hours=12)
