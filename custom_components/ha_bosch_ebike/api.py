"""Bosch eBike API client."""

from __future__ import annotations

import hashlib
import base64
import secrets
import logging
from datetime import datetime, UTC
from typing import Any

import aiohttp

from .const import API_BASE_URL, AUTH_URL, TOKEN_URL, BIKES_ENDPOINT, ACTIVITIES_ENDPOINT, BIKE_PASS_ENDPOINT, SERVICE_RECORDS_ENDPOINT

_LOGGER = logging.getLogger(__name__)


class BoschEBikeAPI:
    """Async client for the Bosch eBike Data Act API."""

    # Single shared timeout for every Bosch cloud request. Without it a hung
    # connection would block the coordinator poll indefinitely.
    _TIMEOUT = aiohttp.ClientTimeout(total=30)

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        access_token: str | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._code_verifier: str | None = None

    # -- PKCE helpers --

    def generate_pkce(self) -> tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge. Returns (verifier, challenge)."""
        verifier = secrets.token_urlsafe(32)
        self._code_verifier = verifier
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return verifier, challenge

    def get_authorize_url(self, redirect_uri: str) -> str:
        """Build the OAuth2 authorization URL with PKCE."""
        _, challenge = self.generate_pkce()
        params = (
            f"?client_id={self._client_id}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&code_challenge={challenge}"
            f"&code_challenge_method=S256"
            f"&scope=openid"
        )
        return f"{AUTH_URL}{params}"

    # -- Token management --

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for tokens (with PKCE)."""
        data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": self._code_verifier,
        }
        async with self._session.post(TOKEN_URL, data=data, timeout=self._TIMEOUT) as resp:
            resp.raise_for_status()
            tokens = await resp.json()
        self._access_token = tokens["access_token"]
        self._refresh_token = tokens.get("refresh_token")
        return tokens

    async def exchange_code_no_pkce(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for tokens (without PKCE)."""
        data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        async with self._session.post(TOKEN_URL, data=data, timeout=self._TIMEOUT) as resp:
            resp.raise_for_status()
            tokens = await resp.json()
        self._access_token = tokens["access_token"]
        self._refresh_token = tokens.get("refresh_token")
        return tokens

    async def refresh_access_token(self) -> dict[str, Any]:
        """Refresh the access token using the refresh token."""
        if not self._refresh_token:
            raise AuthError("No refresh token available")
        data = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "refresh_token": self._refresh_token,
        }
        async with self._session.post(TOKEN_URL, data=data, timeout=self._TIMEOUT) as resp:
            resp.raise_for_status()
            tokens = await resp.json()
        self._access_token = tokens["access_token"]
        if "refresh_token" in tokens:
            self._refresh_token = tokens["refresh_token"]
        return tokens

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    def set_tokens(self, access_token: str, refresh_token: str | None) -> None:
        """Set tokens from stored config entry."""
        self._access_token = access_token
        self._refresh_token = refresh_token

    # -- API calls --

    async def _get(self, base_url: str, path: str, retry_on_401: bool = True) -> Any:
        """GET request with Bearer auth and auto-refresh on 401."""
        if not self._access_token:
            raise AuthError("Not authenticated")
        headers = {"Authorization": f"Bearer {self._access_token}"}
        url = f"{base_url}{path}"
        async with self._session.get(url, headers=headers, timeout=self._TIMEOUT) as resp:
            if resp.status == 401 and retry_on_401:
                _LOGGER.debug("401 received, refreshing token")
                await self.refresh_access_token()
                return await self._get(base_url, path, retry_on_401=False)
            resp.raise_for_status()
            return await resp.json()

    def convert_bikes(self, bikes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        new = []
        for b in bikes:
            batteries = []
            for batt in b['batteries']:
                batteries.append({
                    'deliveredWhOverLifetime': batt['deliveredWhOverLifetime'],
                    'chargeCycles': batt['numberOfFullChargeCycles']
                })
            new.append({
                'id': b['id'],
                'oemId': b['driveUnit']['oemBikeId'],
                'createdAt': b['createdAt'],
                'language': b['remoteControl']['language'],
                'serviceDue': { 
                    'date': b['remoteControl']['serviceDue']['date'],
                    'odometer': b['remoteControl']['serviceDue']['totalDistance']
                },
                'driveUnit': {
                    'productName': b['driveUnit']['productName'],
                    'serialNumber': b['driveUnit']['serialNumber'],
                    'maximumAssistanceSpeed': b['driveUnit']['maxAssistanceSpeed'],
                    'odometer': b['driveUnit']['totalDistanceTraveled'],
                    'powerOnTime': b['driveUnit']['powerOnTime'],
                    'walkAssistConfiguration': {
                        'isEnabled': b['driveUnit']['walkAssist']['isEnabled'],
                        'maximumSpeed': b['driveUnit']['walkAssist']['maximumSpeed']
                    }
                },
                'batteries': batteries
            })
        return new

    async def get_bikes(self) -> list[dict[str, Any]]:
        """Fetch all bike profiles."""
        data = await self._get(API_BASE_PROFILE_URL, BIKES_ENDPOINT)
        return self.convert_bikes(data)

    def convert_summary(self, activity: dict[str, Any]) -> dict[str, Any]:
        attributes = activity.pop("attributes")
        activity.update(attributes)

        new = {}
        new['id'] = activity['id']
        new['bikeId'] = activity['bikeId']
        new['title'] = activity['title']
        new['durationWithoutStops'] = activity['durationWithoutStops']
        new['startOdometer'] = activity['startOdometer']
        new['distance'] = activity['distance']
        
        # convert timestamps
        start_time = datetime.fromtimestamp(activity.get("startTime", 0), UTC)
        end_time = datetime.fromtimestamp(activity.get("endTime", 0), UTC)
        new['startTime'] = start_time.isoformat().replace("+00:00", "Z")
        new['endTime'] = end_time.isoformat().replace("+00:00", "Z")
        new['timeZone'] = activity['timeZoneOfActivity']

        new['speed'] = { 'average': activity['averageSpeed'], 'maximum': activity['maximumSpeed'] }
        new['cadence'] = { 'average': activity['averageCadence'], 'maximum': activity['maximumCadence'] }
        new['riderPower'] = { 'average': activity['averageRiderPower'], 'maximum': activity['maximumRiderPower'] }
        new['elevation'] = { 'gain': activity['elevationGain'], 'loss': activity['elevationLoss'] }
        new['caloriesBurned'] = activity['caloriesBurnt']

        return new

    async def get_latest_activity(self) -> dict[str, Any] | None:
        """Fetch the most recent activity summary."""
        data = await self._get(API_BASE_ACTIVITY_URL, f"{ACTIVITIES_ENDPOINT}?page=0&size=1&sort=-startTime")
        summaries = data.get("data", [])
        return self.convert_summary(summaries[0]) if summaries else None

    async def get_all_activities(self, page_size: int = 50) -> list[dict[str, Any]]:
        """Fetch all activity summaries with pagination."""
        all_activities: list[dict[str, Any]] = []
        page = 0
        offset=0

        while True:
            data = await self._get(API_BASE_ACTIVITY_URL, 
                f"{ACTIVITIES_ENDPOINT}?page={page}&size={page_size}&sort=-startTime"
            )
            summaries = data.get("data", [])
            if not summaries:
                break

            for s in summaries:
                all_activities.append(self.convert_summary(s))
 
            total = data.get("meta", {}).get("total", 0)
            page += 1
            offset += page_size
            _LOGGER.debug(
                "Bosch eBike: Fetched %d/%d activities", len(all_activities), total
            )

            if offset >= total:
                break

        _LOGGER.info("Bosch eBike: Imported %d activities total", len(all_activities))
        return all_activities

    def convert_detail(self, activity: dict[str: Any]) -> dict[str, Any]:
        activity = activity.get("data", {})

        points = []
        for p in activity['attributes']['activityData']:
            points.append({
                'distance': p['s'],
                'altitude': p['h'],
                'speed': p['v'],
                'cadence': p['c'],
                'latitude': p['lat'],
                'longitude': p['lon'],
                'riderPower': p['p']
            })

        return {'activityDetails': points}
    
    async def get_activity_detail(self, activity_id: str) -> dict[str, Any]:
        """Fetch full activity detail including GPS track points."""
        data = await self._get(API_BASE_ACTIVITY_URL, f"{ACTIVITIES_ENDPOINT}/{activity_id}/detail")
        return self.convert_detail(data)

    async def get_bike_pass(self, bike_id: str) -> dict[str, Any]:
        """Bike Pass (frame number + theft report logs) for one bike."""
        return await self._get(f"{BIKE_PASS_ENDPOINT}?bikeId={bike_id}")

    async def get_service_records(self, bike_id: str) -> dict[str, Any]:
        """Digital Service Book records (battery measurements, customer reports) for one bike."""
        return await self._get(f"{SERVICE_RECORDS_ENDPOINT}?bikeId={bike_id}")

    async def get_all_activity_details(
        self, activity_ids: list[str], progress_callback: Any = None
    ) -> list[dict[str, Any]]:
        """Fetch full details for all activities (including GPS)."""
        details: list[dict[str, Any]] = []
        total = len(activity_ids)
        for idx, aid in enumerate(activity_ids):
            try:
                detail = await self.get_activity_detail(aid)
                details.append(detail)
                _LOGGER.debug("Bosch eBike: Fetched detail %d/%d: %s", idx + 1, total, aid)
                if progress_callback:
                    progress_callback(idx + 1, total)
            except Exception as err:
                _LOGGER.warning("Bosch eBike: Failed to fetch activity %s: %s", aid, err)
        _LOGGER.info("Bosch eBike: Fetched %d/%d activity details", len(details), total)
        return details


class AuthError(Exception):
    """Authentication error."""
