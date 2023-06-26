# -*- coding: utf-8 -*-
import logging

import structlog


class Logger:
    _instance = None
    _logger = None
    _std_logger = None

    def __new__(cls, log_level=logging.INFO, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._logger, cls._std_logger = cls.setup_structlog(log_level)
        return cls._instance

    @classmethod
    def setup_structlog(cls, log_level=logging.INFO):
        processors = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ]

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        cls._std_logger = logging.getLogger()
        cls._std_logger.setLevel(log_level)

        return structlog.get_logger(), cls._std_logger

    def get_logger(self):
        return self._logger

    def get_std_logger(self):
        return self._std_logger

    def set_level(self, log_level):
        level = logging.getLevelName(log_level)
        self._std_logger.setLevel(level)

    def info(self, message:str):
        self._logger.info(message)

    def error(self, message:str):
        self._logger.error(message)

    def debug(self, message:str):
        self._logger.debug(message)

    def warning(self, message:str):
        self._logger.warning(message)

    def critical(self, message:str):
        self._logger.critical(message)

    def exception(self, message:str):
        self._logger.exception(message)

    def log(self, level, message:str):
        self._logger.log(level, message)