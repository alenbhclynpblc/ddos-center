import structlog
from structlog import get_logger
from structlog.twisted import LoggerFactory
import logging, sys, os
import Configurer


class RootLogger():
    log_level = 10
    log_directory = "logs"
    log_directoryIsRelative = 1
    log_format = "%(asctime)s %(message)s"
    log_variable_order = "event, ip, port, sended, received"

    def __init__(self):
        Configurer.patch(self)
        applicationName = os.path.basename(sys.modules['__main__'].__file__).split('.')[0].lower()
        moduleName = self.__class__.__name__.lower()
        logFileName = "%s-%s.log" % (applicationName, moduleName)

        if self.log_directoryIsRelative:
            logDirectory = os.path.join(os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__)),
                                        self.log_directory)

        logging.basicConfig(
            format=self.log_format,
            filename="%s/%s" % (logDirectory, logFileName),
            # stream=sys.stdout,
            level=int(self.log_level),
        )

        structlog.configure(
            processors=[
                structlog.processors.KeyValueRenderer(
                    key_order=self.log_variable_order.split(','),
                ),
            ],
            context_class=structlog.threadlocal.wrap_dict(dict),
            logger_factory=structlog.stdlib.LoggerFactory(),
        )

        self.logger = get_logger()

    def bind(self, **kwargs):
        self.logger = self.logger.bind(**kwargs)

    def info(self, message, **kwargs):
        self.logger.info(message, **kwargs)

    def warn(self, message, **kwargs):
        self.logger.warn(message, **kwargs)

    def critical(self, message, **kwargs):
        self.logger.critical(message, **kwargs)

    def debug(self, message, **kwargs):
        self.logger.debug(message, **kwargs)
