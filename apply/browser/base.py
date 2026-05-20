from abc import ABC, abstractmethod


class BaseATSAdapter(ABC):
    """One subclass per ATS platform (Greenhouse, Lever, Workday, Generic)."""

    @abstractmethod
    async def apply(self, job_url: str, application_id: int) -> bool:
        """Fill and submit an application. Returns True on success. Phase 4 TODO."""
        ...
