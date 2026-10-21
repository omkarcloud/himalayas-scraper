"""/himalayas/talent/* — the public candidate marketplace, read from the
site's own pages since 2026-10-20 (the MCP talent tools now need a signed-in
account):

  search   /talent[/<job-title-or-skill-slug>]?country=<Name>&sort=recent&page=N
           — 20 cards per page: name, headline, country, expected salary,
           job categories, skills, recent experience (Cloudflare-challenged:
           fetch.talent_page replays a patchright-minted clearance)
  profile  /@<slug> — the full public profile: availability, location, work
           authorization, expected salary, what they are looking for, bio,
           experience with descriptions, education, tech stack, links

`query` picks the site's job-title / skill category (`react developer` ->
/talent/react-developer); the site has no free-text talent search."""
from urllib.parse import urlencode

from himalayas import fetch
from himalayas import shared as S
from himalayas import talent_html as T


def search(query=None, country=None, sort=None, page=1):
    category = S.slugify(query) if query else None
    path = f"/talent/{category}" if category else "/talent"
    params = {"country": country, "sort": "recent" if sort == "recent" else None,
              "page": page if page and page > 1 else None}
    query_string = urlencode({k: v for k, v in params.items() if v})
    try:
        html = fetch.talent_page(path + (f"?{query_string}" if query_string else ""),
                                 label=f"talent search {query!r} p{page}")
    except fetch.HimalayasNotFound:
        raise fetch.HimalayasNotFound(f"Himalayas has no talent category matching '{query}'. Use a job title or "
                                      f"skill, e.g. 'react developer', 'product designer' or 'python'.")
    result = T.search_page(html, page)
    result["query"] = query
    result["category"] = {"slug": category, "link": f"https://himalayas.app/talent/{category}"} if category else None
    return result


def profile(talent):
    html = fetch.profile_page(talent)
    result = T.profile_page(html)
    if result is None or not result.get("name"):
        raise fetch.HimalayasNotFound(f"Himalayas has no talent profile @{talent}")
    result["slug"] = result.get("slug") or talent
    result["link"] = result.get("link") or S.talent_link(talent)
    return result
