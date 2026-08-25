
# WILDLANDS Field Monitoring API

This is the first real backend/data layer for the conservation monitoring system.

## Architecture

Field team
→ `field_monitoring.html`
→ FastAPI
→ PostgreSQL/PostGIS
→ main GIS dashboard

## 1. Start the database + API

Install Docker Desktop, then from this folder:

```bash
docker compose up --build
```

API:
`http://localhost:8000`

Health check:
`http://localhost:8000/health`

Interactive API docs:
`http://localhost:8000/docs`

## 2. What is stored

Each field observation contains:

- project/site ID
- observation type
- observer
- date
- GPS point
- notes
- structured observation payload

The payload can contain IAP, restoration, biodiversity, or site-condition fields.

## 3. Why PostGIS

The GPS position is stored as a real PostGIS geometry:

`POINT(longitude latitude)` in EPSG:4326.

That means later we can perform spatial queries such as:

- observations inside a restoration area
- observations within a distance of a site
- IAP observations near roads/rivers
- biodiversity observations by project
- field observations intersecting satellite-analysis polygons

## 4. Important

The HTML currently used in the project is still a frontend prototype. The next frontend change should replace its local save/export behaviour with a POST request to:

`POST /api/observations`

Do not delete `field_data.json` yet; it remains a useful export/backup during the transition.
