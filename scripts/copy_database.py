"""Copy every row from one Ava database to another with the same schema.
Usage: python -m scripts.copy_database SOURCE_URL DESTINATION_URL"""
import sys
from datetime import datetime, timezone
from sqlalchemy import func, insert, select
from backend.app.database import Base, database

SKIP = {'login_sessions'}   # logins are temporary; everyone just signs in again


def main(source_url, destination_url):
    source, _ = database(source_url)
    destination, _ = database(destination_url)
    with source.connect() as src, destination.begin() as dst:   # one transaction: all or nothing
        for table in Base.metadata.sorted_tables:               # parents before children
            if table.name in SKIP:
                continue
            if dst.scalar(select(func.count()).select_from(table)):
                sys.exit(f'{table.name} already has rows in the destination. Nothing was copied.')
            rows = [dict(row._mapping) for row in src.execute(select(table))]
            for row in rows:
                for key, value in row.items():
                    if isinstance(value, datetime) and value.tzinfo is None:
                        row[key] = value.replace(tzinfo=timezone.utc)   # SQLite drops timezones
            if rows:
                dst.execute(insert(table), rows)
            print(f'{table.name}: {len(rows)} rows')
    print('Done. Compare these counts with your source before switching.')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])