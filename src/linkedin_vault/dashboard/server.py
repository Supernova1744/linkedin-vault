import uvicorn

from linkedin_vault.config import Settings


def run_dashboard(settings: Settings) -> None:
    uvicorn.run(
        "linkedin_vault.dashboard.app:app",
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        reload=False,
        log_level="warning",
    )
