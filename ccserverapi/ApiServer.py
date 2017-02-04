from ccserverapi import BaseServer
from ccapi.Messaging import ApiRequestMessage, PrintableResponseMessage, CriticalAlarm, NotificationMessage
import inspect


class ApiServer(BaseServer):
    legitimate_ips = ["127.0.0.1"]

    def __init__(self, pool):
        from ccapi import Configurer
        Configurer.patch(self)
        BaseServer.__init__(self, pool)

    def connectionMade(self):
        if self._getIpAddress() in self.legitimate_ips:
            BaseServer.connectionMade(self)
        else:
            self.critical('Unauthorized server access!', ip=self._getIpAddress(), port=self._getPort())
            self.stopProducing()
            alertMessage = CriticalAlarm()
            alertMessage.addAlarm('Non-admin user tried to connect !!')
            alertMessage.setTableHeader(['ip', 'port'])
            alertMessage.addTableRow([self._getIpAddress(), self._getPort()])
            self.sendBroadcastPushMessage(alertMessage)

    def requestReceived(self, session, requestMessage):
        request = ApiRequestMessage().loadDataOverDict(requestMessage)

        if request.getAction() == None:
            self.debug('Message action not found', request=session.getRequestedMessage(), ip=self._getIpAddress(),
                       port=self._getPort())
            return PrintableResponseMessage().addWarning('Action Parameter Needed!')

        api = BaseServer._getServerArgument(self, 'api')

        if not hasattr(api, request.getAction()):
            self.debug('Message method not found', request=session.getRequestMessage(), ip=self._getIpAddress(),
                       port=self._getPort())
            response = PrintableResponseMessage().addWarning('Method not found!')
            notification = NotificationMessage()
            notification.addNotification(
                'Unwaited method call %s : [%s]' % (self.getIpAddress(), request.getAction()))
            self.write(response)
            self.sendBroadcastPushMessageExceptSelf(notification)
            return
        else:
            notification = NotificationMessage()
            notification.addNotification(
                'New method call %s : [%s]' % (self.getIpAddress(), request.getAction()))
            notification.setTableHeader(['Key', 'Value'])
            for key, value in request.getArguments():
                notification.addTableRow({'Key': key, 'Value': value})
            self.sendBroadcastPushMessageExceptSelf(notification)

        neededArguments = inspect.getargspec(getattr(api, request.getAction())).args
        neededArguments.remove('self')

        try:
            requestedArguments = request.getArguments()
            apiArguments = {}
            for neededArg in neededArguments:
                if neededArg in requestedArguments:
                    apiArguments[neededArg] = requestedArguments[neededArg]

            response = getattr(api, request.getAction())(**apiArguments)
            return response
        except Exception as e:
            # @todo Log exceptions!
            import traceback
            traceback.print_exc()
            res = PrintableResponseMessage()
            res.addAlarm(e.message)
            return res
