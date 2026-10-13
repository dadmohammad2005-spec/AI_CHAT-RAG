#!/bin/bash
set -e

echo "==> Checking database connection..."
python << 'EOF'
import os
import sys
import time
import psycopg

db_host = os.environ.get("DB_HOST", "localhost")
db_port = os.environ.get("DB_PORT", "5432")
db_name = os.environ.get("DB_NAME", "ai_rag_db")
db_user = os.environ.get("DB_USER", "rag_admin")
db_password = os.environ.get("DB_PASSWORD", "rag_secure_password")

max_retries = 30
retry_interval = 2

for i in range(max_retries):
    try:
        conn = psycopg.connect(
            host=db_host,
            port=db_port,
            dbname=db_name,
            user=db_user,
            password=db_password,
            connect_timeout=3
        )
        conn.close()
        print("==> Database is ready!")
        sys.exit(0)
    except Exception as e:
        print(f"Waiting for database ({i+1}/{max_retries})... {e}")
        time.sleep(retry_interval)

print("==> Database connection failed. Exiting.")
sys.exit(1)
EOF

# For web service container: run migrations and collectstatic
if [ "$1" = "gunicorn" ] || [ "$1" = "python" ]; then
    echo "==> Running database migrations..."
    python manage.py migrate --noinput

    echo "==> Initializing demo data if needed..."
    python manage.py setup_demo_data || true
fi

exec "$@"
