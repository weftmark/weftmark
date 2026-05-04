#!/bin/sh
set -e

echo "Running Alembic migrations..."

# Run upgrade. If the DB is stuck at a legacy (pre-squash) revision that no
# longer exists in the migration graph, Alembic will error with "Can't locate
# revision". In that case, stamp the new baseline (--purge clears the version
# table and inserts e5f6a7b8c9d0) and retry — the retry will be a no-op since
# the schema is already fully up-to-date.
set +e
alembic upgrade head > /tmp/alembic_out.txt 2>&1
ALEMBIC_EXIT=$?
set -e
cat /tmp/alembic_out.txt

if [ $ALEMBIC_EXIT -ne 0 ]; then
    if grep -q "Can't locate revision" /tmp/alembic_out.txt; then
        echo "Legacy revision detected — stamping new baseline e5f6a7b8c9d0"
        alembic stamp e5f6a7b8c9d0 --purge
        alembic upgrade head
        echo "Migrations complete."
    else
        echo "WARNING: Alembic migrations failed — starting server to surface diagnostics via /health/ready."
    fi
else
    echo "Migrations complete."
fi

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
