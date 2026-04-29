# Database Migration System

## Overview

EchoGTFS uses a custom, minimal migration system written in Python. There is no third-party migration framework. Migrations are plain SQL files that are discovered, version-sorted, and executed once at every application startup. The system is designed so that each migration can be re-executed without causing errors, which is the idempotency guarantee described in detail below.

## Relevant Files

- `backend/src/echogtfs/migrations.py`: Migration runner; reads SQL files, tracks applied versions, executes pending statements.
- `backend/src/echogtfs/migrations/`: Directory of SQL files named `001.sql`, `002.sql`, ..., `NNN.sql`.
- `backend/src/echogtfs/main.py`: Calls `run_migrations(engine)` during the `lifespan` startup context, after `Base.metadata.create_all`.

## Execution Flow

`run_migrations(engine)` is called once at application startup. The full sequence is:

1. Open a single database transaction via `engine.begin()`.
2. Create the `_migrations` tracking table if it does not already exist (`CREATE TABLE IF NOT EXISTS _migrations ...`).
3. Read all version numbers from `_migrations` into a Python set called `applied`.
4. Glob all `*.sql` files from the `migrations/` directory and sort them by their integer stem (`int(p.stem)`).
5. For each migration file in order:
   a. If `version in applied`, log a debug message and skip.
   b. Otherwise, read the file, split it into individual SQL statements, execute each statement, then `INSERT` the version number into `_migrations`.
6. All work happens inside the single transaction opened in step 1. If any statement raises an exception the entire transaction rolls back.

## Version Tracking Table

```sql
CREATE TABLE IF NOT EXISTS _migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

The `version` column is the integer parsed from the file name. It is the primary key, so duplicate inserts are prevented at the database level. The `applied_at` column records when the migration was applied.

## SQL Statement Splitting

asyncpg (the PostgreSQL driver used by the async SQLAlchemy engine) does not support multiple SQL commands in a single `execute` call. The `split_sql_statements(sql_content)` function handles this by:

1. Stripping single-line comments (`--` to end of line) from every line.
2. Iterating character by character and splitting on `;` to produce individual statements.
3. Tracking `$$`-delimited dollar-quote blocks and suppressing semicolon splitting inside them. This is required to support `DO $$ ... END $$;` procedural blocks correctly.
4. Returning a list of non-empty, stripped statement strings.

## Idempotency

Idempotency means that executing a migration more than once produces the same result as executing it once. In the context of this system, idempotency is achieved on two levels: the runner level and the SQL level.

### Runner-Level Idempotency

The version tracking table is the primary guard. Before any migration file is executed, the runner checks whether its version number is already present in `_migrations`. If it is, the file is skipped entirely. Because the version is inserted only after all statements in the file succeed, a migration that failed partway through (and caused a transaction rollback) will not appear in `_migrations` and will be retried on the next startup.

This means: a migration file will be executed at most once on any given database, assuming the database connection is stable.

### SQL-Level Idempotency

The runner-level guard alone is sufficient in normal operation. The SQL-level idempotency patterns used in the migration files exist as a second layer of safety, covering scenarios such as:

- The `_migrations` table being manually cleared or the tracking state being out of sync.
- A developer needing to re-apply a migration in a development database without resetting the tracking table.
- Testing migration files directly with a database client.

Two PostgreSQL SQL patterns are used across the migration files:

#### Pattern 1: `IF NOT EXISTS` / `IF EXISTS` in DDL

Standard PostgreSQL DDL supports conditional variants for many statements:

```sql
CREATE TABLE IF NOT EXISTS data_sources ( ... );
CREATE INDEX IF NOT EXISTS ix_data_sources_name ON data_sources (name);
```

These statements succeed silently when the object already exists, instead of raising an error. They are used in migrations `002.sql`, `007.sql`, `012.sql`, and others whenever a table, index, or constraint is created.

#### Pattern 2: `DO $$ BEGIN ... IF NOT EXISTS ... END $$` Procedural Guards

For DDL operations that do not have a native `IF NOT EXISTS` variant in PostgreSQL (e.g., `ALTER TABLE ADD COLUMN`, `ALTER TABLE ADD CONSTRAINT`, `ALTER TABLE DROP CONSTRAINT`, `ALTER COLUMN TYPE`), the migrations use anonymous `DO` blocks with conditional logic against `information_schema`:

```sql
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='users' AND column_name='is_technical_contact') THEN
        ALTER TABLE users ADD COLUMN is_technical_contact BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;
```

This pattern is used for:

- Adding a column (check `information_schema.columns` for column existence).
- Dropping and re-adding a foreign key constraint (check `information_schema.table_constraints` for constraint name existence).
- Changing a column type (check `information_schema.columns` for the current `data_type`).

#### Concrete Examples from the Migration Files

| File | Operation | Guard Used |
|---|---|---|
| `001.sql` | `ADD COLUMN is_technical_contact` | `DO $$ IF NOT EXISTS (columns WHERE ...) $$` |
| `002.sql` | `CREATE TABLE data_sources` | `CREATE TABLE IF NOT EXISTS` |
| `002.sql` | `CREATE INDEX` (multiple) | `CREATE INDEX IF NOT EXISTS` |
| `003.sql` | `ADD COLUMN last_run_at` | `DO $$ IF NOT EXISTS (columns WHERE ...) $$` |
| `003.sql` | `CREATE INDEX ix_data_sources_last_run_at` | `CREATE INDEX IF NOT EXISTS` |
| `004.sql` | Drop and re-add foreign key with `ON DELETE CASCADE` | `DO $$ IF EXISTS / IF NOT EXISTS (table_constraints WHERE ...) $$` |
| `005.sql` | `ADD COLUMN data_source_id` + foreign key | `DO $$ IF NOT EXISTS (columns / table_constraints WHERE ...) $$` |
| `006.sql` | `ALTER COLUMN start_time TYPE BIGINT` | `DO $$ IF EXISTS (columns WHERE data_type='integer') $$` |
| `007.sql` | `ADD COLUMN is_active` | `DO $$ IF NOT EXISTS (columns WHERE ...) $$` |
| `012.sql` | `CREATE TABLE data_source_logs` | `CREATE TABLE IF NOT EXISTS` |
| `012.sql` | Foreign key on `data_source_logs` | `DO $$ IF NOT EXISTS (table_constraints WHERE ...) $$` |

## Adding a New Migration

1. Create a new file in `backend/src/echogtfs/migrations/` with the next sequential zero-padded name (e.g., `013.sql`).
2. Write the SQL for the schema change.
3. Make every statement idempotent:
   - Use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` for table and index creation.
   - Wrap `ALTER TABLE` operations in a `DO $$ BEGIN IF NOT EXISTS ... END $$;` block, querying `information_schema.columns` or `information_schema.table_constraints` as appropriate.
   - For type changes, guard the `ALTER COLUMN ... TYPE` call by checking the current `data_type` in `information_schema.columns` so the statement is skipped if the column is already the target type.
4. No registration or configuration change is needed; the runner discovers files by glob.

## Constraints and Limitations

- Migrations run inside a single transaction. A failure in any statement of any pending migration rolls back all work for that startup run. The application will fail to start and must be restarted after fixing the issue.
- There is no rollback mechanism. Migrations are forward-only. To undo a migration, write a new migration that reverses the change.
- Migration files must not be renamed or renumbered after they have been applied to any database, because the runner uses the integer file stem as the stable version identifier.
- The system does not support branching or merging of migration histories. Versions must form a single linear sequence.
