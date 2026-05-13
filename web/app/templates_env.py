from datetime import datetime, timezone
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def _timestamp_to_date(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d/%m/%Y")


templates.env.filters["timestamp_to_date"] = _timestamp_to_date
