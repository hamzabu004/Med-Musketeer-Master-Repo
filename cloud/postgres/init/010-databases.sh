#!/bin/sh
# Runs once, on an empty data volume, after the TimescaleDB image's own init scripts.
# Creates one database for ZITADEL and one for MedMusketeer, each with its own roles:
#   zitadel      owns the zitadel database
#   mm_migrator  owns the medmusketeer database and runs the migrations
#   mm_api       the API's runtime login; table privileges are granted by the migrations
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -v zitadel_pw="$ZITADEL_DB_PASSWORD" \
    -v migrator_pw="$MM_MIGRATOR_PASSWORD" \
    -v api_pw="$MM_API_PASSWORD" <<'EOSQL'
CREATE ROLE zitadel LOGIN PASSWORD :'zitadel_pw';
CREATE DATABASE zitadel OWNER zitadel;
REVOKE ALL ON DATABASE zitadel FROM PUBLIC;

CREATE ROLE mm_migrator LOGIN PASSWORD :'migrator_pw';
CREATE ROLE mm_api LOGIN PASSWORD :'api_pw';
CREATE DATABASE medmusketeer OWNER mm_migrator;
REVOKE ALL ON DATABASE medmusketeer FROM PUBLIC;
GRANT CONNECT ON DATABASE medmusketeer TO mm_api;

\connect medmusketeer
CREATE EXTENSION IF NOT EXISTS timescaledb;
EOSQL
