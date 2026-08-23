"""Deterministic, zero-cost technology extraction from free-text job postings.

Matches a curated list of unambiguous technology/product names against posting
text (title + description). This is intentionally conservative: single-letter
or common-English-word technology names (e.g. "R", "Go", "C") are excluded to
avoid false positives, since there is no LLM step to verify matches here.
"""
import re

# Technology names that collide with common English words (e.g. "excel", "spark",
# "chef" as verbs/nouns) are matched case-sensitively against their proper-noun
# capitalization instead of being excluded outright or matched loosely.
CASE_SENSITIVE_TECHNOLOGIES: dict[str, list[str]] = {
    "Excel": ["Excel"],
    "Spark": ["Spark"],
    "Chef": ["Chef"],
}

TECHNOLOGY_ALIASES: dict[str, list[str]] = {
    "Python": ["python"],
    "Java": ["java"],
    "JavaScript": ["javascript"],
    "TypeScript": ["typescript"],
    "C++": ["c++"],
    "C#": ["c#"],
    ".NET": [".net", "dotnet"],
    "Golang": ["golang"],
    "Scala": ["scala"],
    "Kotlin": ["kotlin"],
    "Ruby": ["ruby"],
    "PHP": ["php"],
    "Perl": ["perl"],
    "COBOL": ["cobol"],
    "Mainframe": ["mainframe", "z/os"],
    "PL/SQL": ["pl/sql", "plsql"],
    "SQL": ["sql"],
    "NoSQL": ["nosql"],
    "VBA": ["vba"],
    "Node.js": ["node.js", "nodejs", "node js"],
    "React": ["react.js", "reactjs", "react"],
    "Angular": ["angular.js", "angularjs", "angular"],
    "Vue.js": ["vue.js", "vuejs", "vue"],
    "Spring": ["spring boot", "spring framework", "spring mvc", "spring batch"],
    "Hibernate": ["hibernate"],
    "Microservices": ["microservices", "micro services"],
    "REST": ["restful api", "rest api", "rest apis"],
    "GraphQL": ["graphql"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "Google Cloud Platform": ["gcp", "google cloud platform", "google cloud"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Docker": ["docker"],
    "OpenShift": ["openshift"],
    "Terraform": ["terraform"],
    "CloudFormation": ["cloudformation"],
    "Ansible": ["ansible"],
    "Puppet": ["puppet"],
    "Jenkins": ["jenkins"],
    "CI/CD": ["ci/cd", "continuous integration", "continuous deployment"],
    "Git": ["git", "github", "gitlab", "bitbucket"],
    "JIRA": ["jira"],
    "Confluence": ["confluence"],
    "ServiceNow": ["servicenow"],
    "Splunk": ["splunk"],
    "SonarQube": ["sonarqube"],
    "JUnit": ["junit"],
    "Selenium": ["selenium"],
    "Maven": ["maven"],
    "Gradle": ["gradle"],
    "Linux": ["linux"],
    "Unix": ["unix"],
    "Windows Server": ["windows server"],
    "VMware": ["vmware"],
    "Citrix": ["citrix"],
    "Active Directory": ["active directory"],
    "Okta": ["okta"],
    "CyberArk": ["cyberark"],
    "Palo Alto Networks": ["palo alto networks", "palo alto firewall"],
    "CrowdStrike": ["crowdstrike"],
    "QRadar": ["qradar"],
    "Oracle": ["oracle database", "oracle db", "oracle"],
    "MySQL": ["mysql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MongoDB": ["mongodb", "mongo db"],
    "DB2": ["db2"],
    "Redis": ["redis"],
    "Cassandra": ["cassandra"],
    "Elasticsearch": ["elasticsearch", "elastic search"],
    "Kafka": ["kafka", "apache kafka"],
    "RabbitMQ": ["rabbitmq"],
    "Hadoop": ["hadoop"],
    "Apache Spark": ["apache spark", "pyspark", "spark sql"],
    "Airflow": ["airflow", "apache airflow"],
    "Snowflake": ["snowflake"],
    "Databricks": ["databricks"],
    "dbt": ["dbt"],
    "Informatica": ["informatica"],
    "Talend": ["talend"],
    "Tableau": ["tableau"],
    "Power BI": ["power bi", "powerbi"],
    "Alteryx": ["alteryx"],
    "SAS": ["sas programming", "sas software", "sas macros"],
    "TensorFlow": ["tensorflow"],
    "PyTorch": ["pytorch"],
    "SAP": ["sap"],
    "Salesforce": ["salesforce"],
    "Bloomberg Terminal": ["bloomberg terminal", "bloomberg professional"],
    "Murex": ["murex"],
    "Calypso": ["calypso"],
    "Summit": ["summit fintegration", "summit fnp"],
    "Aladdin": ["aladdin platform", "blackrock aladdin"],
    "FIS": ["fis global", "fis profile"],
    "Temenos": ["temenos"],
    "Finastra": ["finastra"],
    "Avaloq": ["avaloq"],
}


def _build_pattern(surface_forms: list[str], *, case_sensitive: bool) -> re.Pattern[str]:
    escaped = sorted((re.escape(form) for form in surface_forms), key=len, reverse=True)
    body = "|".join(escaped)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", flags)


_PATTERNS: dict[str, re.Pattern[str]] = {
    **{
        name: _build_pattern(forms, case_sensitive=False)
        for name, forms in TECHNOLOGY_ALIASES.items()
    },
    **{
        name: _build_pattern(forms, case_sensitive=True)
        for name, forms in CASE_SENSITIVE_TECHNOLOGIES.items()
    },
}


def extract_technologies(*texts: str | None) -> list[str]:
    """Return canonical technology names whose surface forms appear in any of `texts`."""
    combined = " ".join(text for text in texts if text)
    if not combined:
        return []
    return sorted(name for name, pattern in _PATTERNS.items() if pattern.search(combined))


EXCERPT_WINDOW_CHARS = 60


def find_technology_excerpt(canonical_name: str, *texts: str | None) -> str | None:
    """Return a short window of text around the first match for `canonical_name`,
    for use as a human-checkable evidence excerpt. None if the technology is
    not registered or does not match any of the supplied texts."""
    pattern = _PATTERNS.get(canonical_name)
    if pattern is None:
        return None
    for text in texts:
        if not text:
            continue
        match = pattern.search(text)
        if match is None:
            continue
        start = max(0, match.start() - EXCERPT_WINDOW_CHARS)
        end = min(len(text), match.end() + EXCERPT_WINDOW_CHARS)
        return text[start:end].strip()
    return None
