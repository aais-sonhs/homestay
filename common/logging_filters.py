"""Logging filters shared by the web and worker processes."""

import logging


class SuppressNotFoundFilter(logging.Filter):
    """Hide common probe 404s while preserving application 404 records."""

    NOISY_PATHS = {
        "/favicon.ico",
        "/favicon.png",
        "/robots.txt",
        "/config.js",
        "/config.json",
        "/api/config",
        "/api/env",
    }
    NOISY_PREFIXES = ("/.env",)

    def filter(self, record):
        if getattr(record, "status_code", None) != 404:
            return True
        try:
            message = record.getMessage()
        except Exception:
            return True
        marker = "Not Found: "
        if marker not in message:
            return True
        path = message.split(marker, 1)[1].strip().split("?", 1)[0]
        return path not in self.NOISY_PATHS and not any(
            path.startswith(prefix) for prefix in self.NOISY_PREFIXES
        )

