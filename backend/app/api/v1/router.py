"""
v1 API router — aggregates all feature sub-routers.

Mounted at /api/v1 in app/main.py.
"""

from fastapi import APIRouter

from app.api.v1 import admin, analyze, graph, patches, plan, report, smells, validate

router = APIRouter()

# Analysis and job management.
router.include_router(analyze.router, prefix="/analyze", tags=["analysis"])

# Universal Code Graph.
router.include_router(graph.router, prefix="/graph", tags=["graph"])

# Smell detection results.
router.include_router(smells.router, prefix="/smells", tags=["smells"])

# Refactor plan management.
router.include_router(plan.router, prefix="/plan", tags=["plan"])

# Code patches.
router.include_router(patches.router, prefix="/patches", tags=["patches"])

# Validation results.
router.include_router(validate.router, prefix="/validate", tags=["validation"])

# Modernization reports.
router.include_router(report.router, prefix="/report", tags=["report"])

# Admin: health, metrics, API key management.
router.include_router(admin.router, prefix="/admin", tags=["admin"])
