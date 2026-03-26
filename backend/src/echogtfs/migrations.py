"""
Simple database migration system.

Migrations are SQL files stored in the migrations/ directory.
Each migration has a unique integer version number as its filename (e.g., 001.sql).
A database table tracks which migrations have been applied.
"""
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations(engine: AsyncEngine) -> None:
    """
    Execute all pending database migrations in sequential order.
    Creates a _migrations table to track applied migrations.
    """
    async with engine.begin() as conn:
        # Ensure the migrations tracking table exists
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS _migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Get list of applied migrations
        result = await conn.execute(text("SELECT version FROM _migrations ORDER BY version"))
        applied = {row[0] for row in result.fetchall()}

        # Find all migration files
        if not MIGRATIONS_DIR.exists():
            logger.info("No migrations directory found, skipping migrations")
            return

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: int(p.stem))
        
        for migration_file in migration_files:
            version = int(migration_file.stem)
            
            if version in applied:
                logger.debug(f"Migration {version} already applied, skipping")
                continue
            
            logger.info(f"Applying migration {version}: {migration_file.name}")
            
            # Read and execute the migration SQL
            sql_content = migration_file.read_text(encoding="utf-8")
            await conn.execute(text(sql_content))
            
            # Record that this migration has been applied
            await conn.execute(
                text("INSERT INTO _migrations (version) VALUES (:version)"),
                {"version": version}
            )
            
            logger.info(f"Migration {version} applied successfully")
    
    logger.info("All migrations applied")
