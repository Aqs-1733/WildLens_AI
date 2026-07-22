from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class SpeciesNetError(RuntimeError):
    """Base class for degradable SpeciesNet client failures."""


class SpeciesNetDisabled(SpeciesNetError):
    """SpeciesNet integration is disabled by configuration."""


class SpeciesNetUnavailable(SpeciesNetError):
    """The local SpeciesNet API is unreachable."""


class SpeciesNetTimeout(SpeciesNetError):
    """The local SpeciesNet API exceeded its timeout budget."""


class SpeciesNetHTTPError(SpeciesNetError):
    """The local SpeciesNet API returned a non-successful HTTP status."""


class SpeciesNetJSONError(SpeciesNetError):
    """The local SpeciesNet API returned invalid JSON or schema."""


class SpeciesNetClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.speciesnet_enabled)

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            timeout=float(self.settings.speciesnet_timeout_seconds),
            connect=float(self.settings.speciesnet_connect_timeout_seconds),
            read=float(self.settings.speciesnet_read_timeout_seconds),
            write=float(self.settings.speciesnet_write_timeout_seconds),
            pool=float(self.settings.speciesnet_pool_timeout_seconds),
        )

    async def health(self) -> dict[str, Any]:
        if not self.enabled:
            raise SpeciesNetDisabled("SpeciesNet is disabled")
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                response = await client.get(f"{self.settings.speciesnet_api_url.rstrip('/')}/health")
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise SpeciesNetTimeout(str(exc)) from exc
        except httpx.ConnectError as exc:
            raise SpeciesNetUnavailable(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise SpeciesNetHTTPError(f"HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except ValueError as exc:
            raise SpeciesNetJSONError(str(exc)) from exc
        if not isinstance(data, dict):
            raise SpeciesNetJSONError("Health response is not an object")
        return data

    async def predict_image_bytes(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.jpg",
        mime_type: str = "image/jpeg",
        country: str = "",
        top_k: int = 5,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        files = {"file": (filename, image_bytes, mime_type)}
        data = {"top_k": str(top_k)}
        if country.strip():
            data["country"] = country.strip().upper()
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                response = await client.post(
                    f"{self.settings.speciesnet_api_url.rstrip('/')}/predict/upload",
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise SpeciesNetTimeout(str(exc)) from exc
        except httpx.ConnectError as exc:
            raise SpeciesNetUnavailable(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise SpeciesNetHTTPError(f"HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except ValueError as exc:
            raise SpeciesNetJSONError(str(exc)) from exc

        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise SpeciesNetJSONError("Prediction response is not a successful object")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise SpeciesNetJSONError("Prediction response has no result object")
        return payload

    async def safe_predict_image_bytes(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.jpg",
        mime_type: str = "image/jpeg",
        country: str = "",
        top_k: int = 5,
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            return (
                await self.predict_image_bytes(
                    image_bytes,
                    filename=filename,
                    mime_type=mime_type,
                    country=country,
                    top_k=top_k,
                ),
                None,
            )
        except SpeciesNetError as exc:
            message = str(exc) or exc.__class__.__name__
            logger.warning("SpeciesNet branch degraded: %s", message)
            return None, message


speciesnet_client = SpeciesNetClient()
