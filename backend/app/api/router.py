"""Aggregates module routers under /api/v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.modules.archive.router import router as archive_router
from app.modules.astrology.router import router as astrology_router
from app.modules.consent.attestation import router as attestation_router
from app.modules.consent.claim_invites import router as claim_invites_router
from app.modules.consent.router import router as consent_router
from app.modules.documents.router import files_router as document_files_router
from app.modules.documents.router import router as documents_router
from app.modules.evidence.router import router as evidence_router
from app.modules.extraction.router import router as extraction_router
from app.modules.family.router import router as family_router
from app.modules.gedcom.router import router as gedcom_router
from app.modules.genealogy.router import router as genealogy_router
from app.modules.heritage.router import router as heritage_router
from app.modules.identity.router import router as auth_router
from app.modules.lifeevents.router import router as lifeevents_router
from app.modules.merge.router import router as merge_router
from app.modules.notifications.router import router as reminders_router
from app.modules.notifications.router import user_router as notifications_user_router
from app.modules.property.router import router as property_router
from app.modules.public.router import router as public_router
from app.modules.render.router import files_router as render_files_router
from app.modules.render.router import router as render_router
from app.modules.search.router import router as search_router
from app.modules.trees.router import router as trees_router
from app.modules.visualization.router import router as visualization_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(trees_router)
api_router.include_router(genealogy_router)
api_router.include_router(lifeevents_router)
api_router.include_router(reminders_router)
api_router.include_router(notifications_user_router)
api_router.include_router(visualization_router)
api_router.include_router(render_router)
api_router.include_router(render_files_router)
api_router.include_router(public_router)
api_router.include_router(evidence_router)
api_router.include_router(heritage_router)
api_router.include_router(family_router)
api_router.include_router(search_router)
api_router.include_router(consent_router)
api_router.include_router(attestation_router)
api_router.include_router(claim_invites_router)
api_router.include_router(merge_router)
api_router.include_router(property_router)
api_router.include_router(documents_router)
api_router.include_router(document_files_router)
api_router.include_router(extraction_router)
api_router.include_router(astrology_router)
api_router.include_router(gedcom_router)
api_router.include_router(archive_router)
