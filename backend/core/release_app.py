"""Compose the legacy and Collection APIs behind the existing /api proxy."""
from contextlib import AsyncExitStack, asynccontextmanager
from starlette.applications import Starlette
from starlette.routing import Mount


class CorePrefix:
    def __init__(self, app, prefix):
        self.app, self.prefix = app, prefix

    async def __call__(self, scope, receive, send):
        path = scope["path"][len(scope.get("root_path", "")):]
        inner = {**scope, "root_path": "", "path": "/api" + path if path == "/v1" or path.startswith("/v1/") else path}
        inner["raw_path"] = inner["path"].encode()

        async def scoped_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [
                    (key, value.replace(b"Path=/api/v1", b"Path=" + self.prefix.encode() + b"/v1") if key.lower() == b"set-cookie" else value)
                    for key, value in message["headers"]
                ]}
            await send(message)

        await self.app(inner, receive, scoped_send)


def make_release_app(legacy, core):
    @asynccontextmanager
    async def lifespan(app):
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(legacy.router.lifespan_context(legacy))
            await stack.enter_async_context(core.router.lifespan_context(core))
            yield

    return Starlette(lifespan=lifespan, routes=[
        Mount("/api/content", app=CorePrefix(core, "/api/content")),
        Mount("/content-api", app=CorePrefix(core, "/content-api")),
        Mount("/", app=legacy),
    ])
