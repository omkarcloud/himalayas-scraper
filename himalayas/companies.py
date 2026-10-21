"""/himalayas/companies/* — company search / directory, company profiles and
a company's open jobs. Search and profiles come from the MCP server
(search_companies / get_companies / get_company_details, markdown parsed by
parsers.py); open jobs from the company-scoped search feed (JSON)."""
from himalayas import fetch
from himalayas import parsers as P
from himalayas import shared as S


def search(query=None, country=None, worldwide=None, benefits=None, tech_stack=None, sort=None, page=1):
    """One page (20) of companies. Without a keyword / benefit / tech-stack
    filter it is the directory (get_companies: newest first)."""
    filtered = bool(query or benefits or tech_stack or (sort and sort != "relevant"))
    if filtered:
        args = {"keyword": query, "page": page, "country": country, "worldwide": True if worldwide else None,
                "benefits": ",".join(benefits) if benefits else None,
                "tech_stack": ",".join(tech_stack) if tech_stack else None, "sort": sort}
        text = fetch.mcp("search_companies", args, label=f"company search {query!r} p{page}")
    else:
        args = {"page": page, "country": country, "worldwide": True if worldwide else None}
        text = fetch.mcp("get_companies", args, label=f"companies p{page}")
    result = P.mcp_company_list(text, page)
    result["query"] = query
    return result


def details(company):
    """The company profile: about, size, founded, CEO, locations, markets,
    tech stack by category, benefits, website and social links."""
    text = fetch.mcp("get_company_details", {"company_slug": company}, label=f"company {company}")
    result = P.mcp_company_details(text)
    if result is None or not result.get("name"):
        raise fetch.HimalayasNotFound(f"Himalayas has no company '{company}'")
    result["slug"] = result.get("slug") or company
    result["link"] = result.get("link") or S.company_link(company)
    return result


def open_jobs(company, page=1, sort=None):
    """A company's open jobs from the search feed (full job objects)."""
    try:
        raw = fetch.feed_search({"company": company, "sort": sort, "page": page}, label=f"jobs of {company} p{page}")
    except fetch.HimalayasBadRequest as e:
        # the feed answers an unknown slug with 400 {"errors": "Invalid company"}
        if "invalid company" in str(e).lower():
            raise fetch.HimalayasNotFound(f"Himalayas has no company '{company}'")
        raise
    result = P.feed_search_result(raw, page)
    result["company"] = {"slug": company, "link": S.company_link(company)}
    return result
