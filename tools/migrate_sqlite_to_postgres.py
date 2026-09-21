"""One-time, all-or-nothing transfer from an Opulent SQLite backup to PostgreSQL."""
import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


TABLES = ('users', 'settings', 'properties', 'units', 'contacts', 'charge_types',
          'plans', 'charges', 'payments', 'allocations', 'messages', 'audit')
IDENTITY_TABLES = ('users', 'properties', 'units', 'contacts', 'charge_types',
                   'plans', 'charges', 'payments', 'messages', 'audit')


def migrate(source_path, database_url):
    os.environ['DATABASE_URL'] = database_url
    import server
    server.DATABASE_URL = database_url
    source_path = Path(source_path).resolve(strict=True)
    with closing(sqlite3.connect(f'{source_path.as_uri()}?mode=ro', uri=True)) as source:
        source.row_factory = sqlite3.Row
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite source failed its integrity check.')
        if source.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite source has invalid linked records.')
        server.init_db()
        with server.connect(True) as target:
            populated = sum(target.execute(f'SELECT COUNT(*) count FROM {name}').fetchone()['count'] for name in ('users','properties','charges','payments'))
            if populated:
                raise ValueError('PostgreSQL destination is not empty. Nothing was imported.')
            # Defaults created by init_db are replaced with the exact source rows.
            target.execute('DELETE FROM charge_types')
            target.execute('DELETE FROM settings')
            for table in TABLES:
                columns = [row['name'] for row in source.execute(f'PRAGMA table_info({table})')]
                records = source.execute(f'SELECT * FROM {table}').fetchall()
                if not records:
                    continue
                placeholders = ','.join('?' for _ in columns)
                target.executemany(f'INSERT INTO {table}({",".join(columns)}) VALUES({placeholders})',
                                   [tuple(record[column] for column in columns) for record in records])
            for table in IDENTITY_TABLES:
                target.execute("SELECT setval(pg_get_serial_sequence(?, 'id'), COALESCE((SELECT MAX(id) FROM " + table + "),1), (SELECT COUNT(*)>0 FROM " + table + "))", (table,))
            target.execute('DELETE FROM sessions')
            target.execute('DELETE FROM previews')
            target.execute('UPDATE settings SET automatic=0')
            target.execute("UPDATE messages SET status='cancelled',updated=? WHERE status='queued'", (server.stamp(),))
            server.audit(target, 'migration', 'sqlite_to_postgresql', {'source': source_path.name})
    print('Migration complete. Sessions cleared and automatic scheduling disabled for review.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('sqlite_backup')
    parser.add_argument('--database-url', default=os.environ.get('DATABASE_URL'))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit('Set DATABASE_URL or pass --database-url. Never commit it.')
    migrate(args.sqlite_backup, args.database_url)
