from __future__ import annotations

from .database import Database
from .repositories import AppRepository
from .services import ApplicationServices


class ApplicationContext:
    """Contenedor explícito de dependencias de la aplicación."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.repository = AppRepository(database)
        self.services = ApplicationServices(self.repository)
