# TimescaleDB with the MedMusketeer init script baked in (no bind mount; the image's own
# 000/001 TimescaleDB init scripts stay in place). Runs once, on an empty data volume.
FROM timescale/timescaledb:2.31.0-pg18
COPY --chmod=0755 init/010-databases.sh /docker-entrypoint-initdb.d/010-databases.sh
