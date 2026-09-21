"""Restore a verified backup while the local server is stopped."""
import argparse
import os
import socket
import sqlite3
from contextlib import closing
from pathlib import Path

import server


def restore(path):
    file = Path(path).resolve(strict=True)
    if file == server.DB.resolve():
        raise ValueError('Choose a backup, not the active database.')
    guard = socket.socket()
    try:
        # Reserve the server port throughout restore, avoiding a simultaneous startup.
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            guard.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        guard.bind(('127.0.0.1', int(os.environ.get('OPULENT_PORT','8765'))))
        with closing(sqlite3.connect(f'{file.as_uri()}?mode=ro', uri=True)) as source:
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup failed its integrity check.')
            required={'users','sessions','settings','properties','units','contacts','charges','payments','allocations','messages','previews','audit','plans','charge_types'}
            tables={r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not required <= tables:
                raise ValueError('This is not a compatible Opulent backup.')
            if source.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Backup contains invalid linked records.')
            server.DB.parent.mkdir(exist_ok=True, parents=True)
            if server.DB.exists():
                print('Pre-restore safety backup:',server.save_backup())
            destination=sqlite3.connect(server.DB)
            try:
                source.backup(destination)
                # Restored sessions and pending send jobs must not unexpectedly resume.
                destination.execute('DELETE FROM sessions')
                destination.execute('DELETE FROM previews')
                destination.execute('UPDATE settings SET automatic=0')
                destination.execute("UPDATE messages SET status='cancelled',updated=? WHERE status='queued'",(server.stamp(),))
                server.audit(destination,'maintenance','restore',{'source':file.name})
                destination.commit()
            finally:
                destination.close()
        print('Restore complete. Automatic scheduling is disabled. Start Opulent and sign in.')
    finally:
        guard.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['restore'])
    parser.add_argument('backup')
    args=parser.parse_args()
    try:
        restore(args.backup)
    except Exception as exc:
        print('Restore failed:',str(exc))
        raise SystemExit(1)
