"""A minimal client for the AirTrail API."""

import asyncio
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 15


class AirTrailError(Exception):
    """Base exception for AirTrail API errors."""


class AirTrailConnectionError(AirTrailError):
    """Raised when the AirTrail instance cannot be reached."""


class AirTrailAuthError(AirTrailError):
    """Raised when the API key is invalid or lacks permissions."""


class AirTrailClient:
    """Client for an AirTrail instance's API."""

    def __init__(self, session: aiohttp.ClientSession, url: str, api_key: str) -> None:
        self._session = session
        self._base_url = url.rstrip("/")
        self._api_key = api_key

    async def _get(self, path: str) -> dict[str, Any] | None:
        """Perform a GET request, returning None if the endpoint does not exist."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.get(
                    f"{self._base_url}/api{path}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AirTrailConnectionError(str(err)) from err

        async with response:
            if response.status in (401, 403):
                raise AirTrailAuthError(f"Unauthorized ({response.status})")
            if response.status == 404:
                return None
            if response.status >= 400:
                raise AirTrailError(f"Unexpected response ({response.status})")
            try:
                return await response.json()
            except (aiohttp.ContentTypeError, ValueError) as err:
                raise AirTrailError("Invalid response from AirTrail") from err

    async def flights(self) -> list[dict[str, Any]]:
        """Return all flights belonging to the API key's user."""
        data = await self._get("/flight/list")
        if data is None:
            raise AirTrailError("The flight list endpoint is not available")
        return data.get("flights", [])

    async def stats(self) -> dict[str, Any] | None:
        """Return aggregated statistics, or None on versions without the endpoint."""
        data = await self._get("/stats")
        return data.get("stats") if data else None
