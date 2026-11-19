# Threads and Processes

This document lists the threads, worker processes, and asyncio tasks that the backend starts itself, the names they carry, and how they behave in a production system. Names are visible in debuggers, thread dumps, and `ps`.

## Worker Threads

Blocking work is moved off the event loop with `create_named_thread()`. It behaves like `asyncio.to_thread` but renames the executing thread for the duration of the call and restores the previous name afterwards. The threads belong to the default asyncio executor, so they are reused and carry their original name (`asyncio_N`) while idle.

| Thread Name | Purpose |
| --- | --- |
| `datasource-cpu-bound` | CPU-bound parsing and transformation work inside a datasource. |
| `realtime-processing` | Synchronous helper calls of the realtime processing services. |
| `datalog-dump-writer` | Writing datasource payload dump files. |
| `alembic-migration` | Running Alembic migrations at startup. |
| `trip-matching` | Intermediate stop comparison in the matching service. |
| `datasource-pool-shutdown` | Waiting for the process pool to shut down. |

## Asyncio Tasks

Background tasks started by routers run on the event loop, not in their own thread. They are named for task introspection.

| Task Name | Purpose |
| --- | --- |
| `source-import-<id>` | Manual import of one data source with progress stream. |
| `source-toggle-<id>` | Activation toggle of one data source with progress stream. |
| `gtfs-import` | Manual GTFS static import with progress stream. |

## Datasource Process Pool

Datasource runs execute in a `ProcessPoolExecutor` that uses the `spawn` start method. The maximum size is configured by `DATASOURCE_PROCESS_POOL_SIZE` (see [datasources.md](datasources.md)).

Parent process:

| Thread Name | Purpose |
| --- | --- |
| `datasource-pool-manager` | Executor management thread that dispatches jobs and collects results. |
| `datasource-pool-feeder` | Queue feeder thread that sends job data to the workers. |

Both threads are created lazily on the first submitted job and are renamed right after submission. The renaming uses CPython internals and is skipped silently if they are not available.

Worker processes:

- The process name and its main thread are `datasource-worker-N`.
- Workers are started on demand up to the configured maximum. Idle workers are reused.
- A worker that is idle blocks while waiting for the next job and runs no application code. Its main thread runs the datasource import only while a job is active.
- Each job opens its own database and cache connections and closes them when the job ends.

## Behavior in Production

- `ps` shows the worker processes by their original command line (`python -c "from multiprocessing.spawn import spawn_main ..."`). The process name `datasource-worker-N` is set inside Python and is not reflected in the command line. Thread names are visible with `ps -T` or `top -H`, depending on the platform.
- Because of the `spawn` start method, Python also starts one `multiprocessing.resource_tracker` process. It is idle for the lifetime of the application and is not a datasource worker. With a pool size of 2, up to three child processes are therefore expected.
- A worker PID changes when the pool is recreated (application restart or reload, scheduler close) or when a worker crashes and is replaced.
- The threads of the web server (event loop) and the AnyIO worker threads used by FastAPI for synchronous dependencies are not created by application code and keep their library names.
- Debuggers such as debugpy label child processes as `Subprocess <pid>`.
