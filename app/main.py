import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .client import PortalAuthenticationError, PortalError, UrjaPortalClient
from .config import get_settings
from .models import ApiResponse, ConsumptionReading, MeterDetail, MeterSummary, PageMeta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.portal = UrjaPortalClient(settings)
    yield
    await app.state.portal.aclose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A stable read-only REST API that translates the authenticated Urja Meter Ops portal into typed JSON.",
    contact={"name": "Flock Energy engineering"},
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def portal(request: Request) -> UrjaPortalClient:
    return request.app.state.portal


def api_error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request.state.request_id}},
    )


@app.exception_handler(PortalAuthenticationError)
async def auth_error(request: Request, _: PortalAuthenticationError):
    return api_error(request, 503, "UPSTREAM_AUTHENTICATION_FAILED", "The upstream portal could not be authenticated")


@app.exception_handler(PortalError)
async def portal_error(request: Request, _: PortalError):
    return api_error(request, 502, "UPSTREAM_UNAVAILABLE", "The upstream portal did not provide the requested data")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    code = "NOT_FOUND" if exc.status_code == 404 else "INVALID_REQUEST"
    return api_error(request, exc.status_code, code, str(exc.detail))


@app.get("/health", tags=["Operations"])
async def health():
    return {"status": "ok", "service": settings.app_name, "version": settings.app_version}


@app.get("/api/v1/meters", response_model=ApiResponse[list[MeterSummary]], tags=["Meters"])
async def list_meters(
    request: Request,
    q: str | None = Query(None, min_length=1, max_length=100, description="Meter ID or serial number search"),
    page: int = Query(1, ge=1, le=1000),
):
    meters, total, page_size = await portal(request).list_meters(q, page)
    return ApiResponse(
        data=meters,
        meta=PageMeta(page=page, page_size=page_size, total=total, has_next=page * page_size < total),
    )


@app.get("/api/v1/meters/{meter_id}", response_model=ApiResponse[MeterDetail], tags=["Meters"])
async def get_meter(request: Request, meter_id: str = Path(..., pattern=r"^J\d{6}$")):
    try:
        return ApiResponse(data=await portal(request).get_meter(meter_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Meter not found") from None


@app.get("/api/v1/meters/{meter_id}/consumption", response_model=ApiResponse[list[ConsumptionReading]], tags=["Consumption"])
async def get_consumption(request: Request, meter_id: str = Path(..., pattern=r"^J\d{6}$")):
    try:
        return ApiResponse(data=await portal(request).get_consumption(meter_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="Meter not found") from None
