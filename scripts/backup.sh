#!/bin/sh
# Ежедневный бэкап PostgreSQL. Хранение: ежедневные — 7 дней, еженедельные (вс) — 4 недели.
set -e
export PGPASSWORD="$POSTGRES_PASSWORD"
DIR=/backups
STAMP=$(date +%Y-%m-%d)
DOW=$(date +%u)   # 7 = воскресенье

mkdir -p "$DIR/daily" "$DIR/weekly"

pg_dump -h "${POSTGRES_HOST:-db}" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c \
  -f "$DIR/daily/$POSTGRES_DB-$STAMP.dump"

# Проверка целостности: список содержимого дампа
pg_restore --list "$DIR/daily/$POSTGRES_DB-$STAMP.dump" > /dev/null \
  && echo "Backup OK: $STAMP" || { echo "Backup CORRUPT: $STAMP" >&2; exit 1; }

if [ "$DOW" = "7" ]; then
  cp "$DIR/daily/$POSTGRES_DB-$STAMP.dump" "$DIR/weekly/"
fi

# Ротация
find "$DIR/daily"  -name "*.dump" -mtime +7  -delete
find "$DIR/weekly" -name "*.dump" -mtime +28 -delete
