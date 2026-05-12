'''FastAPI application factory with CORS and optional HTTPS enforcement middleware.'''
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import Response, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from .routers.files import router as files_router
from .routers.auth import router as auth_router
from .routers.generate_prompts import router as generate_prompts_router
from .routers.run_prompt import router as run_prompt_router
from .routers.documents import router as documents_router, _engine as _doc_engine, Base as _DocumentBase
from .middleware.rate_limit import RateLimitMiddleware
from .config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with _doc_engine.begin() as conn:
        await conn.run_sync(_DocumentBase.metadata.create_all)
    yield


app = FastAPI(title="File Management API", lifespan=lifespan)
settings = Settings()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic validation errors to a 400 Bad Request response.
    FastAPI defaults to 422, but the specification requires 400 with error details.
    """
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.errors()},
    )

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Optional HTTPS enforcement: only enforce in production mode if env var PRODUCTION=True
    if getattr(settings, "production", False):
        if request.url.scheme != "https":
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": "HTTPS required"})
    # CORS handling
    origin = request.headers.get("origin")
    if origin and origin not in settings.allowed_origins:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Origin not allowed"})
    # Handle preflight requests
    if request.method == "OPTIONS":
        response = JSONResponse(content={})
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    response: Response = await call_next(request)
    # Add CORS headers to normal responses
    if origin and origin in settings.allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

app.add_middleware(RateLimitMiddleware)
app.include_router(files_router)
app.include_router(auth_router)
app.include_router(generate_prompts_router)
app.include_router(run_prompt_router)
app.include_router(documents_router)
