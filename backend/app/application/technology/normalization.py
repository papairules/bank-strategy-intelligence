from backend.app.application.technology.models import TechnologyCategory


_ALIASES = {
    "amazon web services": "AWS",
    "aws": "AWS",
    "excel": "Excel",
    "google cloud platform": "Google Cloud",
    "gcp": "Google Cloud",
    "hadoop": "Hadoop",
    "kubernetes": "Kubernetes",
    "microsoft azure": "Microsoft Azure",
    "ms excel": "Excel",
    "microsoft excel": "Excel",
    "oracle": "Oracle",
    "power bi": "Power BI",
    "powerbi": "Power BI",
    "python": "Python",
    "sas": "SAS",
    "sql": "SQL",
    "tableau": "Tableau",
    "teradata": "Teradata",
    "vba": "VBA",
}

_CATEGORIES = {
    "AWS": TechnologyCategory.CLOUD_PLATFORM,
    "Excel": TechnologyCategory.ANALYTICS_STATISTICAL_TOOL,
    "Google Cloud": TechnologyCategory.CLOUD_PLATFORM,
    "Hadoop": TechnologyCategory.DATA_PLATFORM,
    "Kubernetes": TechnologyCategory.DEVOPS_INFRASTRUCTURE,
    "Microsoft Azure": TechnologyCategory.CLOUD_PLATFORM,
    "Oracle": TechnologyCategory.DATABASE,
    "Power BI": TechnologyCategory.BI_VISUALIZATION,
    "Python": TechnologyCategory.PROGRAMMING_LANGUAGE,
    "SAS": TechnologyCategory.ANALYTICS_STATISTICAL_TOOL,
    "SQL": TechnologyCategory.DATABASE,
    "Tableau": TechnologyCategory.BI_VISUALIZATION,
    "Teradata": TechnologyCategory.DATA_PLATFORM,
    "VBA": TechnologyCategory.PROGRAMMING_LANGUAGE,
}


def normalize_technology(value: str) -> str:
    compact = " ".join(value.strip().split())
    return _ALIASES.get(compact.casefold(), compact)


def categorize_technology(value: str) -> TechnologyCategory:
    return _CATEGORIES.get(value, TechnologyCategory.OTHER)
