# PostgreSQL 16 + PostGIS 3.6 + pgvector (CLAUDE.md stack).
FROM postgis/postgis:16-3.6

RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16-pgvector \
 && rm -rf /var/lib/apt/lists/*
