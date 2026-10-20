"""Core-only release entry point. Start with uvicorn core.core_only:app."""

from core.main import app as core
from core.release_app import make_core_app

app = make_core_app(core)
