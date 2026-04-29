# Configuration

EchoGTFS offers flexible configuration options to adapt the system to your environment and requirements. Configuration can be managed via environment variables, the web interface, and adapter-specific settings.

## Environment Variables
- Core settings such as database credentials, secret keys, and frontend port are managed in the `.env` file.
- See the project README for a full list of environment variables and their descriptions.

## System Configuration
- After logging in as an admin, navigate to the **Settings** section.
- You can define the app title, as well as the appearance settings (primary and secondary color).

## GTFS Realtime Configuration
- After logging in as an admin, navigate to the **Settings** section.
- Define a GTFS-RT endpoint URL for accessing the GTFS-RT service alerts feed. This URL is always appended to `https://[YourDomain]/api/`.
- Optionally you can define a basic auth username and password for protecting the GTFS-RT stream. To change a given password, enter a new password. To disable basic auth, simply remove the username.

### Output Formats
The GTFS-RT endpoint supports different output formats via query parameters:
- **Default (no parameter):** Returns the feed in GTFS-RT Protobuf format (binary, `application/x-protobuf`)
- **`?json`:** Returns the feed as JSON for debugging and inspection
- **`?debug`:** Alternative parameter for JSON output, functionally identical to `?json`

Example:
- `https://[YourDomain]/api/gtfs-rt` → Protobuf (for production use)
- `https://[YourDomain]/api/gtfs-rt?json` → JSON (for debugging)
- `https://[YourDomain]/api/gtfs-rt?debug` → JSON (for debugging) 

## Data Cleanup Configuration
- After logging in as an admin, navigate to the **Settings** section.
- EchoGTFS includes an automated cleanup service for managing expired internal alerts.
- **Important:** Data cleanup only affects internal alerts (created within EchoGTFS). External alerts from data sources are always synchronized from their respective sources and are never affected by the cleanup process.

### Cleanup Schedule
- Define a **cron expression** to control when the cleanup job runs.
- Default: `*/10 * * * *` (every 10 minutes)
- The cleanup job automatically starts on system startup and is rescheduled whenever settings are updated.

### Expired Alert Policy
Configure how the system handles internal alerts whose last validity period has expired:
- **Deactivate (default):** Sets `is_active=false` for expired alerts. The alerts remain in the database but are no longer published in the GTFS-RT feed.
- **Delete:** Permanently removes expired alerts from the database.

### Permanent Deletion
Configure when expired internal alerts should be permanently deleted from the database:
- **Never (default):** Alerts are never automatically deleted (only deactivated if configured).
- **After 1 day:** Alerts are deleted if they expired at least 1 day ago.
- **After 7 days:** Alerts are deleted if they expired at least 7 days ago.
- **After 30 days:** Alerts are deleted if they expired at least 30 days ago.

**Note:** Only the calendar date is considered for deletion, not the exact time. For example, if an alert expires on April 7 at 5:00 PM and "After 1 day" is configured, it will be deleted on April 8 during the first cleanup run (regardless of time).

### Data Source Log Cleanup
- **Automatic:** Data source request logs (HTTP request/response data from external data sources) are automatically deleted after **24 hours**.
- This cleanup runs independently of the alert cleanup settings and cannot be disabled.
- Both database entries and log files stored on disk are removed during cleanup.
- This ensures that the system does not accumulate excessive log data over time while retaining recent logs for debugging purposes.

## GTFS Static Configuration
- After logging in as an admin, navigate to the **Settings** section.
- Here you can configure GTFS feed sources and adjust system-wide options.
- The GTFS feed source configured here is the GTFS static feed which used for referencing manually created alerts as well as matching external alerts.
- The GTFS static feed is imported periodically according to the cron expression. If no cron expression is set, the import is only done manually.
