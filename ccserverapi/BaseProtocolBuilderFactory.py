from twisted.internet.protocol import Factory
import sys


class BaseProtocolBuilderFactory(Factory):
    def __init__(self, serverPool,
                 serverFullName='ccapi.BaserServer',
                 serverClassName='BaseServer',
                 serverArugments={}):

        self.serverPool = serverPool
        self.serverPool.addServer(serverFullName + '.' + serverClassName, self)
        self.connections = {}
        self.serverClassName = serverClassName
        self.serverFullName = serverFullName
        self.serverArguments = serverArugments

    def getArguments(self):
        return self.serverArguments

    def getArgument(self, argumentName):
        if argumentName in self.serverArguments:
            return self.serverArguments[argumentName]

        return None

    def buildProtocol(self, addr):
        if self.serverFullName in sys.modules.keys():
            return getattr(sys.modules[self.serverFullName], self.serverClassName)(self.serverPool)

        raise Exception('Server could not found in modules !')

    def removeConnectionFromList(self, ipv4):
        del self.connections[ipv4]

    def getConnections(self, ip=None, port=None):
        if ip is None and port is None:
            return self.connections
        else:
            checkIps = True if ip is not None else False
            checkPort = True if port is not None else False

            tmpPool = {}
            for ipv4, con in self.connections.items():
                if checkIps and not str(ipv4.host).startswith(ip):
                    continue

                if checkPort and not str(ipv4.port) == str(port):
                    continue

                tmpPool[ipv4] = con
                
            return tmpPool

    def getFirstXConnections(self, x):
        f = 0
        pool = {}
        for ipv4, con in self.connections.items():
            if f < x:
                pool[ipv4] = con

            f += 1

        return pool
