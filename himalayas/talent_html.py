"""Talent pages (HTML) -> clean API objects.

Since 2026-10-20 the MCP server's talent tools need a signed-in Himalayas
account (`search_talent` / `get_talent_profile` answer 401 "Authentication
required"), so talent data comes from the site's own server-rendered pages:

  /talent[/<role-slug>][?country=<Name>&sort=recent&page=N]   search results, 20 per page
  /@<slug>                                                      a candidate's public profile

The search pages sit behind Cloudflare (fetch.talent_page replays a
patchright-minted cf_clearance); profiles usually do not. Neither page
embeds the data as JSON — everything below reads the rendered markup.
Pure functions, no network; every parser tolerates missing nodes.

Dropped on purpose: avatar initials, the "Message" / "Share profile" /
"Report" controls, ads, the "People also viewed" rail, the sign-up promos,
and Next.js image-proxy parameters (the CDN link inside them is kept)."""
import re
from math import ceil
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from himalayas import refdata
from himalayas import shared as S
from himalayas.shared import text

# the site's availability labels -> the account setting behind them
AVAILABILITY = {"looking for a job": "actively_searching", "open to opportunities": "open_to_roles",
                "not looking for work": "closed_to_roles"}
VERIFIED_LABEL = "verified their ID"
PAGE_SIZE = 20


def soup_of(html):
    return BeautifulSoup(html or "", "lxml")


def _classes(tag):
    value = tag.get("class") if tag is not None else None
    return value if isinstance(value, list) else []


def _has(*names):
    """class_ filter: every name in the element's class list."""
    def check(value):
        return bool(value) and all(n in value.split() for n in names)
    return check


def _txt(tag, sep=" "):
    return text(tag.get_text(sep, strip=True)) if tag is not None else None


def image_link(src):
    """'/_next/image?url=https%3A%2F%2Fcdn…&w=96' -> 'https://cdn…'; plain URLs pass through."""
    src = text(src)
    if not src:
        return None
    if src.startswith("/_next/image"):
        inner = parse_qs(urlparse(src).query).get("url", [None])[0]
        return S.clean_link(unquote(inner)) if inner else None
    if src.startswith("/"):
        return refdata.SITE + src
    return S.clean_link(src)


def _country_ref(anchor):
    """<a href="/talent/countries/romania"><img title="ro">Romania</a> -> {name, slug, code}."""
    if anchor is None:
        return None
    slug = (anchor.get("href") or "").rstrip("/").rsplit("/", 1)[-1] or None
    img = anchor.find("img")
    code = (img.get("title") or "").upper() if img is not None else ""
    record = refdata.COUNTRY_BY_SLUG.get(slug or "") or refdata.COUNTRY_BY_CODE.get(code)
    return {"name": _txt(anchor) or (record or {}).get("name"), "slug": slug,
            "code": code or (record or {}).get("code") or None}


def _tag_links(container):
    """Role / skill chips -> ([{name, slug}] categories, [names] skills)."""
    categories, skills = [], []
    for a in container.find_all("a", href=True) if container is not None else []:
        href = a["href"]
        if not href.startswith("/talent/") or href.startswith("/talent/countries/"):
            continue
        name = _txt(a)
        if not name:
            continue
        if href.startswith("/talent/skills/"):
            if name not in skills:
                skills.append(name)
        else:
            slug = href.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            if all(c["slug"] != slug for c in categories):
                categories.append({"name": name, "slug": slug})
    return categories, skills


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def month(value):
    """'Apr 2026' -> '2026-04'; '2019' -> '2019'; 'Present' / junk -> None."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{4})$", value)
    if match and match.group(1).lower() in _MONTHS:
        return f"{match.group(2)}-{_MONTHS[match.group(1).lower()]:02d}"
    match = re.match(r"(\d{4})$", value)
    return match.group(1) if match else None


def date_range(value):
    """'May 2020 - Present ( 6 years 5 months )' -> {started_at, ended_at, is_current, duration}."""
    value = text(value) or ""
    duration = re.search(r"\(\s*([^)]*?)\s*\)", value)
    head = re.sub(r"\(.*?\)", "", value).strip()
    start, _, end = head.partition(" - ")
    current = bool(re.search(r"present|current|now", end, re.I))
    return {"started_at": month(start), "ended_at": None if current else month(end),
            "is_current": current if (start or end) else None,
            "duration": text(duration.group(1)) if duration else None}


# ---- search pages ----------------------------------------------------------------------------------------

_COUNT_RE = re.compile(r"(?:of\s+)?([\d,]+)\s+remote workers", re.I)


def _total(soup):
    for h2 in soup.find_all("h2"):
        label = _txt(h2) or ""
        match = re.search(r"(?:\d[\d,]*\s*-\s*\d[\d,]*\s+of\s+)?([\d,]+)\s+remote workers", label, re.I)
        if match:
            return S.to_int(match.group(1).replace(",", ""))
    return None


def _card_experience(card):
    out = []
    label = next((p for p in card.find_all("p") if _txt(p) == "Experience"), None)
    box = label.find_next_sibling("div") if label is not None else None
    for row in box.find_all("div", class_=_has("items-center", "gap-x-3"), recursive=False) if box is not None else []:
        title = row.find("p", class_=_has("font-medium", "text-gray-900"))
        company = row.find(["p", "a"], class_=_has("font-medium", "text-gray-700"))
        dates = row.find("p", class_=_has("text-sm", "text-gray-600"))
        entry = {"title": _txt(title), "company": _txt(company)}
        entry.update(date_range(_txt(dates)))
        if entry["title"] or entry["company"]:
            out.append(entry)
    return out


def search_card(card):
    """One result card -> talent summary."""
    anchor = card.find("a", href=re.compile(r"^/@"))
    slug = S.slug_from_talent_link(anchor.get("href")) if anchor is not None else None
    name_tag = card.find("h3")
    avatar = next((img for img in card.find_all("img") if img.get("alt") and "flag" not in (img.get("src") or "")
                   and "react-circle-flags" not in (img.get("src") or "")), None)
    # the headline's own box is exactly "mb-4 md:mb-6" (the name row also carries mb-4)
    headline_box = next((d for d in card.find_all("div") if set(_classes(d)) == {"mb-4", "md:mb-6"}), None)
    headline = headline_box.find("p") if headline_box is not None else None
    country_link = card.find("a", href=re.compile(r"^/talent/countries/"))
    salary = None
    if country_link is not None:
        chip = country_link.find_next_sibling("p")
        salary = _salary(_txt(chip)) if chip is not None else None
    categories, skills = _tag_links(card)
    return {
        "name": _txt(name_tag),
        "slug": slug,
        "link": S.talent_link(slug),
        "is_id_verified": bool(card.find(attrs={"aria-label": re.compile(VERIFIED_LABEL, re.I)})),
        "avatar_link": image_link(avatar.get("src")) if avatar is not None else None,
        "headline": _txt(headline),
        "country": _country_ref(country_link),
        "expected_salary": salary,
        "job_categories": categories,
        "skills": skills,
        "recent_experience": _card_experience(card),
    }


def search_page(html, page=1):
    """/talent… page -> {talent, pagination}."""
    soup = soup_of(html)
    cards = []
    for anchor in soup.find_all("a", href=re.compile(r"^/@[^/?]+$")):
        if _txt(anchor) != "View profile":
            continue
        cards.append(search_card(anchor.parent))
    total = _total(soup)
    if total is None:
        total = len(cards)
    return {
        "talent": cards,
        "pagination": {"page": page, "items_per_page": PAGE_SIZE,
                       "total_pages": ceil(total / PAGE_SIZE) if total else 0, "total_count": total},
    }


# ---- profile pages ------------------------------------------------------------------------------------------

def _section_list(main, heading):
    h2 = next((h for h in main.find_all("h2") if _txt(h) == heading), None)
    if h2 is None:
        return []
    box = h2.find_next("div", class_=_has("flex-col", "gap-y-4"))
    return box.find_all("article", recursive=False) if box is not None else []


def _logo(article):
    img = next((i for i in article.find_all("img") if (i.get("alt") or "").endswith(" logo")), None)
    return image_link(img.get("src")) if img is not None else None


def _experience(main):
    out = []
    for art in _section_list(main, "Experience"):
        body = art.find("div", class_="flex-grow") or art
        company_tag = body.find(["a", "p"], class_=_has("font-medium", "text-gray-700"))
        company_link = None
        if company_tag is not None and company_tag.name == "a":
            company_link = S.clean_link(company_tag.get("href"))
        company_slug = S.slug_from_company_link(company_link)
        dates_tag = body.find("div", class_=_has("items-center", "gap-x-2"))
        description = next((p for p in body.find_all("p", recursive=False)), None)
        _, skills = None, [a for a in (_txt(a) for a in body.find_all("a", href=re.compile(r"^/talent/"))) if a]
        entry = {
            "title": _txt(body.find("h3")),
            "company": {"name": _txt(company_tag), "slug": company_slug,
                        "link": S.company_link(company_slug) if company_slug else None,
                        "logo_link": _logo(art)},
        }
        entry.update(date_range(_txt(dates_tag.find("p")) if dates_tag is not None else None))
        entry["description"] = S.multiline(description.get_text("\n", strip=True)) if description is not None else None
        entry["skills"] = list(dict.fromkeys(skills))
        out.append(entry)
    return out


def _education(main):
    out = []
    for art in _section_list(main, "Education"):
        body = art.find("div", class_="flex-grow") or art
        degree_tag = body.find("p", class_=_has("font-medium", "text-gray-700"))
        parts = [text(s) for s in (degree_tag.stripped_strings if degree_tag is not None else []) if text(s) and s.strip() != ","]
        grade, dates, extra = None, None, []
        for p in body.find_all("p"):
            label = _txt(p) or ""
            if p is degree_tag or not label:
                continue
            if label.lower().startswith("grade"):
                grade = text(label.split(":", 1)[-1])
            elif re.search(r"\b\d{4}\b", label) and " - " in label and dates is None:
                dates = label
            else:
                extra.append(label)
        entry = {"school": _txt(body.find("h3")), "logo_link": _logo(art),
                 "degree": parts[0] if parts else None, "field_of_study": parts[1] if len(parts) > 1 else None,
                 "grade": grade}
        span = date_range(dates)
        entry.update({"started_at": span["started_at"], "ended_at": span["ended_at"]})
        entry["description"] = "\n".join(extra) or None
        out.append(entry)
    return out


def _tech_stack(main):
    h2 = next((h for h in main.find_all("h2") if _txt(h) == "Tech stack"), None)
    box = h2.find_next("div", class_=_has("grid")) if h2 is not None else None
    out = []
    for a in box.find_all("a", href=re.compile(r"^/companies/tech/")) if box is not None else []:
        img = a.find("img")
        out.append({"name": _txt(a), "slug": a["href"].rstrip("/").rsplit("/", 1)[-1],
                    "logo_link": image_link(img.get("src")) if img is not None else None})
    return out


def _sidebar(main):
    """{label: container} for the right-hand facts box (Availability, Location, …)."""
    out = {}
    for h3 in main.find_all("h3", class_=_has("text-gray-500")):
        label = _txt(h3)
        if label and label not in out:
            out[label] = h3.parent
    return out


def _social_links(box):
    out = {}
    for a in box.find_all("a", href=True) if box is not None else []:
        href = re.sub(r"^(https?://)+(https?://)", r"\2", a["href"].strip())
        href = re.sub(r"^https?://https?://", "https://", href)
        label = _txt(a.find("span", class_="sr-only")) or _txt(a) or ""
        network = S.lower_snake(label.rsplit("'s ", 1)[-1]) if "'s " in label else S.lower_snake(urlparse(href).hostname or "")
        if network and network not in out:
            out[network] = S.clean_link(href)
    return out


def _salary(label):
    """'145k-200k USD' -> {min, max, currency, period}."""
    label = text(label)
    if not label:
        return None
    currency = re.search(r"\b([A-Z]{3})\b", label)
    figures = []
    for raw, k in re.findall(r"([\d,.]+)\s*([kKmM])?", label):
        value = S.num(raw.replace(",", ""))
        if value is None:
            continue
        if k:
            value *= 1000 if k.lower() == "k" else 1_000_000
        figures.append(S.amount(value))
    if not figures:
        return None
    return {"min": figures[0], "max": figures[1] if len(figures) > 1 else None,
            "currency": currency.group(1) if currency else None, "period": "annual"}


def _role_from_title(soup, name):
    """'<title>Jason Head - Lead UX Designer - SS&C Technologies | Himalayas' -> 'Lead UX Designer'."""
    title = _txt(soup.find("title")) or ""
    title = title.rsplit("|", 1)[0].strip()
    parts = [p.strip() for p in title.split(" - ")]
    if len(parts) >= 2 and (not name or parts[0] == name):
        return parts[1] or None
    return None


def profile_page(html):
    """/@<slug> page -> the full public profile; None when it is not a profile."""
    soup = soup_of(html)
    main = soup.find("main")
    if main is None or main.find("h1") is None:
        return None
    header = main.find("section")
    name = _txt(main.find("h1"))
    handle = header.find("p", class_=_has("md:text-2xl")) if header is not None else None
    slug = (_txt(handle) or "").replace("@", "").replace(" ", "") or None
    cover = main.find("img")
    avatar = next((img for img in main.find_all("img") if name and img.get("alt") == name), None)
    headline = header.find("p", class_=_has("line-clamp-2")) if header is not None else None
    side = _sidebar(main)
    availability = _txt(side["Availability"].find("div")) if "Availability" in side else None
    if availability is None and header is not None:
        badge = header.find("div", class_=_has("rounded-md"))
        availability = _txt(badge)
    location_box = side.get("Location")
    location_name = None
    if location_box is not None:
        location_name = text(" ".join(s for s in location_box.stripped_strings if s != "Location"))
    location = _country_ref(header.find("a", href=re.compile(r"^/talent/countries/"))) if header is not None else None
    if location is None and location_name:
        record = refdata.COUNTRY_BY_NAME.get(location_name.lower())
        location = {"name": location_name, "slug": (record or {}).get("slug"), "code": (record or {}).get("code")}
    authorized = [_country_ref(a) for a in side["Authorized to work in"].find_all("a", href=re.compile(r"^/talent/countries/"))] \
        if "Authorized to work in" in side else []
    portfolio = side["Portfolio"].find("a", href=True) if "Portfolio" in side else None
    salary_box = side.get("Salary expectations")
    salary_label = text(" ".join(s for s in salary_box.stripped_strings if s != "Salary expectations")) if salary_box else None
    categories, _ = _tag_links(side.get("Job categories"))
    skills = [c["name"] for c in _tag_links(side.get("Skills"))[0]] + _tag_links(side.get("Skills"))[1]
    looking = next((h for h in main.find_all("h2") if (_txt(h) or "").startswith("What I")), None)
    looking_for = looking.find_next("article") if looking is not None else None
    about = None
    for article in main.find_all("article", class_=_has("prose-content")):
        if looking_for is not None and article is looking_for:
            continue
        about = S.multiline("\n\n".join(p.get_text(" ", strip=True) for p in article.find_all("p")) or article.get_text("\n", strip=True))
        break
    known = {"Availability", "Location", "Authorized to work in", "Portfolio", "Salary expectations", "Social media",
             "Job categories", "Skills"}
    details = {S.lower_snake(k): text(" ".join(s for s in box.stripped_strings if s != k))
               for k, box in side.items() if k not in known}
    return {
        "name": name,
        "slug": slug,
        "link": S.talent_link(slug),
        "is_id_verified": bool(main.find(attrs={"aria-label": re.compile(VERIFIED_LABEL, re.I)})),
        "role": _role_from_title(soup, name),
        "headline": _txt(headline),
        "availability": AVAILABILITY.get((availability or "").lower(), S.lower_snake(availability)),
        "location": location,
        "authorized_to_work_in": [c for c in authorized if c],
        "expected_salary": _salary(salary_label),
        "looking_for": S.multiline(looking_for.get_text("\n", strip=True)) if looking_for is not None else None,
        "about": about,
        "job_categories": categories,
        "skills": list(dict.fromkeys(skills)),
        "experience": _experience(main),
        "education": _education(main),
        "tech_stack": _tech_stack(main),
        "avatar_link": image_link(avatar.get("src")) if avatar is not None else None,
        "cover_image_link": image_link(cover.get("src")) if cover is not None and not cover.get("alt") else None,
        "portfolio_link": S.clean_link(portfolio.get("href")) if portfolio is not None else None,
        "social_links": _social_links(side.get("Social media")),
        "details": {k: v for k, v in details.items() if k and v} or None,
    }
