--  'date --date='30 day ago' +%y-%m-%d

SELECT drop_chunks(
  'sites_probes',
  'YYYY-DD-MM'::timestamp
);
