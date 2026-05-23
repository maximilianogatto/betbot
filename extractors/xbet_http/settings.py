"""Runtime settings for the 1xBet/SpinBetter HTTP extractor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class XBetHttpSettings:
    """Configuration for defensive LineFeed polling."""

    base_url: str = "https://spinbetter.com/service-api/LineFeed"
    language: str = "es"
    sport_id: str = "1"
    discovery_country_group: str = "14"
    timeout_seconds: float = 20.0
    max_attempts: int = 2
    retry_backoff_seconds: float = 0.75
    min_request_interval_seconds: float = 0.35

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive.")
        if self.retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative.")
        if self.min_request_interval_seconds < 0:
            raise ValueError("min_request_interval_seconds must not be negative.")
