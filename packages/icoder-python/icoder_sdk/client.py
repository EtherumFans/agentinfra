"""iCoDer HTTP client with automatic token refresh."""

from typing import Optional, Callable
import httpx
from .types import iCoDerConfig, TokenResponse


class iCoDerClient:
    """Low-level HTTP client for iCoDer API."""

    def __init__(self, config: iCoDerConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.http = httpx.Client(
            base_url=self.base_url,
            timeout=config.timeout,
            headers={"Authorization": f"Bearer {config.access_token}"} if config.access_token else {},
        )
        self._on_token_refresh: Optional[Callable] = None

    def on_token_refresh(self, callback: Callable[[str, str], None]):
        """Register callback for token refresh events."""
        self._on_token_refresh = callback

    def _refresh_token(self) -> bool:
        """Attempt to refresh the access token. Returns True if successful."""
        if not self.config.refresh_token:
            return False
        try:
            resp = httpx.post(
                f"{self.base_url}/api/auth/refresh",
                json={"refresh_token": self.config.refresh_token},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.config.access_token = data["access_token"]
                self.config.refresh_token = data.get("refresh_token", self.config.refresh_token)
                self.http.headers["Authorization"] = f"Bearer {self.config.access_token}"
                if self._on_token_refresh:
                    self._on_token_refresh(self.config.access_token, self.config.refresh_token)
                return True
        except Exception:
            pass
        return False

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make an HTTP request with automatic token refresh on 401."""
        resp = self.http.request(method, path, **kwargs)
        if resp.status_code == 401 and self._refresh_token():
            resp = self.http.request(method, path, **kwargs)
        return resp

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)

    def close(self):
        self.http.close()
