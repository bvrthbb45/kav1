"""In-memory log of sync events (Hebrew), shown in the control panel."""

import logging
import threading
import time
from collections import deque
from typing import Deque, Dict, List

log = logging.getLogger(__name__)

MAX_EVENTS = 500

INFO = "info"
SUCCESS = "success"
WARNING = "warning"
ERROR = "error"

_LOG_LEVELS = {
    INFO: logging.INFO,
    SUCCESS: logging.INFO,
    WARNING: logging.WARNING,
    ERROR: logging.ERROR,
}

_lock = threading.Lock()
_events: Deque[Dict] = deque(maxlen=MAX_EVENTS)
_next_id = 1


def add(level: str, message: str, source: str = "server") -> None:
    """Record an event for the panel and mirror it to the server log."""
    global _next_id
    with _lock:
        _events.append(
            {
                "id": _next_id,
                "time": time.time(),
                "level": level,
                "source": source,
                "message": message,
            }
        )
        _next_id += 1
    log.log(_LOG_LEVELS.get(level, logging.INFO), "[%s] %s", source, message)


def since(after_id: int = 0) -> List[Dict]:
    with _lock:
        return [e for e in _events if e["id"] > after_id]
