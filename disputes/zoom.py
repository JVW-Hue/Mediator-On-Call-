"""
Zoom API integration for creating mediation meetings.
Uses JWT authentication (or OAuth for newer Zoom apps).
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def create_zoom_meeting(topic: str, start_time, duration: int = 60):
    """
    Create a scheduled Zoom meeting via the Zoom API.

    Args:
        topic: Meeting topic/name
        start_time: datetime (timezone-aware preferred)
        duration: Meeting duration in minutes

    Returns:
        (join_url, host_url) tuple or (None, None) on failure
    """
    token = getattr(settings, "ZOOM_JWT_TOKEN", None) or getattr(
        settings, "ZOOM_ACCESS_TOKEN", None
    )
    if not token:
        logger.warning("Zoom credentials not configured; skipping meeting creation")
        return None, None

    try:
        import requests
    except ImportError:
        logger.error("requests not installed; cannot create Zoom meeting")
        return None, None

    # Zoom expects ISO format with Z suffix for UTC
    start_iso = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "topic": topic,
        "type": 2,  # scheduled meeting
        "start_time": start_iso,
        "duration": duration,
        "timezone": "UTC",
        "settings": {
            "host_video": True,
            "participant_video": True,
            "join_before_host": False,
            "mute_upon_entry": True,
            "waiting_room": True,
        },
    }

    try:
        response = requests.post(
            "https://api.zoom.us/v2/users/me/meetings",
            headers=headers,
            json=payload,
            timeout=15,
        )
        if response.status_code == 201:
            data = response.json()
            return data.get("join_url"), data.get("start_url")
        logger.error(
            "Zoom API error: %s %s", response.status_code, response.text[:200]
        )
    except Exception as e:
        logger.exception("Zoom meeting creation failed: %s", e)
    return None, None
