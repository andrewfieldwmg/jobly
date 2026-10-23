from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Protocol


class JobSource(Protocol):
    """Boundary implemented by permitted feeds, ATS adapters or fixtures."""

    def fetch(self) -> Iterable[Mapping[str, object]]: ...


@dataclass(frozen=True)
class DemoProfile:
    """Fictional review policy used only by the synthetic demonstration."""

    region_terms: tuple[str, ...] = ("london", "united kingdom", "uk", "emea")
    target_families: tuple[str, ...] = (
        "professional services",
        "enterprise architecture",
        "data & ai",
        "transformation consulting",
    )
    salary_floor_gbp: int = 120_000
    maximum_queue: int = 5
    stale_after_days: int = 45


@dataclass(frozen=True)
class CanonicalJob:
    source_id: str
    source_name: str
    title: str
    company: str
    location: str
    work_model: str
    employment_type: str
    salary_min_gbp: int | None
    salary_max_gbp: int | None
    posted_at: str
    updated_at: str
    description: str
    requirements: tuple[str, ...]
    url: str
    status: str
    expected_outcome: str = ""
    alternate_source_ids: tuple[str, ...] = ()


class FixtureSource:
    def __init__(self, path: Path):
        self.path = path

    def fetch(self) -> Iterable[Mapping[str, object]]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return payload["jobs"]


def normalise_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9&]+", " ", text).strip()


def normalise_location(value: object) -> str:
    location = normalise_text(value)
    london_aliases = {
        "london",
        "london uk",
        "london united kingdom",
        "london england united kingdom",
        "greater london",
    }
    return "london" if location in london_aliases else location


def _integer(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def normalise_record(raw: Mapping[str, object]) -> CanonicalJob:
    return CanonicalJob(
        source_id=str(raw["source_id"]),
        source_name=str(raw.get("source_name") or "fixture"),
        title=str(raw.get("title") or "").strip(),
        company=str(raw.get("company") or "").strip(),
        location=str(raw.get("location") or "").strip(),
        work_model=str(raw.get("work_model") or "").strip(),
        employment_type=str(raw.get("employment_type") or "").strip(),
        salary_min_gbp=_integer(raw.get("salary_min_gbp")),
        salary_max_gbp=_integer(raw.get("salary_max_gbp")),
        posted_at=str(raw.get("posted_at") or ""),
        updated_at=str(raw.get("updated_at") or raw.get("posted_at") or ""),
        description=str(raw.get("description") or "").strip(),
        requirements=tuple(str(value).strip() for value in raw.get("requirements", []) if str(value).strip()),
        url=str(raw.get("url") or "").strip(),
        status=str(raw.get("status") or "active").strip(),
        expected_outcome=str(raw.get("expected_outcome") or "").strip(),
    )


def identity_key(job: CanonicalJob) -> str:
    return "|".join((normalise_text(job.company), normalise_text(job.title), normalise_location(job.location)))


def deduplicate(jobs: Iterable[CanonicalJob]) -> tuple[list[CanonicalJob], int]:
    by_key: dict[str, CanonicalJob] = {}
    duplicates = 0
    for job in sorted(jobs, key=lambda value: value.updated_at, reverse=True):
        key = identity_key(job)
        if key not in by_key:
            by_key[key] = job
            continue
        duplicates += 1
        current = by_key[key]
        alternate_ids = tuple(sorted(set(current.alternate_source_ids + (job.source_id,) + job.alternate_source_ids)))
        richer = job if len(job.description) > len(current.description) else current
        by_key[key] = CanonicalJob(
            **{
                **asdict(current),
                "description": richer.description,
                "requirements": richer.requirements,
                "alternate_source_ids": alternate_ids,
            }
        )
    return list(by_key.values()), duplicates


def family_for(job: CanonicalJob) -> str:
    text = normalise_text(f"{job.title} {job.description}")
    rules = (
        ("Professional Services", ("professional services", "practice director", "client delivery")),
        ("Enterprise Architecture", ("enterprise architect", "solution architect", "architecture")),
        ("Data & AI", ("data & ai", "data ai", "artificial intelligence", "agentic ai", "ai strategy")),
        ("Transformation Consulting", ("transformation", "consulting", "advisory")),
        ("Engineering / Product", ("engineering manager", "head of engineering", "product manager")),
    )
    for family, terms in rules:
        if any(term in text for term in terms):
            return family
    return "Other"


def _days_old(value: str, now: datetime) -> int:
    posted = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return max(0, (now - posted.astimezone(timezone.utc)).days)


def hard_gate(job: CanonicalJob, profile: DemoProfile, now: datetime) -> str | None:
    if normalise_text(job.status) != "active":
        return "Listing is not active"
    employment = normalise_text(job.employment_type)
    if employment not in {"full time", "permanent"}:
        return "Employment type is not permanent full-time"
    location = normalise_text(f"{job.location} {job.work_model}")
    if not any(term in location for term in profile.region_terms):
        return "Location is outside the configured region"
    if _days_old(job.posted_at, now) > profile.stale_after_days:
        return "Listing is older than the freshness limit"
    if job.salary_max_gbp is not None and job.salary_max_gbp < profile.salary_floor_gbp:
        return "Published salary range is below the configured floor"
    return None


def score_job(job: CanonicalJob, profile: DemoProfile) -> dict[str, object]:
    family = family_for(job)
    text = normalise_text(f"{job.title} {job.description} {' '.join(job.requirements)}")
    title = normalise_text(job.title)
    fit = 4.0
    evidence: list[str] = []
    gaps: list[str] = []

    family_signal = {
        "Professional Services": (3.0, "Professional Services and practice leadership"),
        "Enterprise Architecture": (2.7, "Enterprise and solution architecture"),
        "Data & AI": (2.6, "Data and AI strategy or delivery"),
        "Transformation Consulting": (2.2, "Transformation and consulting leadership"),
        "Engineering / Product": (-1.5, "Adjacent rather than core functional experience"),
        "Other": (-0.7, "Weak role-family evidence"),
    }
    delta, note = family_signal[family]
    fit += delta
    (evidence if delta > 0 else gaps).append(note)

    if re.search(r"\b(director|head of|vice president|vp)\b", title):
        fit += 1.3
        evidence.append("Target seniority and decision scope")
    elif re.search(r"\b(senior manager|principal)\b", title):
        fit += 0.8
        evidence.append("Senior management scope")
    elif re.search(r"\b(manager|lead)\b", title):
        fit += 0.2

    if any(term in text for term in ("c suite", "executive advisory", "p&l", "commercial ownership")):
        fit += 0.5
        evidence.append("Executive and commercial responsibility")
    if any(term in text for term in ("production software engineering", "recent coding leadership")):
        fit -= 1.8
        gaps.append("Recent production engineering leadership is mandatory")
    if any(term in text for term in ("security clearance required", "active clearance required")):
        fit -= 1.5
        gaps.append("Mandatory clearance is not evidenced")

    fit = round(max(0.0, min(10.0, fit)), 1)
    salary_confidence = 5.0
    if job.salary_min_gbp is not None and job.salary_min_gbp >= profile.salary_floor_gbp:
        salary_confidence = 9.5
    elif job.salary_max_gbp is not None and job.salary_max_gbp >= profile.salary_floor_gbp:
        salary_confidence = 7.5

    freshness = max(0.0, 10.0 - _days_old(job.posted_at, datetime(2026, 10, 12, tzinfo=timezone.utc)) * 0.2)
    overall = round(fit * 0.60 + salary_confidence * 0.25 + freshness * 0.15, 1)
    if overall >= 8.0 and fit >= 7.5:
        classification = "Apply"
    elif overall >= 6.8 and fit >= 6.4:
        classification = "Investigate"
    else:
        classification = "Watch"

    reason = evidence[0] if evidence else "Adjacent senior role"
    caveat = gaps[0] if gaps else (
        "Compensation is not published and needs early confirmation"
        if job.salary_max_gbp is None
        else "No material requirement gap detected in the fixture"
    )
    return {
        "source_id": job.source_id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "work_model": job.work_model,
        "family": family,
        "classification": classification,
        "score": overall,
        "fit": fit,
        "salary_confidence": salary_confidence,
        "posted_at": job.posted_at,
        "url": job.url,
        "explanation": f"{reason}. {caveat}.",
        "evidence": evidence,
        "gaps": gaps,
        "alternate_source_ids": list(job.alternate_source_ids),
        "expected_outcome": job.expected_outcome,
    }


def run_pipeline(source: JobSource, profile: DemoProfile | None = None) -> dict[str, object]:
    profile = profile or DemoProfile()
    now = datetime(2026, 10, 12, tzinfo=timezone.utc)
    raw = list(source.fetch())
    normalised = [normalise_record(record) for record in raw]
    unique, duplicate_count = deduplicate(normalised)
    rejected: list[dict[str, str]] = []
    ranked: list[dict[str, object]] = []
    for job in unique:
        rejection = hard_gate(job, profile, now)
        if rejection:
            rejected.append(
                {
                    "source_id": job.source_id,
                    "title": job.title,
                    "company": job.company,
                    "reason": rejection,
                    "expected_outcome": job.expected_outcome,
                }
            )
        else:
            ranked.append(score_job(job, profile))
    ranked.sort(key=lambda value: (-float(value["score"]), str(value["company"]), str(value["title"])))
    queue = ranked[: profile.maximum_queue]
    digest = hashlib.sha256(
        json.dumps({"queue": queue, "rejected": rejected}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "source_mode": "synthetic-fixture",
        "summary": {
            "input_records": len(raw),
            "normalised_records": len(normalised),
            "duplicates_collapsed": duplicate_count,
            "unique_records": len(unique),
            "hard_gate_rejections": len(rejected),
            "eligible_records": len(ranked),
            "review_queue": len(queue),
        },
        "eligible": ranked,
        "review_queue": queue,
        "rejected": rejected,
        "reproducibility_hash": digest,
    }


def evaluate_expected(result: Mapping[str, object], source: JobSource) -> dict[str, object]:
    expected = {
        str(record["source_id"]): str(record.get("expected_outcome") or "")
        for record in source.fetch()
        if record.get("expected_outcome")
    }
    observed: dict[str, str] = {}
    for row in result["eligible"]:
        observed[str(row["source_id"])] = str(row["classification"])
        for alternate in row.get("alternate_source_ids", []):
            observed[str(alternate)] = str(row["classification"])
    for row in result["rejected"]:
        observed[str(row["source_id"])] = "Rejected"
    checks = [
        {
            "source_id": source_id,
            "expected": outcome,
            "observed": observed.get(source_id, "Not queued"),
            "passed": observed.get(source_id, "Not queued") == outcome,
        }
        for source_id, outcome in sorted(expected.items())
    ]
    passed = sum(1 for check in checks if check["passed"])
    return {
        "cases": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "pass_rate": round(passed / len(checks), 4) if checks else None,
        "checks": checks,
    }
