from abc import ABC, abstractmethod
from db.models import Application, Job


def _parse_cookie_string(cookie_str: str) -> list[tuple[str, str]]:
    """Parse 'name=value; name2=value2' into (name, value) pairs."""
    pairs = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, val = part.partition("=")
            pairs.append((name.strip(), val.strip()))
    return pairs


class BaseATSAdapter(ABC):
    @abstractmethod
    async def apply(self, job: Job, app: Application) -> bool:
        """Navigate to job URL, fill and submit application. Returns True on success."""
        ...
