from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM (Groq)
    groq_api_key: str = ""
    scoring_model: str = "llama-3.1-8b-instant"
    generation_model: str = "llama-3.3-70b-versatile"

    # Scraping
    scrape_platforms: str = '["linkedin", "glints", "jobstreet"]'
    scrape_max_pages: int = 5
    linkedin_session_cookie: str = ""
    glints_session_cookie: str = ""
    jobstreet_session_cookie: str = ""

    # Application
    apply_delay_min_seconds: int = 60
    apply_delay_max_seconds: int = 120

    # Email (SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_email: str = ""
    from_name: str = ""

    # Scheduling
    schedule_enabled: bool = False
    schedule_cron: str = "0 9 * * 1-5"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Storage paths
    db_path: str = "./data/ineedthatjob.db"
    output_dir: str = "./data/output"
    screenshot_dir: str = "./data/screenshots"
    log_dir: str = "./data/logs"

    def ensure_dirs(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        for d in [self.output_dir, self.screenshot_dir, self.log_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)


settings = Settings()
