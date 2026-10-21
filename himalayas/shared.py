"""Value helpers shared by every Himalayas parser. Safe nested access, numbers,
text, dates and HTML -> text first; then what Himalayas needs:
epoch timestamps, site links, utm stripping, slugs and the small markdown
readers the MCP server's text answers are parsed with. The generic helpers
mirror seek/shared.py (see the note at their section). Pure functions, no
network; every helper tolerates None and junk."""
import html as html_lib
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SITE = "https://himalayas.app"

# ---- generic value helpers -------------------------------------------------------------------------
# Same semantics as seek/shared.py (the indeed/seek family); copied, not
# imported, so the himalayas package stands alone — it ships as its own
# open-source repo, which must not pull in other sites' modules.

def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None


def to_int(value):
    out = num(value)
    return int(round(out)) if out is not None else None

def amount(value):
    """A money amount: whole numbers as int, others rounded to cents."""
    out = num(value)
    if out is None:
        return None
    return int(out) if float(out).is_integer() else round(out, 2)


def text(value):
    """Whitespace-collapsed, HTML-unescaped string; '' -> None. Accepts
    {"text": ...} wrappers."""
    if isinstance(value, dict):
        value = value.get("text")
    if value is None:
        return None
    out = " ".join(html_lib.unescape(str(value)).replace("\xa0", " ").split())
    return out or None


def multiline(value):
    """Like text() but keeps line breaks (review bodies, descriptions)."""
    if isinstance(value, dict):
        value = value.get("text")
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None


_LONG_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")


def iso_date(value):
    """'21 Sep 2026' / '2026-09-22T…' / 'September 22, 2026' -> 'YYYY-MM-DD'."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return "-".join(match.groups())
    for fmt in _LONG_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def lower_snake(value):
    """'Work/Life balance' / 'Benefits & perks' -> 'work_life_balance' / 'benefits_perks'."""
    value = text(value)
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or None


_BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
               "section", "article", "header", "footer", "blockquote", "pre", "hr", "dd", "dt", "dl"}
_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in ("li", "br"):
            return
        elif tag in ("ul", "ol"):
            self.parts.append("\n\n")      # a list ends its paragraph
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(value):
    """An HTML fragment -> readable plain text: block elements become line
    breaks, list items get a dash, runs of blank lines collapse."""
    value = value if isinstance(value, str) else None
    if not value:
        return None
    if "<" not in value:
        return multiline(value)
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception:
        return multiline(re.sub(r"<[^>]+>", " ", value))
    raw = "".join(parser.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"\n\n(- )", r"\n\1", out).strip()   # list items stay tight
    return out or None


# ---- dates ---------------------------------------------------------------------------------------

def epoch_to_iso(value):
    """1792399742 -> '2026-10-19T08:49:02Z' (UTC, second precision); junk -> None."""
    seconds = num(value)
    if seconds is None or seconds <= 0:
        return None
    if seconds > 10_000_000_000:          # milliseconds
        seconds /= 1000
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


# ---- links ----------------------------------------------------------------------------------------

_TRACKING_PARAMS = ("ref", "source", "fbclid", "gclid")


def clean_link(value):
    """Drop utm_* / ref / source tracking params and fragments from a link;
    '' / None -> None; a bare 'linkedin.com/in/x' gets https://."""
    value = text(value)
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        if value.startswith("//"):
            value = "https:" + value
        elif re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", value, re.I):
            value = "https://" + value
        else:
            return value
    parts = urlparse(value)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not (k.lower().startswith("utm_") or k.lower() in _TRACKING_PARAMS)]
    return urlunparse(parts._replace(query=urlencode(query), fragment=""))


def job_link(company_slug, job_slug):
    return f"{SITE}/companies/{company_slug}/jobs/{job_slug}" if company_slug and job_slug else None


def company_link(slug):
    return f"{SITE}/companies/{slug}" if slug else None


def talent_link(slug):
    return f"{SITE}/@{slug}" if slug else None


def slugs_from_job_link(value):
    """'https://himalayas.app/companies/acme/jobs/dev?x' -> ('acme', 'dev'); else (None, None)."""
    match = re.search(r"/companies/([a-z0-9][a-z0-9-]*)/jobs/([a-z0-9][a-z0-9-]*)", str(value or ""), re.I)
    return (match.group(1).lower(), match.group(2).lower()) if match else (None, None)


def slug_from_company_link(value):
    match = re.search(r"/companies/([a-z0-9][a-z0-9-]*)", str(value or ""), re.I)
    return match.group(1).lower() if match else None


def slug_from_talent_link(value):
    match = re.search(r"/@([A-Za-z0-9][\w.-]*)", str(value or ""))
    return match.group(1) if match else None


def slugify(value):
    """'Software Engineer' / 'Software-Engineer' -> 'software-engineer'."""
    value = text(value)
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or None


def category(value):
    """'Benefits-Coordinator' / 'Benefits Coordinator' -> {name, slug}."""
    raw = text(value)
    if not raw:
        return None
    name = " ".join(raw.replace("-", " ").split())
    return {"name": name, "slug": slugify(raw)}


def categories(values):
    out, seen = [], set()
    for item in as_list(values) if isinstance(values, list) else split_bullets(values):
        cat = category(item)
        if cat and cat["slug"] not in seen:
            seen.add(cat["slug"])
            out.append(cat)
    return out


# ---- lists -------------------------------------------------------------------------------------------

def split_bullets(value, sep=r"\s*[•,]\s*"):
    """'a • b • c' / 'a, b, c' -> ['a', 'b', 'c'] (trimmed, deduped, '' dropped)."""
    value = text(value)
    if not value:
        return []
    out = []
    for item in re.split(sep, value):
        item = item.strip(" •,")
        if item and item not in out:
            out.append(item)
    return out


def split_commas(value):
    return split_bullets(value, sep=r"\s*,\s*")


def more_count(value):
    """'a • b +12 more' -> 12 (the items the MCP server left out); None otherwise."""
    match = re.search(r"\+\s*(\d+)\s+more\b", str(value or ""))
    return int(match.group(1)) if match else None


def without_more(value):
    return re.sub(r"\s*\+\s*\d+\s+more\b.*$", "", str(value or "")).strip()


# ---- markdown readers (the MCP server answers in markdown) -------------------------------------------

_EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]+")


def strip_md(value):
    """Remove **bold**, emoji and surrounding whitespace."""
    if value is None:
        return None
    out = str(value).replace("**", "")
    out = _EMOJI_RE.sub("", out)
    return " ".join(out.split()) or None


def is_verified(value):
    return "✅" in str(value or "")


def sections(markdown):
    """Split on '## ' headings -> {'' : preamble, 'About': body, ...} (bodies
    stripped, headings without markup)."""
    out, current, buf = {}, "", []
    for line in str(markdown or "").splitlines():
        if line.startswith("## "):
            out[current] = "\n".join(buf).strip()
            current, buf = strip_md(line[3:]) or "", []
        else:
            buf.append(line)
    out[current] = "\n".join(buf).strip()
    return out


_KV_RE = re.compile(r"^\s*(?:[^\w*]*)\*\*([^*]+?):\*\*\s*(.*?)\s*$")


def kv_lines(block):
    """'**Type:** Full-time' lines -> {'Type': 'Full-time'} (first wins);
    emoji before the key are ignored."""
    out = {}
    for line in str(block or "").splitlines():
        match = _KV_RE.match(line)
        if match:
            key = " ".join(match.group(1).split())
            out.setdefault(key, match.group(2).strip())
    return out


def kv_pairs(block):
    """Like kv_lines but ordered [(key, value), ...] with every occurrence."""
    out = []
    for line in str(block or "").splitlines():
        match = _KV_RE.match(line)
        if match:
            out.append((" ".join(match.group(1).split()), match.group(2).strip()))
    return out


def md_entries(markdown):
    """The '---'-separated entries of an MCP list answer (header dropped)."""
    body = str(markdown or "")
    parts = re.split(r"\n\s*---\s*\n", body)
    out = []
    for part in parts:
        part = part.strip()
        if part:
            out.append(part)
    return out


def found_total(markdown):
    """'Found 302 jobs matching ...' / '## Remote Talent — Page 1 (95 total)' -> 302 / 95."""
    head = str(markdown or "")[:300]
    match = re.search(r"\bFound\s+([\d,]+)\s+", head) or re.search(r"\(([\d,]+)\s+total\)", head)
    return to_int(match.group(1).replace(",", "")) if match else None


def shown_page(markdown):
    match = re.search(r"showing page\s+(\d+)|Page\s+(\d+)", str(markdown or "")[:300])
    return to_int(match.group(1) or match.group(2)) if match else None


def md_links(block):
    """'🔗 **Company Page:** https://…' lines -> {'company_page': link} with
    tracking params stripped; '**Social:** Twitter: u • LinkedIn: u' -> under 'social'."""
    out = {}
    for key, value in kv_pairs(block):
        if key.lower() == "social":
            social = {}
            for item in re.split(r"\s*•\s*", value):
                name, _, link = item.partition(":")
                if link.strip():
                    social[lower_snake(name)] = clean_link(link.strip())
            out["social"] = social
            continue
        link = re.search(r"https?://\S+|[\w.-]+\.[a-z]{2,}\S*", value, re.I)
        if link:
            out[lower_snake(key)] = clean_link(link.group(0).rstrip(".,)"))
    return out


# ---- salary labels -------------------------------------------------------------------------------------

_MONEY_RE = re.compile(r"(?<![\w.])\$?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*([kK])?(?![\w.])")
_CURRENCY_RE = re.compile(r"\b([A-Z]{3})\b")
_CURRENCY_WORDS = {"THE", "AND", "FOR", "PER", "NOT", "MIN", "MAX"}
_PERIODS = [
    ("hourly", r"per hour|an hour|/\s*hour|hourly|/hr\b"),
    ("daily", r"per day|a day|daily"),
    ("weekly", r"per week|a week|weekly"),
    ("fortnightly", r"per fortnight|fortnightly"),
    ("monthly", r"per month|a month|monthly|/\s*month"),
    ("annual", r"per year|a year|/\s*year|annual|yearly|per annum"),
]


def salary_from_label(label):
    """'$75,000 - $95,000 USD' / '50,400 - 79,200 EUR' / '$4,500 USD per month
    (about $54,000 USD a year)' / 'From 70,000 (INR)' -> {min, max, currency,
    period}; 'Competitive salary' -> None."""
    label = strip_md(label)
    if not label or re.search(r"competitive|not (?:disclosed|specified)|undisclosed", label, re.I):
        return None
    head = label.split("(about", 1)[0]
    figures = []
    for match in _MONEY_RE.finditer(head):
        value = num(match.group(1).replace(",", ""))
        if value is None:
            continue
        if match.group(2):
            value *= 1000
        figures.append(value)
    currency = None
    for match in _CURRENCY_RE.finditer(label):
        if match.group(1) in _CURRENCY_WORDS:
            continue
        currency = match.group(1)
        break
    if currency is None and "$" in label:
        currency = "USD"
    period = None
    low = head.lower()
    for name, pattern in _PERIODS:
        if re.search(pattern, low):
            period = name
            break
    if not figures:
        return None
    lo, hi = amount(min(figures)), amount(max(figures))
    if len(figures) == 1:
        if re.search(r"\bfrom\b|\bmin", low):
            hi = None
        elif re.search(r"\bup to\b|\bmax", low):
            lo = None
    return {"min": lo, "max": hi, "currency": currency, "period": period}
