from typing import Optional
from sqlmodel import Field, SQLModel, Relationship


class Skill(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    category: Optional[str] = None       # 'technical', 'soft', 'domain', 'language'
    proficiency: Optional[str] = None    # 'expert', 'advanced', 'intermediate', 'beginner'
    years_experience: Optional[float] = None
    keywords: Optional[str] = None       # comma-separated ATS variants


class Experience(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    company: str
    title: str
    start_date: str                      # ISO format: 2023-01
    end_date: Optional[str] = None       # NULL = current position
    location: Optional[str] = None
    description: Optional[str] = None
    is_remote: bool = False
    achievements: list["Achievement"] = Relationship(back_populates="experience", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class Achievement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    experience_id: int = Field(foreign_key="experience.id")
    description: str
    metrics: Optional[str] = None
    skills_used: Optional[str] = None    # comma-separated
    experience: Optional[Experience] = Relationship(back_populates="achievements")


class Education(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    institution: str
    degree: str
    field: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None


class Certification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    issuer: Optional[str] = None
    date_obtained: Optional[str] = None
    expiry_date: Optional[str] = None


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    skills_used: Optional[str] = None
    highlights: Optional[str] = None


class Preferences(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)   # enforced single row
    target_roles: Optional[str] = None             # JSON array
    target_locations: Optional[str] = None         # JSON array
    min_salary: Optional[float] = None
    max_salary: Optional[float] = None
    salary_currency: str = "IDR"
    preferred_languages: Optional[str] = None      # JSON array
    industries_include: Optional[str] = None       # JSON array
    industries_exclude: Optional[str] = None       # JSON array
    company_size_preference: Optional[str] = None  # 'startup', 'mid', 'enterprise', 'any'


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str                          # 'linkedin', 'glints', 'jobstreet'
    external_id: Optional[str] = None
    url: str
    title: str
    company: str
    location: Optional[str] = None
    description: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: str = "IDR"
    job_type: Optional[str] = None         # 'full-time', 'contract', 'part-time', 'internship'
    remote_type: Optional[str] = None      # 'remote', 'hybrid', 'onsite'
    experience_level: Optional[str] = None
    posted_date: Optional[str] = None
    scraped_at: str
    raw_html: Optional[str] = None
    compatibility_score: Optional[float] = None
    score_breakdown: Optional[str] = None  # JSON
    status: str = "new"
    applications: list["Application"] = Relationship(back_populates="job", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    activity_logs: list["ActivityLog"] = Relationship(back_populates="job")


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")
    resume_path: Optional[str] = None
    resume_pdf_path: Optional[str] = None
    resume_content: Optional[str] = None   # JSON
    cover_letter: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    apply_method: Optional[str] = None
    recipient_email: Optional[str] = None
    applied_at: Optional[str] = None
    apply_status: str = "pending_review"
    # pending_review → approved → submitting → submitted
    #                → rejected (user skipped)
    #                → applied_manually (user applied via platform URL)
    #                → failed (automation error)
    skip_reason: Optional[str] = None
    error_log: Optional[str] = None
    screenshot_path: Optional[str] = None
    created_at: str
    job: Optional[Job] = Relationship(back_populates="applications")


class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: str
    action: str   # 'scraped', 'scored', 'generated', 'approved', 'submitted', 'failed'
    job_id: Optional[int] = Field(default=None, foreign_key="job.id")
    details: Optional[str] = None
    job: Optional[Job] = Relationship(back_populates="activity_logs")
