from sqlmodel import Session, select
from db.models import (
    Skill, Experience, Achievement,
    Education, Certification, Project, Preferences,
)


# ---- Skills ----

def get_skills(session: Session) -> list[Skill]:
    return list(session.exec(select(Skill).order_by(Skill.name)).all())

def create_skill(session: Session, data: dict) -> Skill:
    skill = Skill(**data)
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill

def update_skill(session: Session, skill_id: int, data: dict) -> Skill:
    skill = session.get(Skill, skill_id)
    for k, v in data.items():
        setattr(skill, k, v)
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill

def delete_skill(session: Session, skill_id: int) -> None:
    skill = session.get(Skill, skill_id)
    if skill:
        session.delete(skill)
        session.commit()


# ---- Experiences ----

def get_experiences(session: Session) -> list[Experience]:
    experiences = list(session.exec(select(Experience).order_by(Experience.start_date.desc())).all())
    for exp in experiences:
        _ = exp.achievements  # eager-load
    return experiences

def create_experience(session: Session, data: dict) -> Experience:
    exp = Experience(**data)
    session.add(exp)
    session.commit()
    session.refresh(exp)
    return exp

def update_experience(session: Session, exp_id: int, data: dict) -> Experience:
    exp = session.get(Experience, exp_id)
    for k, v in data.items():
        setattr(exp, k, v)
    session.add(exp)
    session.commit()
    session.refresh(exp)
    return exp

def delete_experience(session: Session, exp_id: int) -> None:
    exp = session.get(Experience, exp_id)
    if exp:
        session.delete(exp)
        session.commit()


# ---- Achievements ----

def get_achievements(session: Session, experience_id: int) -> list[Achievement]:
    return list(session.exec(select(Achievement).where(Achievement.experience_id == experience_id)).all())

def create_achievement(session: Session, data: dict) -> Achievement:
    achievement = Achievement(**data)
    session.add(achievement)
    session.commit()
    session.refresh(achievement)
    return achievement

def update_achievement(session: Session, achievement_id: int, data: dict) -> Achievement:
    a = session.get(Achievement, achievement_id)
    for k, v in data.items():
        setattr(a, k, v)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a

def delete_achievement(session: Session, achievement_id: int) -> None:
    a = session.get(Achievement, achievement_id)
    if a:
        session.delete(a)
        session.commit()


# ---- Education ----

def get_education_list(session: Session) -> list[Education]:
    return list(session.exec(select(Education).order_by(Education.end_date.desc())).all())

def create_education(session: Session, data: dict) -> Education:
    edu = Education(**data)
    session.add(edu)
    session.commit()
    session.refresh(edu)
    return edu

def update_education(session: Session, edu_id: int, data: dict) -> Education:
    edu = session.get(Education, edu_id)
    for k, v in data.items():
        setattr(edu, k, v)
    session.add(edu)
    session.commit()
    session.refresh(edu)
    return edu

def delete_education(session: Session, edu_id: int) -> None:
    edu = session.get(Education, edu_id)
    if edu:
        session.delete(edu)
        session.commit()


# ---- Certifications ----

def get_certifications(session: Session) -> list[Certification]:
    return list(session.exec(select(Certification).order_by(Certification.date_obtained.desc())).all())

def create_certification(session: Session, data: dict) -> Certification:
    cert = Certification(**data)
    session.add(cert)
    session.commit()
    session.refresh(cert)
    return cert

def update_certification(session: Session, cert_id: int, data: dict) -> Certification:
    cert = session.get(Certification, cert_id)
    for k, v in data.items():
        setattr(cert, k, v)
    session.add(cert)
    session.commit()
    session.refresh(cert)
    return cert

def delete_certification(session: Session, cert_id: int) -> None:
    cert = session.get(Certification, cert_id)
    if cert:
        session.delete(cert)
        session.commit()


# ---- Projects ----

def get_projects(session: Session) -> list[Project]:
    return list(session.exec(select(Project).order_by(Project.name)).all())

def create_project(session: Session, data: dict) -> Project:
    project = Project(**data)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project

def update_project(session: Session, project_id: int, data: dict) -> Project:
    p = session.get(Project, project_id)
    for k, v in data.items():
        setattr(p, k, v)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p

def delete_project(session: Session, project_id: int) -> None:
    p = session.get(Project, project_id)
    if p:
        session.delete(p)
        session.commit()


# ---- Preferences ----

def get_preferences(session: Session) -> Preferences:
    prefs = session.get(Preferences, 1)
    if not prefs:
        prefs = Preferences(id=1)
        session.add(prefs)
        session.commit()
        session.refresh(prefs)
    return prefs

def update_preferences(session: Session, data: dict) -> Preferences:
    prefs = get_preferences(session)
    for k, v in data.items():
        setattr(prefs, k, v)
    session.add(prefs)
    session.commit()
    session.refresh(prefs)
    return prefs
