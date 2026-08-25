
CREATE EXTENSION IF NOT EXISTS postgis;

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
);

CREATE INDEX IF NOT EXISTS idx_field_obs_site
    ON field_observations(site_id);

CREATE INDEX IF NOT EXISTS idx_field_obs_project
    ON field_observations(project_id);

CREATE INDEX IF NOT EXISTS idx_field_obs_date
    ON field_observations(observation_date);

CREATE INDEX IF NOT EXISTS idx_field_obs_geom
    ON field_observations USING GIST(geom);

CREATE OR REPLACE VIEW latest_field_observation AS
SELECT DISTINCT ON (site_id)
    *
FROM field_observations
ORDER BY site_id, observation_date DESC, created_at DESC;
