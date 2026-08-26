import os
from contextlib import asynccontextmanager
from typing import Optional

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://wildlands:wildlands@localhost:5432/wildlands"
)


def db():
    return psycopg.connect(DATABASE_URL)


def init_db():
    """Create the WILDLANDS database schema if it does not exist."""

    with db() as conn:
        with conn.cursor() as cur:

            # Enable PostGIS
            cur.execute(
                "CREATE EXTENSION IF NOT EXISTS postgis"
            )

            # Main observations table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS field_observations (
                    observation_id BIGSERIAL PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    site_id TEXT NOT NULL,
                    project_name TEXT,
                    record_type TEXT NOT NULL,
                    observer TEXT NOT NULL,
                    observation_date DATE NOT NULL,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION,
                    notes TEXT,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    geom GEOMETRY(Point, 4326),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            # Indexes
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_field_obs_site
                ON field_observations(site_id)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_field_obs_project
                ON field_observations(project_id)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_field_obs_date
                ON field_observations(observation_date)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_field_obs_geom
                ON field_observations USING GIST(geom)
                """
            )

            # Latest observation per site
            cur.execute(
                """
                CREATE OR REPLACE VIEW latest_field_observation AS
                SELECT DISTINCT ON (site_id)
                    *
                FROM field_observations
                ORDER BY site_id, observation_date DESC, created_at DESC
                """
            )

        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run database initialization when the API starts
    init_db()
    yield


app = FastAPI(
    title="WILDLANDS Field Monitoring API",
    version="1.0.0",
    lifespan=lifespan
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Observation(BaseModel):
    project_id: str
    site_id: str
    project_name: Optional[str] = None
    record_type: str
    observer: str
    observation_date: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None
    payload: dict = Field(default_factory=dict)


@app.get("/health")
def health():
    try:
        with db() as conn:
            conn.execute("SELECT 1")

        return {
            "status": "ok",
            "database": "connected"
        }

    except Exception as exc:
        return {
            "status": "error",
            "database": "unavailable",
            "detail": str(exc)
        }


@app.post("/api/observations")
def create_observation(obs: Observation):
    try:
        with db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    INSERT INTO field_observations
                    (
                        project_id,
                        site_id,
                        project_name,
                        record_type,
                        observer,
                        observation_date,
                        latitude,
                        longitude,
                        notes,
                        payload,
                        geom
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        CASE
                            WHEN %s::double precision IS NOT NULL
                                 AND %s::double precision IS NOT NULL
                            THEN ST_SetSRID(
                                ST_MakePoint(
                                    %s::double precision,
                                    %s::double precision
                                ),
                                4326
                            )
                            ELSE NULL
                        END
                    )
                    RETURNING observation_id, created_at
                    """,
                    (
                        obs.project_id,
                        obs.site_id,
                        obs.project_name,
                        obs.record_type,
                        obs.observer,
                        obs.observation_date,
                        obs.latitude,
                        obs.longitude,
                        obs.notes,
                        psycopg.types.json.Jsonb(obs.payload),

                        # Geometry
                        obs.longitude,
                        obs.latitude,
                        obs.longitude,
                        obs.latitude,
                    )
                )

                row = cur.fetchone()

            conn.commit()

        return {
            "status": "saved",
            "observation_id": row[0],
            "created_at": row[1].isoformat()
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get("/api/observations")
def list_observations(site_id: Optional[str] = None):
    try:
        with db() as conn:
            with conn.cursor() as cur:

                if site_id:
                    cur.execute(
                        """
                        SELECT
                            observation_id,
                            project_id,
                            site_id,
                            project_name,
                            record_type,
                            observer,
                            observation_date,
                            latitude,
                            longitude,
                            notes,
                            payload,
                            created_at
                        FROM field_observations
                        WHERE site_id = %s
                        ORDER BY observation_date DESC, created_at DESC
                        """,
                        (site_id,)
                    )

                else:
                    cur.execute(
                        """
                        SELECT
                            observation_id,
                            project_id,
                            site_id,
                            project_name,
                            record_type,
                            observer,
                            observation_date,
                            latitude,
                            longitude,
                            notes,
                            payload,
                            created_at
                        FROM field_observations
                        ORDER BY observation_date DESC, created_at DESC
                        """
                    )

                rows = cur.fetchall()

        columns = [
            "observation_id",
            "project_id",
            "site_id",
            "project_name",
            "record_type",
            "observer",
            "observation_date",
            "latitude",
            "longitude",
            "notes",
            "payload",
            "created_at"
        ]

        return [
            dict(zip(columns, row))
            for row in rows
        ]

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.delete("/api/observations/{observation_id}")
def delete_observation(observation_id: int):
    try:
        with db() as conn:
            with conn.cursor() as cur:

                cur.execute(
                    """
                    SELECT observation_id
                    FROM field_observations
                    WHERE observation_id = %s
                    """,
                    (observation_id,)
                )

                row = cur.fetchone()

                if row is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Observation not found"
                    )

                cur.execute(
                    """
                    DELETE FROM field_observations
                    WHERE observation_id = %s
                    RETURNING observation_id
                    """,
                    (observation_id,)
                )

                deleted_id = cur.fetchone()[0]

            conn.commit()

        return {
            "status": "deleted",
            "observation_id": deleted_id
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )