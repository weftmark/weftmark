#!/bin/bash
# Runs on first PostgreSQL container startup via docker-entrypoint-initdb.d.
# The application database is created automatically by the POSTGRES_DB env var.
set -e
