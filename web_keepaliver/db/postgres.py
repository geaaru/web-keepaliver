# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description: PostgreSQL models and const.
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import asyncpg
import logging
from enum import Enum

from abc import abstractmethod, ABCMeta


class PSQLKeepaliverTables(Enum):
    SITES_PROBES = 'sites_probes'
    SITES_STATUS = 'site_status'

    @staticmethod
    def list():
        return list(map(lambda c: c.value, PSQLKeepaliverTables))


class PostgresDatabase:

    @staticmethod
    async def register_probes(con, records: list):
        ans = 0
        if len(records) == 0:
            raise Exception('No probes available to store in db')

        columns = [
            'time', 'site', 'resource', 'method', 'url',
            'resp_http_code', 'resp_time_ms', 'expected_http_code',
            'ok', 'error_desc'
        ]

        res = await con.copy_records_to_table(
            PSQLKeepaliverTables.SITES_PROBES.value,
            records=records,
            columns=columns,
        )
        if res:
            ans = int(res.split()[1])
        return ans

    @staticmethod
    async def register_site_status(con, record: dict):
        ans = 0
        if not record:
            raise Exception('Invalid site status record')

        # Trying to update the record.
        res = await con.execute(
            """UPDATE %s SET last_update = $1,
               status = $2, n_resources = $3,
               err_counter = err_counter + $4
            WHERE site = $5""" % PSQLKeepaliverTables.SITES_STATUS.value,
            record['last_update'],
            record['status'],
            record['n_resources'],
            record['err_counter'],
            record['site'],
        )

        if res:
            rec_updated = int(res.split()[1])
            if rec_updated == 0:
                # POST: the record is not present.

                res = await con.execute(
                    """INSERT INTO %s
                    (last_update, status, n_resources, err_counter, site)
                    VALUES ($1, $2, $3, $4, $5)
                    """ % PSQLKeepaliverTables.SITES_STATUS.value,
                    record['last_update'],
                    record['status'],
                    record['n_resources'],
                    record['err_counter'],
                    record['site'],
                    )

                if res:
                    ans = int(res.split()[1])
            else:
                ans = rec_updated

        return ans


class PostgresConnector(metaclass=ABCMeta):
    """
        Abstract class to manage PostgreSQL connections
    """
    def __init__(self):
        self.ps_connection = None
        self.ps_pool = None

    def __termination_cb__(self, conn):
        # pylint: disable=unused-argument
        self.get_logger().info("Postgres connection terminated.")

    async def create_pool(self):
        """
            Create the connection pool.
        """
        opts = self.get_postgres_conn_options()
        self.get_logger().debug(
            "Creating connection pool to postgres database [%s]...", opts,
        )
        self.ps_pool = await asyncpg.create_pool(**opts)

        # Trying to retrieve connection server information
        con = await self.acquire()

        self.get_logger().info(
            "Connected to postgres server %s with pid %s.",
            con.get_server_version(),
            con.get_server_pid(),
        )
        await self.release(con)

    async def acquire(self):
        con = await self.ps_pool.acquire()
        con.add_termination_listener(self.__termination_cb__)
        return con

    async def release(self, con):
        await self.ps_pool.release(con)

    async def connect(self):
        """
            Create the database connection.
        """
        opts = self.get_postgres_conn_options()
        self.get_logger().debug(
            "Connecting postgres database [%s]...", opts,
        )
        self.ps_connection = await asyncpg.connect(**opts)
        self.get_logger().info(
            "Connected to postgres server %s with pid %s.",
            self.ps_connection.get_server_version(),
            self.ps_connection.get_server_pid(),
        )
        self.ps_connection.add_termination_listener(self.__termination_cb__)

    async def postgres_cleanup(self):
        if self.ps_connection:
            await self.ps_connection.close()
            self.ps_connection = None

        if self.ps_pool:
            await self.ps_pool.close()
            self.ps_pool = None

    @abstractmethod
    def get_postgres_conn_options(self):
        pass

    @abstractmethod
    def get_logger(self) -> logging.Logger:
        pass


# vim: ts=4 sw=4 expandtab
