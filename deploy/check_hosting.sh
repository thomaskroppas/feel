#!/bin/sh
# Проверка хостинга перед развёртыванием (ТЗ: «Первым делом проверить на хостинге»).
# Запуск по SSH: sh deploy/check_hosting.sh
echo "== Python =="
for p in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  command -v "$p" >/dev/null 2>&1 && echo "$p: $($p --version 2>&1)"
done

PY=${PYTHON:-python3}
echo
echo "== Пакет cryptography (нужен pywebpush) =="
TMP=$(mktemp -d)
"$PY" -m venv "$TMP/venv" && "$TMP/venv/bin/pip" install -q cryptography >/dev/null 2>&1 \
  && "$TMP/venv/bin/python" -c "import cryptography; print('ok, версия', cryptography.__version__)" \
  || echo "НЕ УСТАНАВЛИВАЕТСЯ — нужен другой Python или колёса под эту систему"
rm -rf "$TMP"

echo
echo "== SQLite =="
"$PY" -c "import sqlite3; print('версия', sqlite3.sqlite_version)"

echo
echo "== Диск =="
df -h "$HOME" 2>/dev/null | tail -1
quota -s 2>/dev/null || echo "(quota недоступна — лимит смотрите в панели reg.ru)"

echo
echo "== Cron =="
command -v crontab >/dev/null && echo "crontab есть; минимальный интервал смотрите в панели (нужно раз в 5 минут)" || echo "crontab не найден — настраивать через панель"
