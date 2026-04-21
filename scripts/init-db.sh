#!/bin/bash
# Runs on first PostgreSQL container startup via docker-entrypoint-initdb.d.
# Creates the Authentik database and user alongside the application database.
# The application database itself is created by the POSTGRES_DB env var.

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER ${AUTHENTIK_POSTGRESQL__USER} WITH PASSWORD '${AUTHENTIK_POSTGRESQL__PASSWORD}';
    CREATE DATABASE ${AUTHENTIK_POSTGRESQL__NAME} OWNER ${AUTHENTIK_POSTGRESQL__USER};
    GRANT ALL PRIVILEGES ON DATABASE ${AUTHENTIK_POSTGRESQL__NAME} TO ${AUTHENTIK_POSTGRESQL__USER};
EOSQL
