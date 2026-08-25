from datetime import datetime
import os
from typing import Optional

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://wildlands:wildlands@localhost:5432/wildlands"
)

app = FastAPI(
    title="WILDLANDS Field Monitoring API",
    version="1.0.0"
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


def db():
    return psycopg.connect(DATABASE_URL)


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

                        # Geometry coordinates
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
    """
    Permanently delete one field observation from PostgreSQL.

    The observation_id is the primary identifier returned by
    POST /api/observations and GET /api/observations.
    """
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