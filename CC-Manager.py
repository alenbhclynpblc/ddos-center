from twisted.internet import reactor
from twisted.internet.protocol import ClientFactory
from threading import Thread
from tabulate import tabulate
import time, os
import json
from ccapi.Messaging import *

import cmd2


class Master(CCTransferProtocol):
    writeResponse = False
    responses = []

    def __init__(self):
        self.lastThread = None
        CCTransferProtocol.__init__(self)

    def startCommandLineInterface(self):
        try:
            if self.lastThread is None:
                self.lastThread = Interacter(self, '_stopCommunication')
                self.lastThread.start()
        except Exception as e:
            pass

    def stopCommandLineInterface(self):
        try:
            if self.lastThread is not None:
                self.lastThread.stop()
                self.lastThread = None
        except SystemExit as e:
            pass

    def _stopCommunication(self, exit=False):
        pass

    def connectionMade(self):
        CCTransferProtocol.connectionMade(self)
        # print '[!] Connection Made'
        self.startCommandLineInterface()

    def connectionLost(self, reason):
        # print '[!] Connection Lost'
        self.stopCommandLineInterface()
        CCTransferProtocol.connectionLost(self, reason)

    def responseReceived(self, session, responsedMessage):
        self.responses.append({'requestId': session.requestId, 'response': responsedMessage})
        CCTransferProtocol.responseReceived(self, session, responsedMessage)

    def sendRequest(self, message):
        return CCTransferProtocol.sendRequest(self, message)

    # def requestReceived(self, session, requestMessage):
    #     CCTransferProtocol.requestReceived(self, session, requestMessage)
    #     self.lastThread.pushNotificationReceived(requestMessage)
    #     return DataResponseMessage()

    def pushReceived(self, session, pushNotification):
        self.lastThread.pushNotificationReceived(pushNotification)


class MasterFactory(ClientFactory):
    def buildProtocol(self, addr):
        self.master = Master()
        return self.master

    def clientConnectionLost(self, connector, reason):
        print '[!] Retrying Connection'
        connector.connect()
        time.sleep(3)

    def clientConnectionFailed(self, connector, reason):
        print '[!] Retrying Connection'
        connector.connect()
        time.sleep(3)


class CommandDetailsBuilder():
    def __init__(self, remoteMethodName):
        self.argumentIsNeeded = False
        self.argument = ''

        self.haveOptions = False
        self.options = []

        self.doc = ''

        self.remoteMethod = remoteMethodName

        self.inputArg = ''
        self.inputOptions = None

        self.apiRef = None
        self.optionNames = []

    def loadApiRef(self, apiRef):
        self.apiRef = apiRef

        if 'doc' in apiRef:
            self.doc = apiRef['doc']

        if 'argument' in apiRef:
            self.argument = apiRef['argument']['target']
            # self.argument = False if 'required' in apiRef['argument'] else True
            if 'required' in apiRef['argument']:
                self.argumentIsNeeded = apiRef['argument']['required']
            else:
                self.argumentIsNeeded = True

        if 'options' in apiRef:
            self.optionNames = apiRef['options'].keys()
            count = 0
            for methodName, methodSettings in apiRef['options'].items():
                methodName = str(methodName)
                methodOptionDatas = {}
                for needleSettingName, defaultValue in {'short': '-p' + str(count), 'long': '--param' + str(count),
                                                        'type': None, 'action': None,
                                                        'help': 'No any help found.', 'default': None}.items():
                    if needleSettingName in methodSettings:
                        methodOptionDatas[needleSettingName] = methodSettings[needleSettingName]
                    else:
                        methodOptionDatas[needleSettingName] = defaultValue
                count += 1

                self.options.append(methodOptionDatas)
                self.haveOptions = True

    def buildOptions(self):
        if self.haveOptions:
            result = []
            for s in self.options:
                tmpOption = s
                args = [s['short'], s['long']]
                del s['short']
                del s['long']
                kwargs = tmpOption
                result.append(cmd2.make_option(*args, **kwargs))
        else:
            result = []

        return result

    def buildArgName(self):
        if self.argumentIsNeeded:
            return self.argument

        return ''

    def generateApiRequest(self, arg, opts=None):
        if self.argumentIsNeeded and not len(arg.strip()) > 0:
            resp = PrintableResponseMessage()
            resp.addWarning('Required [arg] not found !')
            return resp

        r = ApiRequestMessage()
        r.setAction(self.generateRequestAction())
        r.setArguments(self.generateRequestArguments(arg, opts))
        return r

    def generateRequestAction(self):
        return self.remoteMethod

    def generateRequestArguments(self, arg, opts=None):
        arguments = {}
        if self.argumentIsNeeded or (self.argument.strip() != '' and arg.strip() != ''):
            arguments[self.argument] = arg.replace('\-', '-')

        if opts is not None and self.haveOptions:
            for remoteables in self.optionNames:
                if opts.get(remoteables) is not None:
                    arguments[remoteables] = opts.get(remoteables)

        return arguments


# Generate new hook for CommandLine 'do_' methods
def getHook(apiReferance, methodName):
    commandBuilder = CommandDetailsBuilder(methodName)
    commandBuilder.loadApiRef(apiReferance)

    @cmd2.options(commandBuilder.buildOptions(), arg_desc=commandBuilder.buildArgName())
    def ___api_call_hook(self, arg, opts={}):
        request = commandBuilder.generateApiRequest(arg, opts)
        if not isinstance(request, ApiRequestMessage):
            self.proceedResponse(json.loads(str(request)))
            return

        self.request(request)

    return ___api_call_hook


class Interacter(Thread):
    def __init__(self, master, callBackMethod):
        self.master = master
        self.callBackMethod = callBackMethod
        Thread.__init__(self)
        self.daemon = True
        self.commandline = None

    def run(self):
        self.commandline = CommandLine(self.master)
        self.commandline.loadapi()
        self.commandline.cmdloop()
        getattr(self.master, self.callBackMethod)()
        return

    def stop(self):
        if self.commandline is not None:
            self.commandline.cmdqueue.append('exit')

    def pushNotificationReceived(self, response):
        if self.commandline is not None:
            self.commandline.cmdqueue.append('pause')
            self.commandline.proceedResponse(response)


class CommandLine(cmd2.Cmd):
    debug = True
    prompt = 'Master > '
    terminators = []

    def __init__(self, master):
        self.master = master
        self.timeOut = 30
        self.__waitingResponse = False
        cmd2.Cmd.__init__(self)

    def do_remoteshell(self):
        pass

    def get_names(self):
        # return dir(self)
        result = ['do_shell', 'do_history', 'do_py', 'do_set', 'do_help']
        for i in self.apiRefs.keys():
            result.append('do_' + str(i))

        return result

    def preparse(self, raw, **kwargs):
        if raw.startswith('execute'):
            raw = raw.replace('-', '\-')

        return raw

    def loadapi(self):
        req = ApiRequestMessage()
        req.setAction('getApiRef')
        req.setArguments({})

        result = self.request(req)
        self.apiRefs = result
        for method, ref in self.apiRefs.items():
            if not hasattr(self, 'do_' + method):
                mthd = getHook(ref, method)
                setattr(self, 'do_' + method, mthd.__get__(self, self.__class__))
            else:
                del self.apiRefs[method]

    def emptyline(self):
        return

    def request(self, command):
        session = self.master.sendRequest(str(command))

        returnableData = None
        done = False
        startTime = time.time()
        while not session.isResponseReceived():
            time.sleep(1)

        response = session.getResponseMessage()
        if 'type' not in response or 'data' not in response:
            self.__warn('Corrupted response message!')
            return None

        return self.proceedResponse(response)

    def proceedResponse(self, response):
        if response['type'] == DataResponseMessage().getMessageType():
            return response['data']
        elif response['type'] in [CriticalAlarm().getMessageType(),
                                  WarningAlarm().getMessageType(),
                                  NotificationMessage().getMessageType(),
                                  PrintableResponseMessage().getMessageType()]:
            rsp = globals()[response['type']]()
            rsp.loadDataOverDict(response)
            rsp.printOutput()
            return response
        elif response['type'] == NullResponseMessage().getMessageType():
            p = PrintableResponseMessage()
            p.addNotification('Null response got.')
            p.printOutput()
        else:
            self.__warn('Unknow message format detected! ' + str(response))

    def __warn(self, message):
        print "\n", '[!] ', message, "\n"

    def __print(self, res, headers=[]):
        print "\n", tabulate(res, headers), "\n"

    def __notify(self, res, headers=[]):
        print '[!] Unwaited message cought !'
        print tabulate(res, headers)


class ManagerInitializer():
    server_ip = 'localhost'
    server_port = 62001

    def __init__(self):
        scriptPath = os.path.dirname(os.path.realpath(__file__))
        scriptPath = os.path.join(scriptPath, 'master.conf')
        from ccapi import Configurer

        file = Configurer.FileConfigPointer(scriptPath)
        Configurer.configure(Configurer.ApplicationType.Manager, file)
        Configurer.patch(self)

    def run(self):
        factory = MasterFactory()
        print 'Server IP: ', self.server_ip
        print 'Server Port: ', self.server_port
        reactor.connectTCP(self.server_ip, int(self.server_port), factory)
        reactor.run()


if __name__ == "__main__":
    m = ManagerInitializer()
    m.run()
