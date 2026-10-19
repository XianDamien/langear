"""Paired release entry point: both APIs share a SHA; processing runs separately."""
from app.main import app as legacy
from core.main import app as core
from core.release_app import make_release_app

app = make_release_app(legacy, core)
