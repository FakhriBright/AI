from time import monotonic
from fastapi import HTTPException, Request, status


class SimpleRateLimiter:
    """Lightweight in-memory rate limiter per IP address for sensitive endpoints."""

    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.interval = 60.0
        self._records: dict[str, list[float]] = {}

    def check(self, request: Request, custom_limit: int | None = None) -> None:
        limit = custom_limit or self.requests_per_minute
        ip = request.client.host if (request.client and request.client.host) else "127.0.0.1"
        now = monotonic()

        if ip not in self._records:
            self._records[ip] = []

        cutoff = now - self.interval
        timestamps = [t for t in self._records[ip] if t > cutoff]
        self._records[ip] = timestamps

        if len(timestamps) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {limit} requests per minute allowed.",
            )

        self._records[ip].append(now)


rate_limiter = SimpleRateLimiter(requests_per_minute=30)
