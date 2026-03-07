# app.models — SQLAlchemy ORM models
# All models are imported here so Alembic autogenerate detects them and
# so that relationship() references resolve correctly at import time.

from app.models.api_key import APIKey
from app.models.app_setting import AppSetting
from app.models.job import Job, Report
from app.models.job_log import JobLog
from app.models.patch import Patch, ValidationResult
from app.models.plan import Plan, PlanTask
from app.models.smell import Smell
from app.models.ucg import Embedding, UCGEdge, UCGNode
from app.models.vcs import VCSProvider

__all__ = [
    "APIKey",
    "AppSetting",
    "Embedding",
    "Job",
    "JobLog",
    "Patch",
    "Plan",
    "PlanTask",
    "Report",
    "Smell",
    "UCGEdge",
    "UCGNode",
    "ValidationResult",
    "VCSProvider",
]
