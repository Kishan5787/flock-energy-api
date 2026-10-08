import asyncio

import httpx

from app.client import UrjaPortalClient
from app.config import Settings


def test_consumption_parser_skips_bad_rows():
    async def fake_request(method: str, path: str, **kwargs):
        return httpx.Response(
            200,
            json={
                "data": [
                    {"timestamp": "23/07/2026 10:00", "kwh": "1.25", "kvah": "1.31", "voltR": "231.4"},
                    {"timestamp": "23/07/2026 10:30", "kwh": "bad", "kvah": "1.32", "voltR": "232"},
                ]
            },
            request=httpx.Request(method, "https://example.test"),
        )

    async def run():
        client = UrjaPortalClient(Settings(portal_username="operator@urja.local", portal_password="secret"))
        client._request = fake_request
        try:
            rows = await client.get_consumption("J100000")
            assert len(rows) == 1
            assert rows[0].energy_kwh == 1.25
            assert rows[0].voltage_r == 231.4
            assert rows[0].timestamp.isoformat() == "2026-07-23T10:00:00"
        finally:
            await client.aclose()

    asyncio.run(run())
