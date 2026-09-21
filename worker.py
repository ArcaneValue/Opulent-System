"""Dedicated Railway reminder worker."""
import os
import signal
import threading

import server


def main():
    if not os.environ.get('DATABASE_URL'):
        raise RuntimeError('The hosted worker requires DATABASE_URL.')
    server.init_db()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    print(f'Opulent {server.VERSION} reminder worker started — SMS SIMULATION ONLY', flush=True)
    server.worker_loop(stop)


if __name__ == '__main__':
    main()
