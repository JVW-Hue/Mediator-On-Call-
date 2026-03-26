import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 2
worker_class = "sync"
timeout = 300
keepalive = 5

max_requests = 1000
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = "info"

preload_app = True
