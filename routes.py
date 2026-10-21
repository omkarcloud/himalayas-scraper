"""The 15 Himalayas endpoints. Every path is served with and without the
`/himalayas` prefix, so code generated against the hosted API (paths like
/jobs/details) runs unchanged against this server.

Params are validated by the same marshmallow schemas the hosted API uses
(himalayas/schemas.py), so defaults, enums and error messages are
identical: unknown params are rejected, and ONE param per input accepts a
slug or a pasted himalayas.app link (`job`, `company`, `talent`) and a
country as an ISO code, name or slug. List endpoints page with `page` and
return count / per_page / current_page / total_pages / next / previous
first, exactly like the hosted API; /jobs/latest pages with `cursor` /
`next_cursor`.
"""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from schema_fields import load_query
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from himalayas import companies, jobs, lookups, salaries, schemas, talent

PREFIX = "/himalayas"


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The request query as unicode strings (bottle 0.12's .get() hands back
    latin-1 decoded bytes, so a UTF-8 "Côte d'Ivoire" would arrive garbled)."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    return f"{request.urlparts.scheme}://{request.urlparts.netloc}{request.path}?{urlencode(query)}"


def paginate(result, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next /
    previous first, then the data."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if page < total_pages else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(path, schema, impl, paginated=False):
    """Validate the query with the endpoint's schema, run it, and map every
    failure the way the hosted API does: bad params -> 400, missing entity
    -> 404, upstream failure or block -> 502, anything else -> 500."""
    params = query_dict()
    data, error = load_query(schema, params)
    if error:
        return json_response(error, 400)
    try:
        result = impl(**data)
    except ValueError as e:
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:
        return json_response({"error": f"himalayas rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Blocked as e:
        return json_response({"error": f"himalayas blocked the request, retry later: {e}"}, 502)
    except UpstreamError as e:
        return json_response({"error": f"himalayas {path} failed: {e}"}, 502)
    except Exception as e:
        return json_response({"error": f"himalayas {path} failed: {type(e).__name__}: {e}"}, 500)
    return json_response(paginate(result, params) if paginated else result)


P = True   # paginated (page)

# (public path, request schema, endpoint function, paginated) — the order of the docs.
ENDPOINTS = [
    ("/jobs/details", schemas.JobSchema, jobs.details, False),
    ("/jobs/search", schemas.JobSearchSchema, jobs.search, P),
    ("/jobs/latest", schemas.LatestSchema, jobs.latest, False),
    ("/jobs/related", schemas.JobSchema, jobs.related, False),
    ("/jobs/batch", schemas.JobBatchSchema, jobs.batch, False),
    ("/companies/details", schemas.CompanySchema, companies.details, False),
    ("/companies/search", schemas.CompanySearchSchema, companies.search, P),
    ("/companies/jobs", schemas.CompanyJobsSchema, companies.open_jobs, P),
    ("/salaries/benchmarks", schemas.SalaryBenchmarkSchema, salaries.benchmarks, False),
    ("/salaries/country", schemas.SalaryCountrySchema, salaries.country, False),
    ("/salaries/countries", schemas.EmptySchema, salaries.countries, False),
    ("/statistics", schemas.StatisticsSchema, salaries.statistics, False),
    ("/talent/profile", schemas.TalentSchema, talent.profile, False),
    ("/talent/search", schemas.TalentSearchSchema, talent.search, P),
    ("/countries", schemas.EmptySchema, lookups.countries, False),
]


def mount(path, schema, impl, paginated):
    def handler():
        return call(path, schema, impl, paginated)
    handler.__name__ = "himalayas_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route(PREFIX + path, method="GET")(handler)


for _path, _schema, _impl, _paginated in ENDPOINTS:
    mount(_path, _schema, _impl, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
