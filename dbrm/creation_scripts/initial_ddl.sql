-- Initial DDL with tables.

CREATE TABLE IF NOT EXISTS sites_probes (
  time               TIMESTAMP WITH TIME ZONE NOT NULL,
  site               VARCHAR(200) NOT NULL,
  resource           VARCHAR(200) NOT NULL,
  method             VARCHAR(5) NOT NULL,
  url                TEXT NOT NULL,
  resp_http_code     NUMERIC(3),
  resp_time_ms       NUMERIC(8,3),
  expected_http_code NUMERIC(3),
  error_desc         TEXT,
  ok                 BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS site_status (
  site               VARCHAR(200) NOT NULL,
  last_update        TIMESTAMP NOT NULL,
  status             BOOLEAN NOT NULL,
  n_resources        NUMERIC(5) NOT NULL,
  err_counter        NUMERIC(10) NOT NULL,
  CONSTRAINT site_key PRIMARY KEY(site)
);

SELECT create_hypertable(
  'sites_probes', 'time',
  chunk_time_interval => interval '1 day'
);
