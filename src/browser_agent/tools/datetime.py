from datetime import datetime, timezone


def get_datetime() -> str:
    """Get the current date, time, and timezone."""
    now = datetime.now(timezone.utc).astimezone()
    return now.strftime("%A, %B %d, %Y at %I:%M %p %Z")
