# Data Source Logging

EchoGTFS automatically logs all HTTP requests to external data sources. This logging system helps with debugging, monitoring data quality, and understanding the behavior of external APIs.

## Overview

Every time a data source is executed (either via scheduled cron job or manual trigger), EchoGTFS:
1. Records request metadata (URL, headers, timestamp)
2. Stores the complete response content in a log file
3. Tracks HTTP status codes and response sizes
4. Links each log entry to the corresponding data source

## Viewing Logs

### Accessing Logs via UI

1. Navigate to the **Sources** panel
2. Find the data source you want to inspect
3. Click the **document icon** next to the source
4. A modal window displays the most recent log entries (up to 100)

### Log Table Columns

| Column | Description |
|--------|-------------|
| **Timestamp** | When the request was made (local time) |
| **Endpoint** | The URL that was requested (may include parameters) |
| **Status** | HTTP status code with color indicator |
| **Size** | Response size in bytes, KB, or MB |
| **Actions** | View details or download raw response |

### Status Indicators

Logs use colored badges to indicate request status:
- **Green badge (2xx):** Successful request
- **Red badge (4xx/5xx):** Error occurred (client or server error)

### Error Flags

In the Sources list, each data source shows an **ERROR** badge (red background) if the most recent log entry has a 4xx or 5xx status code. This provides a quick visual indicator of problematic sources.

## Interpreting Log Data

### Response Sizes

The **Size** column shows the **actual (uncompressed) size** of the response content stored on disk:
- For **GTFS-RT sources:** Size reflects the JSON-converted protobuf data
- For **SIRI-SX/SIRI-Lite sources:** Size reflects the raw XML response
- Sizes are automatically decompressed if the server sends compressed data (gzip, deflate)

**Example interpretations:**
- **800 KB to 6 MB:** Typical for comprehensive transit alerts covering a large network
- **< 100 KB:** Small response (few alerts, limited data, or potential issue)
- **0 B:** Empty response or request failure

> **Note:** If you notice significantly smaller sizes than expected (e.g., 800 KB when you expect 6 MB), this may indicate:
> - The server is sending partial data
> - Filters or query parameters are limiting the response
> - A temporary issue with the external API

### HTTP Status Codes

Common status codes and their meanings:

| Code Range | Meaning | Common Causes |
|------------|---------|---------------|
| **200-299** | Success | Request completed successfully |
| **400** | Bad Request | Invalid configuration (check endpoint URL, authentication) |
| **401** | Unauthorized | Missing or invalid authentication token |
| **403** | Forbidden | Valid credentials but insufficient permissions |
| **404** | Not Found | Incorrect endpoint URL or resource doesn't exist |
| **429** | Too Many Requests | Rate limit exceeded (reduce request frequency) |
| **500-599** | Server Error | Problem on the external server (usually temporary) |

### Viewing Detailed Log Content

To inspect the full response:

1. Click the **eye icon** in the log table
2. A detail modal shows:
   - Request headers (including authentication)
   - Response headers
3. Click **Download** to save the raw response content for offline analysis

### Downloaded Log Files

Downloaded log files contain:
- **GTFS-RT:** Pretty-printed JSON representation of the protobuf feed
- **SIRI-SX/SIRI-Lite:** Raw XML response

The filename format is: `log_<DataSourceID>_<Date>_<Time>.json/xml`

## Log Storage and Retention

### Storage Location

Logs are stored in two places:
1. **Database:** Metadata (timestamp, URL, headers, status code, size)
2. **File System:** Complete response content in `/var/log/echogtfs/datasources/` (Docker volume)

Each log file is named with a UUID and can be referenced from the database.

## Execution Tracking

### Last Execution Timestamp

Each data source displays a **Last run** timestamp in the Sources table. This timestamp is updated:
- **On success:** After successfully fetching and processing data
- **On failure:** Even if the request fails or returns an error

This ensures you always know when a data source was last attempted, regardless of outcome.

### Manual Execution

When you manually trigger a data source (via the **Run now** button):
1. The import runs asynchronously in the background
2. A new log entry is created
3. The **Last run** timestamp is updated
4. You can view the new log immediately after execution

## Troubleshooting with Logs

### Problem: No alerts are imported from a source

**Steps:**
1. Check the **Last run** timestamp – is it recent?
2. View the most recent log entry
3. Check the **Status** code:
   - **200:** Data was received, check response size
   - **4xx/5xx:** Fix authentication or endpoint configuration
4. Download the log file and inspect the response content
5. Verify that the response contains actual alert data

### Problem: Source shows ERROR badge

**Steps:**
1. Click the **Logs** button
2. Look at the most recent entry's status code
3. Common fixes:
   - **401/403:** Update authentication token in source configuration
   - **404:** Verify endpoint URL is correct
   - **500/502/503:** Wait and retry (external server issue)
   - **429:** Reduce cron frequency or add delays

### Problem: Alerts are missing or incomplete

**Steps:**
1. View logs and check response size
2. Download the log file
3. Inspect the raw data:
   - Are all expected alerts present in the response?
   - Are GTFS entity IDs correctly mapped?
   - Check for invalid reference handling policy

### Problem: Response size seems wrong

**Steps:**
1. Download the log file to verify actual content size
2. Compare with response headers (if available via detail view)
3. Check if the external API applies filters or pagination
4. Verify that query parameters in the endpoint URL are correct