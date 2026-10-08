import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .config import Settings
from .models import ConsumptionReading, GeoLocation, MeterDetail, MeterSummary, NetworkLocation

logger = logging.getLogger(__name__)


class PortalError(RuntimeError):
    """A failure communicating with the upstream portal."""


class PortalAuthenticationError(PortalError):
    """The configured credentials could not establish an upstream session."""


class UrjaPortalClient:
    """Anti-corruption adapter for the authenticated Urja Meter Ops portal."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.portal_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.portal_timeout_seconds),
            follow_redirects=True,
            headers={"User-Agent": "flock-energy-meter-api/1.0"},
        )
        self._login_lock = asyncio.Lock()
        self._logged_in = False

    async def aclose(self) -> None:
        await self._client.aclose()

    async def login(self, force: bool = False) -> None:
        async with self._login_lock:
            if self._logged_in and not force:
                return
            username = self._settings.portal_username.strip()
            password = self._settings.portal_password.get_secret_value()
            if not username or not password:
                raise PortalAuthenticationError(
                    "Portal credentials are not configured; set PORTAL_USERNAME and PORTAL_PASSWORD"
                )

            try:
                response = await self._client.post(
    "/login",
    data={"email": username, "password": password},
    headers={
        "Accept": "application/json",
        "Origin": self._settings.portal_base_url.rstrip("/"),
        "Referer": f"{self._settings.portal_base_url.rstrip('/')}/login",
        "X-Sveltekit-Action": "true",
    },
)
            except httpx.HTTPError as exc:
                raise PortalError("Unable to reach the Urja portal") from exc

            if response.status_code >= 400:
                raise PortalAuthenticationError("Unable to authenticate with the Urja portal")
            self._logged_in = True
            logger.info("Authenticated with Urja portal")

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        await self.login()
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise PortalError("Unable to reach the Urja portal") from exc

        # A stale cookie can manifest as either an auth status or a redirect to /login.
        if response.status_code in (401, 403) or response.url.path == "/login":
            self._logged_in = False
            await self.login(force=True)
            try:
                response = await self._client.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                raise PortalError("Unable to reach the Urja portal") from exc

        if response.status_code >= 500:
            raise PortalError(f"Urja portal returned HTTP {response.status_code}")
        return response

    async def list_meters(self, query: str | None, page: int) -> tuple[list[MeterSummary], int, int]:
        response = await self._request(
            "GET",
            "/portal/meters/search",
            params={"q": query or "", "page": page},
        )
        if response.status_code != 200:
            raise PortalError(f"Meter search failed with HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise PortalError("Meter search returned invalid JSON") from exc
        return (
            [self._summary(item) for item in payload.get("data", [])],
            int(payload.get("total", 0)),
            int(payload.get("pageSize", 20)),
        )

    async def get_meter(self, meter_id: str) -> MeterDetail:
        # Search first so the detail endpoint cannot make a non-existent meter look valid.
        meters, _, _ = await self.list_meters(meter_id, 1)
        summary = next((meter for meter in meters if meter.meter_id == meter_id), None)
        if summary is None:
            raise KeyError(meter_id)

        response = await self._request("GET", f"/meters/{meter_id}")
        if response.status_code == 404:
            raise KeyError(meter_id)
        if response.status_code != 200:
            raise PortalError(f"Meter detail failed with HTTP {response.status_code}")

        detail = self._parse_detail(response.text, summary)

        geo_response = await self._request("GET", f"/portal/meters/{meter_id}/geo")
        if geo_response.status_code == 404:
            raise KeyError(meter_id)
        if geo_response.status_code == 200:
            try:
                geo = geo_response.json().get("data") or {}
                if geo.get("latitude") is not None and geo.get("longitude") is not None:
                    detail.location = GeoLocation(
                        latitude=float(geo["latitude"]),
                        longitude=float(geo["longitude"]),
                    )
            except (ValueError, TypeError, AttributeError) as exc:
                logger.warning("Ignoring malformed geo response for %s: %s", meter_id, exc)
        return detail

    async def get_consumption(self, meter_id: str) -> list[ConsumptionReading]:
        response = await self._request("GET", f"/portal/meters/{meter_id}/energy")
        if response.status_code == 404:
            raise KeyError(meter_id)
        if response.status_code != 200:
            raise PortalError(f"Consumption lookup failed with HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise PortalError("Consumption lookup returned invalid JSON") from exc

        readings: list[ConsumptionReading] = []
        for item in payload.get("data", []):
            try:
                readings.append(
                    ConsumptionReading(
                        timestamp=datetime.strptime(item["timestamp"], "%d/%m/%Y %H:%M"),
                        energy_kwh=float(item["kwh"]),
                        energy_kvah=float(item["kvah"]),
                        voltage_r=(
                            float(item["voltR"])
                            if item.get("voltR") not in (None, "")
                            else None
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed consumption reading: %s", exc)
        return readings

    async def get_all_meters(self) -> list[MeterSummary]:
        first_page, total, page_size = await self.list_meters(None, 1)
        pages = min(self._settings.portal_max_pages, (total + page_size - 1) // page_size)
        results = [*first_page]
        for page in range(2, pages + 1):
            meters, _, _ = await self.list_meters(None, page)
            results.extend(meters)
        return results

    @staticmethod
    def _summary(item: dict[str, Any]) -> MeterSummary:
        return MeterSummary(
            meter_id=str(item.get("meterId", "")),
            serial_number=item.get("serialNo"),
            make=item.get("make"),
            phase_type=item.get("phaseType"),
            installation_status=item.get("installStatus"),
            transformer_code=item.get("dtCode"),
        )

    @staticmethod
    def _parse_detail(html: str, summary: MeterSummary) -> MeterDetail:
        soup = BeautifulSoup(html, "html.parser")
        values: dict[str, str] = {}
        for term in soup.select("dt"):
            definition = term.find_next_sibling("dd")
            if definition:
                values[term.get_text(" ", strip=True).lower()] = definition.get_text(" ", strip=True)

        # The hierarchy is rendered as breadcrumb text. Parse by stable code prefixes,
        # not by position, because incomplete branches can occur.
        labels = [node.get_text(" ", strip=True) for node in soup.select("main nav span")]
        network = NetworkLocation()
        for label in labels:
            match = re.match(r"(.+?)\s+\(([^)]+)\)$", label)
            if not match:
                continue
            name, code = match.groups()
            value = f"{name} ({code})"
            if code.startswith("Z-"):
                network.zone = value
            elif code.startswith("C-"):
                network.circle = value
            elif code.startswith("D-"):
                network.division = value
            elif code.startswith("SD-"):
                network.subdivision = value
            elif code.startswith("SS-"):
                network.substation = value
            elif code.startswith("F-"):
                network.feeder = value
            elif code.startswith("DT-"):
                network.transformer = value

        return MeterDetail(
            **summary.model_dump(),
            installation_type=values.get("installation type"),
            network=network,
        )
