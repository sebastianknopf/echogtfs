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


def split_sql_statements(sql_content: str) -> list[str]:
    """
    Split SQL content into individual statements.
    Handles single-line comments (--) and preserves multi-line statements.
    Recognizes DO $$ blocks and keeps them intact (doesn't split on semicolons inside $$...$$ blocks).
    Returns a list of executable SQL statements.
    """
    # Remove single-line comments (-- comments)
    lines = []
    for line in sql_content.split('\n'):
        # Find comment start (if not in a string)
        comment_pos = line.find('--')
        if comment_pos != -1:
            # Simple approach: take everything before --
            line = line[:comment_pos]
        lines.append(line)
    
    # Join back
    cleaned_sql = '\n'.join(lines)
    
    # Split by semicolon, but respect DO $$ blocks
    statements = []
    current_stmt = ""
    in_dollar_quote = False
    i = 0
    
    while i < len(cleaned_sql):
        char = cleaned_sql[i]
        
        # Check for $$ to toggle dollar-quote state
        if i + 1 < len(cleaned_sql) and cleaned_sql[i:i+2] == '$$':
            in_dollar_quote = not in_dollar_quote
            current_stmt += '$$'
            i += 2
            continue
        
        # If we hit a semicolon outside of a dollar-quote block, end the statement
        if char == ';' and not in_dollar_quote:
            stmt = current_stmt.strip()
            if stmt:
                statements.append(stmt)
            current_stmt = ""
        else:
            current_stmt += char
        
        i += 1
    
    # Add any remaining statement
    stmt = current_stmt.strip()
    if stmt:
        statements.append(stmt)
    
    return statements


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
            
            # Split into individual statements (asyncpg doesn't support multiple commands)
            statements = split_sql_statements(sql_content)
            
            # Execute each statement separately
            for stmt in statements:
                await conn.execute(text(stmt))
            
            # Record that this migration has been applied
            await conn.execute(
                text("INSERT INTO _migrations (version) VALUES (:version)"),
                {"version": version}
            )
            
            logger.info(f"Migration {version} applied successfully")
    
    logger.info("All migrations applied")
