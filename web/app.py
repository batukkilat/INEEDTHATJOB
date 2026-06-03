from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from web.routes import dashboard, jobs, applications, profile, settings as settings_route, api, guide


def create_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="INEEDTHATJOB", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="web/static"), name="static")

    app.include_router(dashboard.router)
    app.include_router(guide.router, prefix="/guide")
    app.include_router(jobs.router, prefix="/jobs")
    app.include_router(applications.router)
    app.include_router(profile.router, prefix="/profile")
    app.include_router(settings_route.router, prefix="/settings")
    app.include_router(api.router, prefix="/api")

    return app
