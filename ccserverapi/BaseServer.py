from ccapi.Messaging import CCTransferProtocol, NotificationMessage
from ccapi.RootLogger import RootLogger


class BaseServer(RootLogger, CCTransferProtocol):
    def __init__(self, pool):
        self.pool = pool
        self.address = ()
        CCTransferProtocol.__init__(self)
        RootLogger.__init__(self)

    def connectionMade(self):
        CCTransferProtocol.connectionMade(self)
        address = self._getAddressIndex()
        self._getCurrentServer().connections[address] = self
        self.address = address
        self.bind(ip=self._getIpAddress(), port=self._getPort(), server=self.__class__.__name__)
        self.info('Connection Made')
        message = NotificationMessage()
        message.addNotification('Connection MADE : %s' % (self._getIpAddress()))
        self.sendBroadcastPushMessage(message)

    def connectionLost(self, reason):
        self.info('Connection Lost')

        if self.address in self._getCurrentServer().connections:
            del self._getCurrentServer().connections[self.address]

        CCTransferProtocol.connectionLost(self, reason)
        message = NotificationMessage()
        message.addNotification('Conection LOST : %s' % (self._getIpAddress()))
        self.sendBroadcastPushMessage(message)

    def sendBroadcastRequest(self, request):
        sessions = []
        for address, client in self._getCurrentServer().connections.items():
            sessions.append(client.sendRequest(request))

        return sessions

    def sendBroadcastPushMessage(self, message):
        sessions = []
        for address, client in self._getCurrentServer().connections.items():
            sessions.append(client.sendPushMessage(message))

        return sessions

    def sendBroadcastPushMessageExceptSelf(self, message):
        sessions = []
        for address, client in self._getCurrentServer().connections.items():
            if self._getIpAddress() != address.host:
                sessions.append(client.sendPushMessage(message))

        return sessions

    def _getCurrentServer(self):
        return self.pool.getServer(str(self.__class__))

    def _getServerArguments(self):
        return self._getCurrentServer().getArguments()

    def _getServerArgument(self, argumentName):
        return self._getCurrentServer().getArgument(argumentName)
