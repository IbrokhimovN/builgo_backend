import multiprocessing
import os

bind = "0.0.0.0:8000"

# Formula: (2 * CPUs) + 1
# Gives ~9 workers for a 4 core machine
workers = multiprocessing.cpu_count() * 2 + 1

# Highly asynchronous pseudo-threads handling massive I/O bound operations
worker_class = "gevent"

# Max connections per worker
worker_connections = 1000

# Prevent memory leaks by restarting workers occasionally
max_requests = 10000
max_requests_jitter = 500

# Keep-alives to speed up consecutive network requests
keepalive = 5

# Timeout for long running requests (fails after 30s)
timeout = 30

name = "buildgo_gunicorn"

# Logging configuration
accesslog = "-"
errorlog = "-"
loglevel = "info"
