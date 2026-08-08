#!/bin/sh
# Восстановление БД из дампа: ./scripts/restore.sh backups/daily/tarobot-2026-08-06.dump
set -e
[ -z "$1" ] && { echo "Использование: $0 <файл.dump>"; exit 1; }
docker compose stop bot worker admin
docker compose exec -T db sh -c \
  "pg_restore -U \$POSTGRES_USER -d \$POSTGRES_DB --clean --if-exists" < "$1"
docker compose start bot worker admin
echo "Восстановление завершено"
