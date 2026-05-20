from abc import ABC, abstractmethod
from db.models import Job


class BaseScraper(ABC):
    platform: str

    @abstractmethod
    async def scrape(self, max_pages: int) -> list[Job]:
        """Scrape job listings and return unsaved Job objects."""
        ...
