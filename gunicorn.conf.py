import os

bind = '0.0.0.0:' + os.environ.get('PORT','8080')
workers = 1  # SQLite + in-process scheduler: one process and one replica only.
threads = 4
worker_class = 'gthread'
timeout = 45
graceful_timeout = 30
accesslog = '-'
errorlog = '-'
preload_app = False
