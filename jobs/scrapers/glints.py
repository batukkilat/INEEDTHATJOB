import asyncio
import json as _json
import random
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from config import settings
from db.models import Job
from jobs.scrapers.base import BaseScraper
from utils.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://glints.com"
_GQL_URL = "https://glints.com/api/v2-alc/graphql"

_SEARCH_QUERY = """
query searchJobsV3($data: JobSearchConditionInput!) {
  searchJobsV3(data: $data) {
    jobsInPage {
      id
      title
      workArrangementOption
      status
      createdAt
      updatedAt
      company {
        ...CompanyFields
        __typename
      }
      citySubDivision {
        id
        name
        __typename
      }
      city {
        ...CityFields
        __typename
      }
      salaries {
        ...SalaryFields
        __typename
      }
      location {
        id
        name
        formattedName
        level
        __typename
      }
      skills {
        skill {
          id
          name
          __typename
        }
        mustHave
        __typename
      }
      __typename
    }
    hasMore
    __typename
  }
}

fragment CompanyFields on Company {
  id
  name
  brandName
  status
  __typename
}

fragment CityFields on City {
  id
  name
  __typename
}

fragment SalaryFields on JobSalary {
  id
  salaryType
  salaryMode
  maxAmount
  minAmount
  CurrencyCode
  __typename
}
"""

def _slate_to_text(raw: str) -> str | None:
    """Extract plain text from Glints Draft.js JSON description."""
    try:
        doc = _json.loads(raw)
        blocks = doc.get("blocks") or []
        lines = [b.get("text", "") for b in blocks if b.get("text", "").strip()]
        return "\n".join(lines) or None
    except Exception:
        return raw[:2000] if raw else None


_HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://glints.com",
    "referer": "https://glints.com/id/en/opportunities/jobs/explore",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "x-glints-country-code": "ID",
}


def _parse_job_item(item: dict, scraped_at: str) -> Job | None:
    external_id = str(item.get("id") or "")
    if not external_id:
        return None

    title = item.get("title") or ""
    if not title:
        return None

    company = (item.get("company") or {}).get("name") or ""

    city = (
        (item.get("citySubDivision") or {}).get("name")
        or (item.get("city") or {}).get("name")
        or (item.get("location") or {}).get("formattedName")
        or ""
    )
    location = f"{city}, Indonesia".strip(", ") if city else "Indonesia"

    arrangement = str(item.get("workArrangementOption") or "").upper()
    remote_type = None
    if arrangement == "REMOTE":
        remote_type = "remote"
    elif arrangement == "HYBRID":
        remote_type = "hybrid"

    url = f"{_BASE_URL}/id/opportunities/jobs/{external_id}"

    posted_date = item.get("createdAt") or item.get("updatedAt") or None

    salaries = item.get("salaries") or []
    salary_min = salary_max = None
    if salaries:
        s = salaries[0]
        salary_min = s.get("minAmount")
        salary_max = s.get("maxAmount")

    return Job(
        platform="glints",
        external_id=external_id,
        url=url,
        title=title,
        company=company,
        location=location,
        remote_type=remote_type,
        posted_date=posted_date,
        scraped_at=scraped_at,
        status="new",
        salary_min=float(salary_min) if salary_min else None,
        salary_max=float(salary_max) if salary_max else None,
        description=None,
    )


class GlintsScraper(BaseScraper):
    platform = "glints"

    async def scrape(self, max_pages: int = 5, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Python Developer"]

        jobs: list[Job] = []
        seen_ids: set[str] = set()
        scraped_at = datetime.now(timezone.utc).isoformat()

        for keyword in keywords:
            log.info("glints_scrape_keyword", keyword=keyword)
            for page_num in range(1, max_pages + 1):
                payload = {
                    "operationName": "searchJobsV3",
                    "variables": {
                        "data": {
                            "CountryCode": "ID",
                            "SearchTerm": keyword,
                            "includeExternalJobs": True,
                            "pageSize": 30,
                            "page": page_num,
                        }
                    },
                    "query": _SEARCH_QUERY,
                }
                try:
                    resp = await asyncio.to_thread(
                        cffi_requests.post,
                        f"{_GQL_URL}?op=searchJobsV3",
                        json=payload,
                        headers=_HEADERS,
                        impersonate="chrome",
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    log.warning("glints_request_failed", keyword=keyword, page=page_num, error=str(e))
                    break

                search_result = (data.get("data") or {}).get("searchJobsV3") or {}
                items = search_result.get("jobsInPage") or []
                has_more = search_result.get("hasMore", False)

                if not items:
                    log.warning("glints_no_jobs", keyword=keyword, page=page_num)
                    break

                before = len(jobs)
                for item in items:
                    job = _parse_job_item(item, scraped_at)
                    if job and job.external_id not in seen_ids:
                        seen_ids.add(job.external_id)
                        jobs.append(job)

                log.debug("glints_page_done", keyword=keyword, page=page_num,
                          new=len(jobs) - before, total=len(jobs))

                if not has_more or len(jobs) == before:
                    break

                await asyncio.sleep(random.uniform(1.0, 2.0))

            log.info("glints_scrape_complete", total=len(jobs))
        return jobs

    async def fetch_description(self, external_id: str) -> str | None:
        query = """
        query getJobById($id: String!) {
          getJobById(id: $id) {
            descriptionJsonString
            __typename
          }
        }
        """
        payload = {
            "operationName": "getJobById",
            "variables": {"id": external_id},
            "query": query,
        }
        try:
            resp = await asyncio.to_thread(
                cffi_requests.post,
                f"{_GQL_URL}?op=getJobById",
                json=payload,
                headers=_HEADERS,
                impersonate="chrome",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = (data.get("data") or {}).get("getJobById", {}).get("descriptionJsonString")
            return _slate_to_text(raw) if raw else None
        except Exception as e:
            log.warning("glints_fetch_description_failed", external_id=external_id, error=str(e))
            return None
