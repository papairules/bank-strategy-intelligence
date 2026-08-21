from copy import deepcopy


def standard_us_full_time() -> dict:
    return {
        "search_summary": {"title": "Senior Platform Engineer", "externalPath": "/job/CHARLOTTE-NC/Senior-Platform-Engineer_R-100001", "bulletFields": ["R-100001", "Posting End Date: 08/31/2026"]},
        "job_detail": {"jobPostingInfo": {"title": "Senior Platform Engineer", "jobDescription": "<h2>Build safely</h2><p>Design synthetic banking platforms.</p><ul><li>Improve reliability</li><li>Partner with teams</li></ul>", "location": "Charlotte, NC", "additionalLocations": [], "startDate": "2026-08-01", "timeType": "Full time", "jobReqId": "R-100001", "externalUrl": "https://wd1.myworkdaysite.com/recruiting/wf/WellsFargoJobs/job/Senior-Platform-Engineer_R-100001", "country": {"descriptor": "United States", "alpha2Code": "US"}, "jobRequisitionLocation": {"country": {"alpha2Code": "US"}}}, "hiringOrganization": {"name": "Wells Fargo"}},
    }


def part_time() -> dict:
    payload = standard_us_full_time()
    payload["search_summary"]["title"] = "Branch Support Specialist"
    info = payload["job_detail"]["jobPostingInfo"]
    info.update({"title": "Branch Support Specialist", "jobReqId": "R-100002", "timeType": "Part time", "startDate": "2026-08-02"})
    return payload


def multiple_locations() -> dict:
    payload = standard_us_full_time()
    payload["job_detail"]["jobPostingInfo"].update({"jobReqId": "R-100003", "additionalLocations": ["Minneapolis, MN", "Charlotte, NC", "New York, NY"]})
    return payload


def international() -> dict:
    payload = standard_us_full_time()
    info = payload["job_detail"]["jobPostingInfo"]
    info.update({"jobReqId": "R-100004", "title": "Technology Analyst", "location": "Bengaluru, India", "country": {"descriptor": "India", "alpha2Code": "IN"}, "jobRequisitionLocation": {"country": {"alpha2Code": "IN"}}})
    return payload


def missing_optional() -> dict:
    payload = standard_us_full_time()
    payload["search_summary"].pop("bulletFields")
    info = payload["job_detail"]["jobPostingInfo"]
    info.pop("additionalLocations")
    info.pop("externalUrl")
    info.pop("jobRequisitionLocation")
    return payload


def copy_payload(payload: dict) -> dict:
    return deepcopy(payload)
