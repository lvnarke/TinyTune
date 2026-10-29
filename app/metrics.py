from prometheus_client import Counter, Gauge, Histogram


HTTP_REQUESTS = Counter(
    "tinytune_http_requests_total",
    "HTTP requests received",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "tinytune_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
HTTP_IN_PROGRESS = Gauge(
    "tinytune_http_requests_in_progress",
    "HTTP requests currently in progress",
    ["method"],
)
DB_POOL_TIMEOUTS = Counter(
    "tinytune_db_pool_timeouts_total", "Database pool acquisition timeouts"
)
CACHE_OPERATIONS = Counter(
    "tinytune_cache_operations_total",
    "Playlist cache operations",
    ["result"],
)
PLAY_EVENTS_ENQUEUED = Counter(
    "tinytune_play_events_enqueued_total", "Play events added to Redis Streams"
)
PLAY_EVENTS_SYNC = Counter(
    "tinytune_play_events_sync_total",
    "Play events processed synchronously",
    ["result"],
)
QUEUE_DEPTH = Gauge(
    "tinytune_play_event_queue_depth", "Unacknowledged and queued play events"
)
WORKER_EVENTS = Counter(
    "tinytune_worker_events_total",
    "Play events handled by workers",
    ["result"],
)
WORKER_DURATION = Histogram(
    "tinytune_worker_event_duration_seconds",
    "Worker event processing duration",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
WORKER_BATCH_SIZE = Histogram(
    "tinytune_worker_batch_size",
    "Number of events received in a worker batch",
    buckets=(1, 2, 5, 10, 25, 50, 100),
)

