"""Marshmallow request schemas for every /himalayas/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Himalayas resolvers (refs.py). Every schema's load() output is
the kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrLinkField convention, never a
sibling `url`/`id` pair): `job` takes '<company>/<job>' or any Himalayas
job link; `company` a slug, a name or a company link; `talent` a slug,
'@slug' or a profile link; `country` an ISO code, a name or a slug; `role`
a job title or its slug; `timezone` a UTC offset in any common spelling.
"""
from marshmallow import ValidationError, fields, validate, validates_schema

from schema_fields import BaseSchema, ChoiceField, CommaListField, Flag, PageField, PositiveInt, RefField, StrippedString
from himalayas import refdata, refs
from himalayas import shared as S
from himalayas.jobs import MAX_BATCH


def _max_length(n):
    def check(value):
        if value is not None and len(value) > n:
            raise ValidationError(f"Longer than maximum length {n}.")
    return check


class CountryField(RefField):
    resolver = staticmethod(refs.resolve_country)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        if not kwargs["required"]:
            kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class JobField(RefField):
    resolver = staticmethod(refs.resolve_job)


class CompanyField(RefField):
    resolver = staticmethod(refs.resolve_company)


class CompanyListField(RefField):
    resolver = staticmethod(refs.resolve_company_list)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class TalentField(RefField):
    resolver = staticmethod(refs.resolve_talent)


class RoleField(RefField):
    resolver = staticmethod(refs.resolve_role)


class TimezoneField(RefField):
    resolver = staticmethod(refs.resolve_timezone)

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class JobListField(fields.Field):
    """'acme/dev, https://himalayas.app/companies/x/jobs/y' -> [{company_slug, job_slug}, ...] (1..MAX_BATCH)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", True)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        out = []
        for item in str(value or "").split(","):
            item = item.strip()
            if not item:
                continue
            try:
                job = refs.resolve_job(item)
            except ValueError as e:
                raise ValidationError(f"'{item}': {e}")
            if job not in out:
                out.append(job)
        if not out:
            raise ValidationError("Must list at least one job ('<company>/<job>' or link, comma-separated).")
        if len(out) > MAX_BATCH:
            raise ValidationError(f"At most {MAX_BATCH} jobs.")
        return out


class SlugListField(CommaListField):
    """'SaaS, Fintech' -> ['saas', 'fintech'] (market / benefit / tech slugs)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_items", 10)
        super().__init__(upper=False, **kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        items = super()._deserialize(value, attr, data, **kwargs)
        out = []
        for item in items or []:
            slug = S.slugify(item)
            if slug and slug not in out:
                out.append(slug)
        return out or None


def _seniority_field():
    return CommaListField(value_map=refdata.SENIORITIES, max_items=6)


def _employment_type_field():
    return CommaListField(value_map=refdata.EMPLOYMENT_TYPES, max_items=7)


# ---- jobs ----------------------------------------------------------------------------------------------------

class JobSearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(200))
    country = CountryField()
    worldwide = Flag()
    exclude_worldwide = Flag()
    seniority = _seniority_field()
    employment_type = _employment_type_field()
    company = CompanyListField()
    timezone = TimezoneField()
    salary_min = PositiveInt(max_value=10_000_000)
    salary_max = PositiveInt(max_value=10_000_000)
    markets = SlugListField()
    benefits = SlugListField()
    sort = ChoiceField(refdata.JOB_SORTS, load_default=None)
    page = PageField(max_page=refdata.MCP_MAX_PAGE)

    @validates_schema
    def validate_combination(self, data, **kwargs):
        if data.get("exclude_worldwide") and not data.get("country"):
            raise ValidationError({"exclude_worldwide": ["Needs a country."]})
        low, high = data.get("salary_min"), data.get("salary_max")
        if low is not None and high is not None and high < low:
            raise ValidationError({"salary_max": ["Must be >= salary_min."]})
        advanced = low is not None or high is not None or data.get("markets") or data.get("benefits")
        if advanced:
            for name in ("seniority", "employment_type"):
                if len(data.get(name) or []) > 1:
                    raise ValidationError({name: ["Accepts one value when salary_min / salary_max / markets / "
                                                  "benefits are set."]})
            if data.get("timezone"):
                raise ValidationError({"timezone": ["Cannot be combined with salary_min / salary_max / markets / "
                                                    "benefits."]})
        elif data.get("query") and (data.get("page") or 1) > refdata.FEED_SEARCH_MAX_RESULTS // refdata.PAGE_SIZE:
            raise ValidationError({"page": [f"A keyword search serves at most {refdata.FEED_SEARCH_MAX_RESULTS} "
                                            f"results ({refdata.FEED_SEARCH_MAX_RESULTS // refdata.PAGE_SIZE} pages)."]})


class LatestSchema(BaseSchema):
    cursor = StrippedString(required=False, load_default=None, validate=_max_length(200))
    limit = fields.Integer(load_default=20, strict=False, validate=validate.Range(min=1, max=20))   # refdata.PAGE_SIZE


class JobSchema(BaseSchema):
    job = JobField()


class JobBatchSchema(BaseSchema):
    jobs = JobListField()


# ---- companies ----------------------------------------------------------------------------------------------------

class CompanySearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(100))
    country = CountryField()
    worldwide = Flag()
    benefits = SlugListField()
    tech_stack = SlugListField()
    sort = ChoiceField(refdata.COMPANY_SORTS, load_default=None)
    page = PageField(max_page=refdata.MCP_MAX_PAGE)


class CompanySchema(BaseSchema):
    company = CompanyField()


class CompanyJobsSchema(CompanySchema):
    page = PageField(max_page=refdata.MCP_MAX_PAGE)
    sort = ChoiceField(refdata.JOB_SORTS, load_default=None)


# ---- salaries / statistics -----------------------------------------------------------------------------------------

class SalaryBenchmarkSchema(BaseSchema):
    role = RoleField()
    seniority = ChoiceField(refdata.SENIORITY_CHOICES, load_default=None)
    country = CountryField()


class SalaryCountrySchema(BaseSchema):
    country = CountryField(required=True)


class StatisticsSchema(BaseSchema):
    record = ChoiceField(refdata.STAT_RECORDS, load_default="jobs")
    type = ChoiceField(refdata.STAT_TYPES, load_default="skills")
    country = CountryField()

    @validates_schema
    def validate_type(self, data, **kwargs):
        if data.get("type") == "industries" and data.get("record") != "companies":
            raise ValidationError({"type": ["'industries' needs record=companies."]})


# ---- talent ----------------------------------------------------------------------------------------------------------

class TalentSearchSchema(BaseSchema):
    query = StrippedString(required=False, load_default=None, validate=_max_length(100))
    country = CountryField()
    sort = ChoiceField(refdata.TALENT_SORTS, load_default=None)
    page = PageField(max_page=refdata.MCP_MAX_PAGE)


class TalentSchema(BaseSchema):
    talent = TalentField()


# ---- lookups ------------------------------------------------------------------------------------------------------------

class EmptySchema(BaseSchema):
    pass
