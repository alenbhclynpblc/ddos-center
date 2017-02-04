from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
import os, ConfigParser
from ccapi.Messaging import ApiRequestMessage, CCTransferProtocol, DataResponseMessage, PrintableResponseMessage
import inspect
import threading, time, signal


class Job(threading.Thread):
    def __init__(self, command, taskPool, environment=os.environ, group=None, target=None, name=None, args=(),
                 kwargs=None, verbose=None):
        threading.Thread.__init__(self, group, target, name, args, kwargs, verbose)
        self.daemon = True
        self.taskPool = taskPool
        self.command = command
        self.environment = environment

    def start(self):
        super(Job, self).start()

    def run(self):
        import subprocess
        self.pro = subprocess.Popen(self.command, shell=True, preexec_fn=os.setsid)
        self.pro.communicate()
        self.taskPool.moveToDone(self.command)

    def stop(self):
        os.killpg(os.getpgid(self.pro.pid), signal.SIGKILL)


class TaskPool():
    def __init__(self):
        self.executionPool = {}
        self.donePool = {}

    def register(self, command):
        count = len(filter(lambda x: x.startswith(str(command)), self.executionPool.keys()))
        if count > 0:
            command = "%s #%s" % (str(command), time.time())

        thread = Job(command, self)
        self.executionPool[str(command)] = thread
        thread.start()

    def unregister(self, command):
        try:
            self.executionPool[str(command)].stop()
        except Exception as e:
            print e.message
            pass

    def get(self, command):
        if command in self.executionPool.keys():
            return self.executionPool[str(command)]

    def find(self, command):
        return [i for i in self.getCurrentExecutions().keys() if i.find(command) > -1]

    def getCurrentExecutions(self):
        return self.executionPool

    def getCurrentCommands(self):
        return self.executionPool.keys()

    def moveToDone(self, command):
        self.donePool[str(command)] = self.executionPool[str(command)]
        del self.executionPool[str(command)]

    def getFinishedCommands(self):
        return self.donePool


class TheApi():
    tasks = TaskPool()

    def __init__(self, bot):
        self.bot = bot

    def execute(self, command):
        self.tasks.register(command)
        res = DataResponseMessage()
        res.setDataDict({'status': 1})
        return res

    def executeIfNotExists(self, command):
        if command not in self.tasks.getCurrentCommands():
            return self.execute(command)
        else:
            return {}

    def getTasks(self):
        response = DataResponseMessage()
        response.setData(self.tasks.getCurrentExecutions().keys())
        return response

    def killTask(self, task):
        tasks = self.tasks.find(task)
        for i in tasks:
            self.tasks.unregister(i)

        response = DataResponseMessage()
        response.setData(tasks)
        return response

    def searchTasks(self, task):
        tasks = self.tasks.find(task)
        response = DataResponseMessage()
        response.setData(tasks)
        return response

    def dropConnection(self):
        reactor.callFromThread(reactor.stop)
        return {}


class Bot(CCTransferProtocol):
    def __init__(self, autoRecover):
        self.lastThread = None
        CCTransferProtocol.__init__(self)
        self.autoRecover = autoRecover

    def connectionMade(self):
        CCTransferProtocol.connectionMade(self)

    def connectionLost(self, reason):
        CCTransferProtocol.connectionLost(self, reason)

    def requestReceived(self, session, requestMessage):
        request = ApiRequestMessage().loadDataOverDict(requestMessage)

        if request.getAction() == None:
            return PrintableResponseMessage().addWarning('Action Parameter Needed!')

        api = TheApi(self)

        if not hasattr(api, request.getAction()):
            response = DataResponseMessage()
            return response

        neededArguments = inspect.getargspec(getattr(api, request.getAction())).args
        neededArguments.remove('self')

        try:
            requestedArguments = request.getArguments()
            apiArguments = []
            for neededArg in neededArguments:
                if neededArg in requestedArguments:
                    apiArguments.append(requestedArguments[neededArg])

            response = getattr(api, request.getAction())(*apiArguments)
            return response
        except Exception as e:
            res = PrintableResponseMessage()
            res.addAlarm(e.message)
            return res


class BotFactory(ClientFactory):
    def __init__(self):
        self.bot = None
        self.autoRecovery = True

    def buildProtocol(self, addr):
        self.bot = Bot(self.autoRecovery)
        return self.bot

    def clientConnectionLost(self, connector, reason):
        if not hasattr(self, 'autoRecover') or self.bot.autoRecover:
            connector.connect()

    def clientConnectionFailed(self, connector, reason):
        if not hasattr(self, 'autoRecover') or self.bot.autoRecover:
            connector.connect()


class BotInitializer():
    server_ip = "localhost"
    server_port = 62000

    def __init__(self):
        scriptPath = os.path.dirname(os.path.realpath(__file__))
        scriptPath = os.path.join(scriptPath, 'master.ini')
        from ccapi import Configurer
        file = Configurer.FileConfigPointer(scriptPath)
        Configurer.configure(Configurer.ApplicationType.Manager, file)
        Configurer.patch(self)

    def run(self):
        reactor.connectTCP(self.server_ip, int(self.server_port), BotFactory())
        reactor.run()


if __name__ == "__main__":
    b = BotInitializer()
    b.run()
