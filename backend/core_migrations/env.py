"""Explicit clean-schema migration job; CORE_DATABASE_URL must be isolated."""

from alembic import context
from sqlalchemy import create_engine, pool, text
from core.config import get_settings
from core.models import Base


def run():
    url = get_settings().database_url
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SELECT pg_advisory_xact_lock(3000280030)"))
            context.configure(
                connection=connection, target_metadata=Base.metadata, compare_type=True
            )
            context.run_migrations()
    engine.dispose()


run()
