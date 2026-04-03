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

## GTFS Static Configuration
- After logging in as an admin, navigate to the **Settings** section.
- Here you can configure GTFS feed sources and adjust system-wide options.
- The GTFS feed source configured here is the GTFS static feed which used for referencing manually created alerts as well as matching external alerts.
- The GTFS static feed is imported periodically according to the cron expression. If no cron expression is set, the import is only done manually.
