"""Collection-wide settings, Dashboard and My Courses surfaces."""

from typing import Annotated

from fastapi import APIRouter, Depends

from core import auth
from core.content import ContentService
from core.courses import my_courses
from core.dashboard import dashboard_data
from core.db import get_db
from core.models import Collection
from core.settings_service import SettingsUpdate, save_settings, settings_data

router = APIRouter(prefix="/api/v1")
Identity = Annotated[Collection, Depends(auth.identity)]


def service(collection: Identity, db=Depends(get_db, scope="function")):
    return ContentService(db, collection)


@router.get("/settings")
def read_settings(content=Depends(service)):
    return settings_data(content.collection)


@router.put("/settings")
def write_settings(body: SettingsUpdate, content=Depends(service)):
    return save_settings(content, body)


@router.get("/dashboard")
def read_dashboard(collection: Identity, db=Depends(get_db, scope="function")):
    return dashboard_data(db, collection)


@router.get("/my-courses")
def read_my_courses(collection: Identity, db=Depends(get_db, scope="function")):
    return my_courses(db, collection)
