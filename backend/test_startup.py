"""Quick startup test for the API."""

import sys

try:
    from app.main import app
    from app.config import settings

    print("✓ FastAPI app imported successfully")
    print(f"✓ App title: {app.title}")
    print(f"✓ App version: {app.version}")
    print(f"✓ Database URL (configured): {settings.database_url}")
    print(f"✓ Database URL (resolved): {settings.resolved_database_url}")
    if settings.sqlite_database_path is not None:
        print(f"✓ SQLite file: {settings.sqlite_database_path}")
    print(f"✓ CORS origins: {settings.cors_origins_list}")

    # Check routers
    routes = [route.path for route in app.routes]
    print(f"✓ Registered routes: {len(routes)}")

    expected_routes = [
        "/health",
        "/api/v1/oss/sts-token",
        "/api/v1/decks/tree",
        "/api/v1/study/submissions",
        "/api/v1/dashboard",
        "/api/v1/settings",
    ]

    for route in expected_routes:
        if route in routes:
            print(f"  ✓ {route}")
        else:
            print(f"  ✗ {route} MISSING")
            sys.exit(1)

    print("\n✅ All startup checks passed!")

except Exception as e:
    print(f"\n❌ Startup failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
