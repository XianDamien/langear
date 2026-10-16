from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from core.config import get_settings


@lru_cache
def get_engine():
    return create_engine(
        get_settings().database_url, pool_pre_ping=True, hide_parameters=True
    )


def get_db():
    with Session(get_engine(), expire_on_commit=False) as db:
        with db.begin():
            yield db
