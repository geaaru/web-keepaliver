# Author: Daniele Rondina, geaaru@sabayonlinux.org
# Description:
# Note: Use PEP-0008 for indentation with max 79 chars on line.

import asyncio
import yaml
import logging
import logging.handlers
import argparse
import functools
import signal

from web_keepaliver import LOGGER_NAME, VERSION

from abc import abstractmethod, ABCMeta
from sys import stdout

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from kafka import KafkaAdminClient, KafkaConsumer

from concurrent.futures import ThreadPoolExecutor, CancelledError


class AppSeed(metaclass=ABCMeta):
    """
        Abstract class to manage base CLI application:

        * define commands line parser
        * initialize logging
        * initialize signal handler.

    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, logger_name=LOGGER_NAME,
                 config_default_file=None,
                 app_description=None,
                 loop=None):
        if not logger_name:
            logger_name = LOGGER_NAME

        self.logger = logging.getLogger(logger_name)
        self.configuration = {}
        self.cmdline_options = None
        self.debug = False
        self.name = 'UNKNOWN'

        if loop:
            self.loop = loop
        else:
            self.loop = asyncio.get_event_loop()
        self._thread_pool_initialized = False
        self._executor = None
        self._cancel_tasks = True

        self.parser = argparse.ArgumentParser(
            description=app_description,
            formatter_class=argparse.RawDescriptionHelpFormatter
        )

        self.parser.add_argument(
            '--version', action='version',
            version=VERSION
        )

        self.parser.add_argument(
            "-c", '--config',
            nargs='?',
            dest='config',
            default=config_default_file,
            help='Path of the configuration file.'
        )

        self.parser.add_argument(
            "-L", "--loglevel",
            nargs='?',
            dest='log_level',
            default=None,
            help="%s\n%s" %
                 ("Define log level between these values"
                  ": info, debug, warn, error.",
                  " (Optional, default is info).")
        )

        self.parser.add_argument(
            '-l', '--logfile',
            nargs='?',
            default=None,
            dest='log_file',
            help='Log file to use for trace migration "'
                 '"operation. (Optional).'
        )

        self.parser.add_argument(
            '-q', '--quiet',
            action='store_true',
            default=False,
            dest='quiet',
            help='Quiet stdout logging.'
        )

        self.parser.add_argument(
            '-d', '--debug',
            action='store_true',
            default=None,
            dest='debug',
            help='Enable debugging log on stdout.'
        )

        self.parser.add_argument(
            '-V', '--verbose',
            action='store_true',
            default=False,
            dest='verbose',
            help='Enable log on stdout with current level.'
        )

    def init_thread_pool(self, size=20):
        if self._thread_pool_initialized:
            raise Exception('Thread pool already initialized!')

        self._executor = ThreadPoolExecutor(max_workers=size)
        self.loop.set_default_executor(self._executor)
        self._thread_pool_initialized = True

    def wait_cancel_tasks(self):
        for task in asyncio.Task.all_tasks():
            try:
                self.loop.run_until_complete(task)
            except CancelledError:
                pass

    def get_loop(self):
        return self.loop

    def get_parser(self):
        return self.parser

    def get_logger(self) -> logging.Logger:
        return self.logger

    def _load_config_file(self, config_file):
        """

            Parse configuration file in YAML format.

        :param config_file: Configuration file
        :return:  nothing
        """
        with open(config_file, 'r') as f:
            self.configuration = yaml.safe_load(f)

    def get_config_param(self, category, param, default=None):
        """

        :param category: Category of the configuration data
        :param param: Configuration param to read.
        :param default:  Default value if category or param aren't present.
        :return: the value of the param or the default value.
        """
        if param is None:
            raise Exception('Invalid param')

        if category is not None and category in self.configuration:
            if param in self.configuration[category]:
                return self.configuration[category][param]
        elif category is None and param in self.configuration:
            return self.configuration[param]

        return default

    def get_config_category(self, category, default=None):
        """
        Retrieve a complete configuration category options.

        :param category: Name of the category
        :param default:  Define the default value if the category
                         is not present.
        :return:         The dictionary with the category options or
                         the default value.
        """
        if category is None:
            raise Exception('Invalid category')

        if category in self.configuration:
            return self.configuration[category]
        return default

    def parse_cmd_line(self):
        """
            Parse command line arguments,
            processing configuration file and
            initialize logging.
        """
        args = self.parser.parse_args()

        if args.config is None:
            self.parser.error(
                'Missing mandatory configuration file option. "'
                '"Use --help for help message')

        self.cmdline_options = args

        if args.debug is not None:
            self.debug = args.debug

        self._init_module()

    @staticmethod
    def _get_log_level(ll):
        """
        Convert log level string in logging level.

        :param ll: log level string
        :return:  logging level const.
        """
        if ll == 'debug':
            level = logging.DEBUG
        elif ll == 'warn':
            level = logging.WARNING
        elif ll == 'error':
            level = logging.ERROR
        else:
            level = logging.INFO

        return level

    def _init_logging(self):
        level = self._get_log_level(
            self.get_config_param('log', 'level', 'info')
        )

        if self.cmdline_options.log_level is not None:
            level = self._get_log_level(self.cmdline_options.log_level)

        log_backup_count = self.get_config_param('log', 'backup_count', 5)
        log_max_bytes = self.get_config_param('log', 'max_bytes', 1024000)
        log_file = self.get_config_param('log', 'logfile', None)

        # Override file name from command line argument
        if self.cmdline_options.log_file is not None:
            log_file = self.cmdline_options.log_file

        self.logger.setLevel(level)

        log_date_fmt = self.get_config_param('log', 'date_format', None)
        log_formatter = self.get_config_param(
            'log', 'formatter',
            '%(asctime)s %(levelname)6s (%(threadName)-10s) '
            '[%(process)10d] %(message)s'
        )

        formatter = logging.Formatter(log_formatter, log_date_fmt)

        if log_file:
            handler = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=log_max_bytes,
                backupCount=log_backup_count
            )
            handler.setFormatter(formatter)
            handler.setLevel(level)
            self.logger.addHandler(handler)

        if not self.cmdline_options.quiet and (
                self.debug or self.cmdline_options.verbose
        ):
            handler_stdout = logging.StreamHandler(stdout)
            handler_stdout.setFormatter(formatter)

            if self.debug:
                handler_stdout.setLevel(logging.DEBUG)
                # Force logger threshold to DEBUG
                self.logger.setLevel(logging.DEBUG)
            else:
                handler_stdout.setLevel(level)

            self.logger.addHandler(handler_stdout)

    def __signal_handler__(self, signame):

        i = 0
        self.logger.info("Received signal %s. n. Task = %d.",
                         signame, len(asyncio.Task.all_tasks()))

        # Cancel all existing task
        if self._cancel_tasks:
            for task in asyncio.Task.all_tasks():
                i += 1

                if task.cancel():
                    self.logger.debug("Pending Task %s in cancelling...", i)
                else:
                    self.logger.warning(
                        "Pending Task %s is not cancellable.", i
                    )

        # Call callback
        try:
            self.signal_handler(signame)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning(
                "Exception from user signal handler function: %s", exc,
            )
            # Ignore user errors

    def add_signal_handler(self, loop=None):
        if loop is None:
            loop = self.loop

        for signame in ('SIGINT', 'SIGTERM'):
            loop.add_signal_handler(getattr(signal, signame),
                                    functools.partial(self.__signal_handler__,
                                                      signame))

    def _init_module(self):
        self._load_config_file(self.cmdline_options.config)

        self._init_logging()

        self.logger.debug(
            'Processed configuration file %s',
            self.cmdline_options.config
        )

    @abstractmethod
    def main(self, parse_cmdline_opts=True):
        pass

    @abstractmethod
    def signal_handler(self, signame):
        pass


class KafkaClientConfigurator(metaclass=ABCMeta):
    """
        Abstract class that implement function to build
        a Kafka Consumer or Producer from custom options
        defined in the class that use this class.
    """

    @abstractmethod
    def get_kafka_configuration(self, producer=False, admin=False):
        pass

    def create_kafka_producer(self):
        opts = self.get_kafka_configuration(producer=True)
        return AIOKafkaProducer(**opts)

    def create_kafka_consumer(self):
        opts = self.get_kafka_configuration(producer=False)
        return AIOKafkaConsumer(**opts)

    def create_sync_kafka_consumer(self):
        opts = self.get_kafka_configuration(producer=False)
        return KafkaConsumer(**opts)

    def create_kafka_admin(self):
        opts = self.get_kafka_configuration(admin=True)
        return KafkaAdminClient(**opts)

# vim: ts=4 sw=4 expandtab
