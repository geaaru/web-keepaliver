# web-keepaliver

Web Services monitoring system that generates metrics to Kafka's Brokers.

It supplies two different programs that are configurable through YAML files:

 * **web-keepaliver-producer**: the service that runs HTTP/HTTPS probes
   to check site status and latency. After the creation of these metrics,
   it sends messages to Kafka Broker (in JSON format) to configured topics.

  * **web-keepaliver-consumer**: the service fetches the messages from Kafka
    Brokers, parses the messages, and stores in a TimescaleDB. The timescaleDB
    is an extension of the PostgreSQL database.

The stored data are read and displayed from a Grafana dashboard

## Developers stuff

The database schema is initialized through the
[database-release-manager](http://geaaru.github.io/database-release-manager/)
that at the moment has a limited number of
functions on PostgreSQL. We use it to automize the setup of the target database
and in the near future to trace and compiles indexes.

Hereinafter, some examples about using the target database after that is been
configured the `dbrm/dbrm-profiles/dev.conf` file with right access data
```shell
$> cd dbrm/
$> # Access to database shell
$> dbrm psql shell
$> # Show schema tables.
$> dbrm psql show --tables
$> # Compile the SQL file
$> dbrm psql compile --file script.sql
```

The tool `dbrm` permits to manage SSH tunnelling to reach database over SSH channel.
```shell
$> dbrm ssl
===========================================================================
Module [ssl]:
---------------------------------------------------------------------------
	long_help               Show long help informations
	show_help               Show command list.
	version                 Show module version.
	create                  Add a new entry to tunnel master data inside
	                        dbrm database.
	enable                  Active an existing tunnel.
	disable                 Disable an active tunnel.
	list                    Show list of tunnels.
	init                    Initialize SSL extension.
	deinit                  Remove SSL extension table.
	delete                  Delete an entry from tunnel list.
---------------------------------------------------------------------------
===========================================================================
$>
```

### LXD Compose

To simplify the developer life we use [lxd-compose](https://mottainaici.github.io/lxd-compose-docs/)
to setup the complete services chain locally that is needed to test the application.

In particular, the service is managed by these containers:

  - one container/service with [Kafka Broker](https://kafka.apache.org/)
    (standalone installation) with Zookeeper (v.2.7.0)
  - one container/service with [TimescaleDB](https://www.timescale.com/)
  - one container/service where are executed the **web-keepaliver-producer** and
    **web-keepaliver-consumer** tools.
  - one container/service with [Grafana](https://grafana.com/)

### Indentation & Code Style

See PEP-0008.

