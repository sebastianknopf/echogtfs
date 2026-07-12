import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from echogtfs.config import settings

logger = logging.getLogger(__name__)


class AlembicMigrationService:

    def __init__(self) -> None:
        backend_dir = Path(__file__).resolve().parents[4]

        self._alembic_ini = backend_dir / "alembic.ini"
        self._script_location = backend_dir / "alembic"

    def _build_config(self) -> Config:
        config = Config(str(self._alembic_ini))
        config.set_main_option("script_location", str(self._script_location))
        config.set_main_option("sqlalchemy.url", settings.database_url)
        
        return config

    def _upgrade_head_sync(self) -> None:
        logger.info("Running Alembic migrations to head")
        
        try:
            command.upgrade(self._build_config(), "head")
        except Exception:
            logger.exception("Alembic migration failed during startup")
            raise

        logger.info("Alembic migrations complete")

    async def upgrade_head(self) -> None:
        await asyncio.to_thread(self._upgrade_head_sync)