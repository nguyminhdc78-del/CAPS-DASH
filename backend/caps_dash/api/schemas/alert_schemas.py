"""Alert response schema.

`message_code` + `details_json` are the real contract: clients localise the
alert text from the code and fill placeholders from the details. `message` is
a plain-English fallback for logs and for a developer hitting the API
directly - never render it in the dashboard UI, or the alert becomes
unlocalisable and unsearchable the moment a non-English client ships.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_type: str
    severity: str
    entity_type: str
    entity_id: str
    message_code: str
    details_json: dict[str, Any]
    message: str
    created_at: dt.datetime
    acknowledged_at: dt.datetime | None
    acknowledged_by_id: int | None
    clock_suspect: bool
