# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description:
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import asyncio
import os
import traceback2

from sys import exit as start_shuttle

from web_keepaliver.common import AppSeed, KafkaClientConfigurator

KEEPALIVER_KAFKA_ADMIN_CONFIG = '/etc/web-keepaliver/kafka-admin.yml'
KEEPALIVER_KAFKA_ADMIN_DEF_NAME = 'web-keepaliver-kafka-admin'
KEEPALIVER_KAFKA_ADMIN_DESC = """
Copyright (c) 2021 Daniele Rondina

Web Keepaliver Kafka Admin CLI.
"""


class KeepaliverKafkaAdmin(AppSeed, KafkaClientConfigurator):

    def __init__(self):
        self.kafka_brokers = []
        self.kafka_admin = None
        self.kafka_consumer = None

        config_def_file = os.getenv(
            'KEEPALIVER_KAFKA_PRODUCER_CONFIG',
            KEEPALIVER_KAFKA_ADMIN_CONFIG,
        )

        AppSeed.__init__(self, logger_name='kafka-admin',
                         config_default_file=config_def_file,
                         app_description=KEEPALIVER_KAFKA_ADMIN_DESC)
        KafkaClientConfigurator.__init__(self)

        self.get_parser().add_argument(
            '--broker',
            action='store',
            default=[],
            nargs='*',
            type=str,
            dest='kafka_brokers',
            help='Override kafka brokers defined in the configuration file.'
        )

    def __del__(self):
        self._cleanup()

    def _cleanup(self):
        # TODO: check this issue. WeirdMethod seems wrong. Skip close for now.
        # Traceback (most recent call last):
        # File "web_keepaliver/kafka_admin.py", line 51, in __del__
        #     self._cleanup()
        # File "web_keepaliver/kafka_admin.py", line 57, in _cleanup
        #     self.kafka_consumer.close()
        # File "/usr/lib/python3.7/site-packages/kafka/consumer/group.py",
        # line 458, in close
        #     self._client.close()
        # File "/usr/lib/python3.7/site-packages/kafka/client_async.py",
        # line 435, in close
        #     conn.close()
        # File "/usr/lib/python3.7/site-packages/kafka/conn.py",
        # line 940, in close
        #     self.config['state_change_callback'](self.node_id, sock, self)
        # File "/usr/lib/python3.7/site-packages/kafka/util.py", line 50,
        # in __call__
        #     return self.method()(self.target(), *args, **kwargs)
        # File "/usr/lib/python3.7/site-packages/kafka/client_async.py",
        # line 269, in _conn_state_change
        #     with self._lock:
        # AttributeError: 'NoneType' object has no attribute '_lock'

        if self.kafka_consumer is not None:
            # self.kafka_consumer.close()
            self.kafka_consumer = None

        if self.kafka_admin is not None:
            # self.kafka_admin.close()
            self.kafka_admin = None

    def get_kafka_configuration(self, producer=False, admin=False):
        opts = self.get_config_category('kafka', {})

        if len(self.kafka_brokers) > 0:
            opts['bootstrap_servers'] = self.kafka_brokers

        opts['client_id'] = self.name
        return opts

    def _initialize(self):
        self.name = self.get_config_param(
            None, 'name', KEEPALIVER_KAFKA_ADMIN_DEF_NAME
        )

        self.init_thread_pool(size=self.get_config_param(
            'general', 'thread_pool_size', 20,
        ))
        self.add_signal_handler()

        asyncio.set_event_loop(loop=self.loop)
        self.kafka_admin = self.create_kafka_admin()
        self.kafka_consumer = self.create_sync_kafka_consumer()

        brokers = 'localhost:9092'
        if len(self.kafka_brokers) > 0:
            brokers = self.kafka_brokers
        else:
            brokers = self.get_config_param(
                'kafka', 'bootstrap_servers', brokers
            )

        self.logger.info(
            'Starting instance %s with kafka brokers %s.',
            self.name, brokers,
        )

    def signal_handler(self, signame):
        if signame == 'SIGTERM':
            self._cleanup()

    def main(self, parse_cmdline_opts=True):
        ans = 0
        if parse_cmdline_opts:
            self.parse_cmd_line()

        try:
            self._initialize()

            print(self.kafka_consumer.topics())
        except KeyboardInterrupt:
            pass
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error(
                'Unexpected error: %s\n%s', exc,
                '\n'.join(traceback2.format_exc().splitlines()) if self.debug
                else ''
            )
            ans = 1

        self.logger.info(
            "Instance %s stopped.", self.name
        )
        self.loop.close()

        return ans


def main():
    in_space = KeepaliverKafkaAdmin()
    start_shuttle(in_space.main())


if __name__ == '__main__':
    main()


# vim: ts=4 sw=4 expandtab
