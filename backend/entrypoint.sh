#!/bin/sh
set -e

echo "Running Alembic migrations..."

# Run upgrade. If the DB is stuck at a legacy (pre-squash) revision that no
# longer exists in the migration graph, Alembic will error with "Can't locate
# revision". In that case, stamp the new baseline (--purge clears the version
# table and inserts 0001_squash_902, the full squash through 0048_yarn_dye_lot)
# and retry — the retry will be a no-op since the schema is already up-to-date.
set +e
alembic upgrade head > /tmp/alembic_out.txt 2>&1
ALEMBIC_EXIT=$?
set -e
cat /tmp/alembic_out.txt

if [ $ALEMBIC_EXIT -ne 0 ]; then
    if grep -q "Can't locate revision" /tmp/alembic_out.txt; then
        echo "Legacy revision detected — stamping new baseline 0001_squash_902"
        alembic stamp 0001_squash_902 --purge
        alembic upgrade head
        echo "Migrations complete."
    else
        echo "WARNING: Alembic migrations failed — starting server to surface diagnostics via /health/ready."
    fi
else
    echo "Migrations complete."
fi

# Record migration timestamp in alembic_meta (best-effort; table may not exist on old DBs)
python -c "
import sys
sys.path.insert(0, '/app')
try:
    from app.config import get_settings
    import sqlalchemy as sa
    url = get_settings().database_url_sync
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(sa.text(
            \"INSERT INTO alembic_meta (key, value) VALUES ('last_migrated_at', now()::text) \"
            \"ON CONFLICT (key) DO UPDATE SET value = now()::text\"
        ))
    engine.dispose()
except Exception as e:
    print(f'Warning: alembic_meta update skipped: {e}', file=sys.stderr)
" || true

echo "Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
