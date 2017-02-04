import json, time
from tabulate import tabulate
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import connectionDone
from RootLogger import RootLogger


class CorruptedDataFormatException(Exception):
    pass


class CorruptedRequestException(Exception):
    pass


class DifferentTransmissionDataPartFound(Exception):
    pass


class RawRequestDataNotLoaded(Exception):
    pass


class RstTracer(Exception):
    def setRequestId(self, requestId):
        self.requestId = requestId

    def getRequestId(self):
        return self.requestId or None


class WriteMethodNotImplemented(Exception):
    pass


class DataConversation():
    def __init__(self, data='{}'):
        data = self._organize(data)
        if data is False:
            raise CorruptedDataFormatException

        self._data = data

    def _organize(self, data):
        dataType = type(data)
        if dataType == str:
            data = json.loads(data)

        return data

    def get(self):
        return self._data

    def set(self, dataDict):
        self._data = dataDict


class RawMessageData(DataConversation):
    pass


class BaseMessage():
    def __init__(self):
        # self.setRequestId(None)
        self.setData({})

    # def getRequestId(self):
    #     return self.requestId
    #
    # def setRequestId(self, id):
    #     self.requestId = id

    def setData(self, data):
        self.data = RawMessageData(data)

    def setDataOverObject(self, data):
        self.data = data

    def getDataDict(self):
        return self.data.get()

    def setDataDict(self, dataDict):
        self.data.set(dataDict)

    def getMessageType(self):
        return self.__class__.__name__

    def buildDataForString(self):
        return self.getDataDict()

    def loadDataOverJsonString(self, jsonString):
        dict = json.loads(jsonString)
        return self.loadDataOverDict(dict)

    def loadDataOverDict(self, dict):
        if 'data' in dict:
            for key, value in dict['data'].items():
                if hasattr(self, key):
                    setattr(self, key, value)

        self.validate()
        return self

    def validate(self):
        return True

    def __str__(self):
        return json.dumps({
            'type': self.getMessageType(),
            'data': self.buildDataForString()
        })


class ApiRequestMessage(BaseMessage):
    def __init__(self):
        self.action = None
        self.arguments = None
        BaseMessage.__init__(self)

    def setAction(self, action):
        self.action = action

    def getAction(self):
        return self.action

    def setArguments(self, arguments):
        self.arguments = arguments

    def getArguments(self):
        return self.arguments

    def getDataDict(self):
        self.setData({'action': self.action, 'arguments': self.arguments})
        return BaseMessage.getDataDict(self)

    def validate(self):
        return BaseMessage.validate(self)


class DataResponseMessage(BaseMessage):
    pass


class PrintableResponseMessage(BaseMessage):
    def __init__(self):
        self.table = {'header': [], 'rows': []}
        self.messages = []
        self.tableRowCount = 0
        BaseMessage.__init__(self)

    def addWarning(self, message=''):
        self.messages.append(['Warning', message])
        return self

    def addAlarm(self, message=''):
        self.messages.append(['Alarm', message])
        return self

    def addNotification(self, message=''):
        self.messages.append(['Notification', message])
        return self

    def setTableHeader(self, columns=[]):
        if type(columns) is dict:
            columns.update({'rowid': 'Row ID'})
        else:
            columns = ['Row ID'] + columns

        self.table['header'] = columns
        return self

    def addTableRow(self, columns=[]):
        if type(columns) is dict:
            columns.update({'rowid': self.tableRowCount})
        else:
            columns = [self.tableRowCount] + columns

        self.tableRowCount += 1

        self.table['rows'].append(columns)
        return self

    def buildDataForString(self):
        if len(self.messages):
            self.getDataDict()['messages'] = self.messages

        if len(self.table['header']) or len(self.table['rows']):
            self.getDataDict()['table'] = self.table

        return BaseMessage.buildDataForString(self)

    def printOutput(self):
        self.printOnlyMessages()
        self.printOnlyTable()

    def printOnlyMessages(self):
        if len(self.messages):
            for messageType, message in self.messages:
                prefix = {
                    'Warning': '[-] ~>',
                    'Alarm': '[!] ~>',
                    'Notification': '[*] ~>'
                }.get(messageType, 'Notification')

                print prefix, message

    def printOnlyTable(self):
        if len(self.table['header']) > 0 or len(self.table['rows']) > 0:
            print tabulate(self.table['rows'], (self.table['header']))

    def getRowCount(self):
        return len(self.table['rows'])


class CriticalAlarm(PrintableResponseMessage):
    def printOutput(self):
        print "\n\n", "<------------------------- Critical Alarm -------------------------->"
        PrintableResponseMessage.printOutput(self)
        print "<------------------------------------------------------------------>"


class WarningAlarm(PrintableResponseMessage):
    def printOutput(self):
        print "\n\n", "<------------------------- Warning -------------------------------->"
        PrintableResponseMessage.printOutput(self)
        print "<------------------------------------------------------------------>"


class NotificationMessage(PrintableResponseMessage):
    def printOutput(self):
        print "\n", "< ------------------------- Notification -------------------------------->"
        PrintableResponseMessage.printOutput(self)
        print "<----------------------------------------------------------------------->"


class NullResponseMessage(BaseMessage):
    pass


# Multiple request mode for partial data transfer
#   SynRequest: => Client X request multirequest mode to Y
#   SynAckRequest: => Y Accepts multirequest mode
#   AckRequest: => Client X send multiple ACK requests for transfer data
#   FinRequest: / RstRequest: => Client Y accept request and ends message with success / Client Y drops communication bec fail
#
#
# Single request mode
#   AckRequest:               => Client X send message with single transfer
#   FinRequest: / RstRequest: => Client Y accept request and ends message with success / Client Y Drops communication bec fail

class SocketWriteInterface():
    def __init__(self, socket):
        self.socket = socket

    def write(self, message):
        raise WriteMethodNotImplemented

    def _getSocket(self):
        return self.socket


class CCSocketWriteInterface(SocketWriteInterface):
    def write(self, message):
        SocketWriteInterface._getSocket(self).writeSomeData('%s\r\n' % str(message))
        # SocketWriteInterface._getSocket(self).write() => Will wait a new traffic occures ! Use writeSomeData !
        # SocketWriteInterface._getSocket(self).doWrite()

    def getIpIndex(self):
        return self.socket.getPeer()

    def getIpAddress(self):
        return self.socket.getPeer().host

    def getPort(self):
        return self.socket.getPeer().port


class CCTransferProtocol(LineReceiver):
    def __init__(self):
        self.sessions = {}

    def _getIpAddress(self):
        return self.transport.getPeer().host

    def _getPort(self):
        return self.transport.getPeer().port

    def _getAddressIndex(self):
        return self.socketWriteInterface.getIpIndex()

    def connectionMade(self):
        self.socketWriteInterface = CCSocketWriteInterface(self.transport)
        LineReceiver.connectionMade(self)

    def connectionLost(self, reason=connectionDone):
        self.sessions = {}
        LineReceiver.connectionLost(self, reason)

    def write(self, message):
        self.transport.writeSomeData(message)

    def getIpIndex(self):
        return self.transport.getPeer()

    def getIpAddress(self):
        return self.transport.getPeer().host

    def getPort(self):
        return self.transport.getPeer().port

    def lineReceived(self, line):
        if line.strip() == '':
            return

        line = str(line).strip()
        try:
            session = self._findSessionOfRequest(line)
        except RstTracer as e:
            id = e.getRequestId()
            self._dropSessionId(id)
            return
        except CorruptedRequestException as e:
            raise e

        if session is None:
            session = CCTransferSession(self, CCTransfer.BASE_Responder)
            self._registerNewSession(session, session.parseAndReturnRequestId(line))
            # print '[!] New Session Constructed ', session.requestId
        try:
            session.proceedReceivedMessage(line)
        except RstTracer as e:
            self.sessionReseted(session)
            self._dropSession(session)

        if session.sessionType == CCTransfer.BASE_Requester:
            if session.isRequestSended():
                self.statusUpdateRequestSended(session, session.getRequestedMessage())
                return

            if session.isResponseReceived():
                self.responseReceived(session, session.getResponseMessage())
                # State is done received(FIN[s])
                self._dropSession(session)
                return

        if session.sessionType == CCTransfer.BASE_Responder:
            if session.isPushNotificationGotten():
                self.pushReceived(session, session.getPushedNotificationMessage())
                return
            elif session.isRequestGotten():
                import threading
                ## If not, core thread will be stuck on creating response
                ## and will not be able to listen requests/responses
                thread = threading.Thread(target=self._sendResponse, args=(session,))
                thread.daemon = True
                thread.start()
                return

    def _sendResponse(self, session):
        request = session.getRequestedMessage()
        response = self.requestReceived(session, request)
        # Interrupted proceedReceivedMessage calls, first response will be generated
        # Last ACK was called we need to trigger Fin requests
        responsePackets = session.chopMessage(response)
        session.addMessage(session.sessionType, CCTransfer.STATE_Fin, responsePackets)
        session.triggerSendResponse()
        # writed(FIN[s])
        self.statusUpdateResponseSended(session, response)
        self._dropSession(session)

    def _findSessionOfRequest(self, line):
        requestData = CCTransferSession(self).parseAndReturnRequestId(line)
        if requestData in self.sessions.keys():
            return self.sessions[requestData]

        return None

    def _registerNewSession(self, session, sessionId):
        self.sessions[sessionId] = session

    def _dropSessionId(self, sessionId):
        if self.sessions.has_key(str(sessionId)):
            del self.sessions[sessionId]

    def _dropSession(self, session):
        self._dropSessionId(session.requestId)

    def sendRequest(self, message):
        handeledSession = CCTransferSession(self, CCTransfer.BASE_Requester)
        messages = handeledSession.chopMessage(message)
        handeledSession.addMessage(CCTransfer.BASE_Requester, CCTransfer.STATE_Ack, messages)
        self._registerNewSession(handeledSession, handeledSession.requestId)
        handeledSession.triggerSendRequest()
        return handeledSession

    def sendPushMessage(self, message):
        handeledSession = CCTransferSession(self, CCTransfer.BASE_Requester)
        messages = handeledSession.chopMessage(message)
        handeledSession.addMessage(CCTransfer.BASE_Requester, CCTransfer.STATE_Psh, messages)
        handeledSession.triggerSendRequest()

    def pushReceived(self, session, requestMessage):
        pass

    # Requester opened a new transfer session and send an request
    def requestReceived(self, session, requestMessage):
        pass

    # Response received one of the requests
    # @implement
    def responseReceived(self, session, responsedMessage):
        pass

    # @implement
    def statusUpdateRequestSended(self, session, message):
        pass

    # @implement
    def statusUpdateResponseSended(self, session, message):
        pass

    # Something happened but requestReceived / responseReceived / messageSended methods didn't called
    # @implement
    def messageNotificationGot(self, type, message):
        pass

    def sessionReseted(self, session):
        pass


class MessageBuilder():
    def __init__(self, maxMessagePartNo):
        self.lastMessagePartNo = -1  # Message part numbers starts with 0
        self.maxMessagePartNo = maxMessagePartNo
        self.dataParts = ''
        self.lastRequestedMessagePartNo = 0
        self.buildedMessage = None

    def preCheck(self, currentMessagePartNo):
        if self.lastMessagePartNo + 1 != currentMessagePartNo:
            raise CorruptedRequestException(
                'Message sequence numbers not mets, one of the seq-no packet is missing')

        if currentMessagePartNo > self.maxMessagePartNo:
            raise CorruptedRequestException('Maximum message packet length exceed!')
        pass

    def addData(self, data, currentMessagePartNo):
        self.preCheck(currentMessagePartNo)

        self.dataParts += data
        self.lastMessagePartNo += 1

        if currentMessagePartNo == self.maxMessagePartNo:
            try:
                self.buildedMessage = json.loads(self.dataParts)
                return True
            except:
                raise CorruptedRequestException('Message traffic is done but data could not been decoded')

        return False

    def getMessage(self):
        return self.buildedMessage


class CCTransfer(RootLogger):
    STATE_Syn = 'SynRequest'
    STATE_SynAck = 'SynAckRequest'
    STATE_Ack = 'AckRequest'
    STATE_Fin = 'FinRequest'
    STATE_Rst = 'RstRequest'
    STATE_Psh = 'PshRequest'

    BASE_Requester = 'RequesterBase'
    BASE_Responder = 'ResponderBase'


class CCTransferSession(RootLogger):
    transferSessionTypes = {
        0: CCTransfer.BASE_Requester,
        1: CCTransfer.BASE_Responder
    }

    transferStateOrderTable = {
        0: CCTransfer.STATE_Syn,
        1: CCTransfer.STATE_SynAck,
        2: CCTransfer.STATE_Ack,
        3: CCTransfer.STATE_Fin,
        4: CCTransfer.STATE_Psh
    }

    acknowledgeConfig = {
        'maxLength': 2000
    }

    def __init__(self, socketWriteInterface, sessionType=CCTransfer.BASE_Responder):
        self.requestId = None
        self.lastState = None
        self.socket = socketWriteInterface

        self.sessionType = sessionType

        self._constructedAt = time.time()
        self._updatedAt = time.time()

        self.receivedMessage = None
        self.receivedPushNotification = None  # Stateless
        self.sendedMessage = None
        self._waitingToSendMessage = None

        self._messageHookes = {
            CCTransfer.BASE_Responder: {
                CCTransfer.STATE_SynAck: ['{}'],
                CCTransfer.STATE_Fin: [],
                CCTransfer.STATE_Rst: ['{}']
            },
            CCTransfer.BASE_Requester: {
                CCTransfer.STATE_Syn: ['{}'],
                CCTransfer.STATE_Ack: [],
                CCTransfer.STATE_Rst: ['{}'],
                CCTransfer.STATE_Psh: []
            }
        }

        self._messageHookeStatuses = []

        RootLogger.__init__(self)
        self.bind(ip=self.socket.getIpAddress(), port=self.socket.getPort(), type=sessionType)

        if self.sessionType == CCTransfer.BASE_Requester:
            import string, random, hashlib
            self.requestId = str(
                hashlib.md5(str(time.time()) + str(random.choice(string.letters + string.digits))).hexdigest())
            self.bind(sessionId=self.requestId)

    def addMessage(self, sessionType, sessionState, messages):
        if sessionType in self._messageHookes.keys():
            if sessionState in self._messageHookes[sessionType].keys():
                self._messageHookes[sessionType][sessionState].extend(messages)

    def getMessageParts(self, sessionType, sessionState):
        if sessionType in self._messageHookes.keys():
            if sessionState in self._messageHookes[sessionType].keys():
                return self._messageHookes[sessionType][sessionState]

        return []

    def _hookDone(self, sessionState, sessionType):
        self._messageHookeStatuses.append(sessionState + '_' + sessionType)

    def _isHookDone(self, sessionState, sessionType):
        if sessionState + '_' + sessionType in self._messageHookeStatuses:
            return True

        return False

    def sendHooks(self, sessionType, sessionState):
        if sessionType in self._messageHookes.keys():
            if sessionState in self._messageHookes[sessionType].keys():
                self.debug(sessionState + ' Packets transmitting')

                messages = self._messageHookes[sessionType][sessionState]
                currentMessagePartNo = 0
                maxMessagePartNo = len(messages) - 1
                # print "\t" + "[*] " + sessionState + " Sended"
                for msg in messages:
                    msg = {
                        'message': str(msg),
                        'currentMessagePartNo': currentMessagePartNo,
                        'maxMessagePartNo': maxMessagePartNo,
                        'requestId': self.requestId,
                        'requestType': sessionState
                    }
                    currentMessagePartNo += 1
                    msg = json.dumps(msg)
                    self.debug('Sending data', sended=msg)
                    self.socket.write('%s\r\n' % str(msg))

    def saveRawRequestMessage(self, message):
        self.debug('Message Created', sended=message)
        self.sendedMessage = message

    def triggerSendRequest(self):
        if len(self.getMessageParts(self.sessionType, CCTransfer.STATE_Ack)) > 1:
            self.sendSynRequest()
        else:
            self.sendAckRequests()

        if len(self.getMessageParts(self.sessionType, CCTransfer.STATE_Psh)) > 0:
            self.sendPshRequests()

    def triggerSendResponse(self):
        self.sendFinResponse()

    def _buildPacket(self, requestType, messageString="", currentMessagePartNo=0, maxMessagePartNo=0):
        return {
            'requestType': requestType,
            'message': str(messageString),
            'currentMessagePartNo': currentMessagePartNo,
            'maxMessagePartNo': maxMessagePartNo,
            'requestId': self.requestId
        }

    def chopMessage(self, message):
        if message is None or str(message).strip() == '':
            return ['{}']

        messageString = str(message)
        maxLength = 1000
        messages = [messageString[i:i + maxLength] for i in range(0, len(messageString), maxLength)]
        return messages

    def proceedReceivedMessage(self, rawRequestData):
        self.debug('Line Received', received=rawRequestData)
        rawRequestData = self.parseRawDataToDict(rawRequestData)

        # Existense was checked on parseRawDataToDict
        requestType = rawRequestData['requestType']
        requestId = rawRequestData['requestId']
        currentMessagePartNo = int(rawRequestData['currentMessagePartNo'])
        maxMessagePartNo = int(rawRequestData['maxMessagePartNo'])
        message = rawRequestData['message']

        try:
            # If requestId is different do not accept
            if self.requestId is not None and requestId != self.requestId:
                self.debug('Request id not accepted')
                raise DifferentTransmissionDataPartFound

            # In listener mode we will not have requestId, we need to register requestId when first gotten
            if self.requestId is None:
                # print '[!] New Request ID Registered : '
                self.bind(sessionId=requestId)
                self.debug('New session constructed')
                self.requestId = requestId

                if requestType not in [CCTransfer.STATE_Syn, CCTransfer.STATE_Ack, CCTransfer.STATE_Psh]:
                    self.debug('State not accepted, request id was none but first state not an SYN or ACK')
                    raise CorruptedRequestException('Wrong state type detected')

            # Check transfer state movement is legal
            if self.lastState not in self._detectNeededPreviousState(requestType):
                self.debug('Received state not accepted')
                raise CorruptedRequestException('State flow not accepted')

            # If requester sends directly ACK request for multi-ack mode, drop !
            if currentMessagePartNo != maxMessagePartNo and self.lastState == None:
                self.debug('Current message part no and max message part no need to be 0, last state was None')
                raise CorruptedRequestException('Syn-Ack Sequence not followed')

            self.lastState = requestType
            self._updatedAt = time.time()

            if requestType == CCTransfer.STATE_Psh:
                if self.sessionType == CCTransfer.BASE_Requester:
                    self.debug('Corrupted request found, got PSH message on requester session')
                    raise CorruptedRequestException('Push message got in wrong base type.')
                else:
                    pass

            # Responder Lifecycle received(SynRequest) / respond(SynAckRequest) / received-multiple(AckRequests) / respond-multiple(FinRequest)
            if requestType == CCTransfer.STATE_Syn and self.sessionType == CCTransfer.BASE_Responder:
                self.sendSynAckResponse()
                self.debug('SYN gotten, SynAck sended')
                return

            # Responder Lifecycle received(SynRequest) / respond(SynAckRequest) / received-multiple(AckRequests) / respond-multiple(FinRequest)
            # # Requester Lifecycle writes(SynRequest) / received(SynAckRequest) / writes-multiple(AckRequests) / received-multiple(FinRequest)
            # # # PSH is stateless and directly sended/received, it will not responde
            if (requestType == CCTransfer.STATE_Ack and self.sessionType == CCTransfer.BASE_Responder) \
                    or (requestType == CCTransfer.STATE_Fin and self.sessionType == CCTransfer.BASE_Requester) \
                    or (requestType == CCTransfer.STATE_Psh and self.sessionType == CCTransfer.BASE_Responder):

                if not hasattr(self, 'messageBuilder'):
                    self.messageBuilder = MessageBuilder(maxMessagePartNo)
                    self.debug('Message builder constructed')
                else:
                    self.debug('Message builder found, adding data')

                if self.messageBuilder.addData(message, currentMessagePartNo):
                    self.debug('Message building completed')
                    if requestType == CCTransfer.STATE_Psh:
                        self.receivedPushNotification = self.messageBuilder.getMessage()
                    else:
                        self.receivedMessage = self.messageBuilder.getMessage()

                    del self.messageBuilder
                else:
                    self.debug('Message data added')

                return True

            # Requester Lifecycle writes(SynRequest) / received(SynAckRequest) / writes-multiple(AckRequests) / received-multiple(FinRequest)
            if requestType == CCTransfer.STATE_SynAck and self.sessionType == CCTransfer.BASE_Requester:
                self.sendAckRequests()
                self.debug('ACK Requests sended')
                # print '[*] SynAck Received - Need To Send ACKs'
                return

            # No any valid state triggered ? Screw :)

            self.debug('No any action triggered !')
            raise CorruptedRequestException('State flow corrupted, message could not proceessed')
        except Exception as e:
            self.debug('Exception got', exception=e.message)
            self.sendRstResponse(e)
            self.debug('Exception raised', exceptionMessage=e.message)

    def sendPshRequests(self):
        self.lastState = CCTransfer.STATE_Psh
        self.sendHooks(self.sessionType, self.lastState)

    def sendSynRequest(self):
        self.lastState = CCTransfer.STATE_Syn
        self.sendHooks(self.sessionType, self.lastState)

    def sendAckRequests(self):
        self.lastState = CCTransfer.STATE_Ack
        self.sendHooks(self.sessionType, self.lastState)

    def sendSynAckResponse(self):
        self.lastState = CCTransfer.STATE_SynAck
        self.sendHooks(self.sessionType, self.lastState)

    def sendRstResponse(self, exception):
        self.addMessage(self.sessionType, CCTransfer.STATE_Rst, [exception.message])
        self.sendHooks(self.sessionType, CCTransfer.STATE_Rst)
        raise RstTracer(exception.message)

    def sendFinResponse(self):
        self.lastState = CCTransfer.STATE_Fin
        self.sendHooks(self.sessionType, self.lastState)

    def isPushNotificationGotten(self):
        if self.sessionType == CCTransfer.BASE_Responder and self.receivedPushNotification is not None:
            return True

    def isRequestGotten(self):
        if self.sessionType == CCTransfer.BASE_Responder and self.receivedMessage is not None:
            return True

        return False

    def isRequestSended(self):
        if self.sessionType == CCTransfer.BASE_Requester and self._isHookDone(self.sessionType, CCTransfer.STATE_Ack):
            return True

        return False

    def isResponseSended(self):
        if self.sessionType == CCTransfer.BASE_Responder and self._isHookDone(self.sessionType, CCTransfer.STATE_Fin):
            return True

        return False

    def isResponseReceived(self):
        if self.sessionType == CCTransfer.BASE_Requester and self.receivedMessage is not None:
            return True

        return False

    def getRequestedMessage(self):
        if self.sessionType == CCTransfer.BASE_Requester:
            return self.sendedMessage
        else:
            return self.receivedMessage

    def getResponseMessage(self):
        if self.sessionType == CCTransfer.BASE_Responder:
            return self.sendedMessage
        else:
            return self.receivedMessage

    def getPushedNotificationMessage(self):
        return self.receivedPushNotification

    def isAlive(self):
        if self._updatedAt + 3 > time.time():
            return False

        if self._constructedAt + 12 > time.time():
            return False

        return True

    def parseAndReturnRequestId(self, rawRequestData):
        return self.parseRawDataToDict(rawRequestData, False)['requestId']

    def parseRawDataToDict(self, rawData, validate=True):
        try:
            rawRequestData = json.loads(rawData)
        except Exception as e:
            self.debug('JSON Parse failed on parseRawDataToDict')
            raise CorruptedRequestException('Corrupted format detected.')

        if not validate:
            return rawRequestData

        if not set(('requestId', 'currentMessagePartNo', 'maxMessagePartNo', 'message', 'requestType')).issubset(
                rawRequestData):
            self.debug('Parsed line have missing keys')
            raise CorruptedRequestException('Missing keys detected.')

        if rawRequestData['requestType'] == CCTransfer.STATE_Rst:
            rst = RstTracer()
            rst.setRequestId(rawRequestData['requestId'])
            self.debug('RST Packate got !')
            raise rst

        if rawRequestData['requestType'] not in self.transferStateOrderTable.values():
            self.debug('RequestType not in acceptable state table')
            raise CorruptedRequestException('Transfer state not accepted.')

        if type(rawRequestData['message']) not in [str, unicode]:
            self.debug('Message is not an string or unicode')
            raise CorruptedRequestException('Transfer message is not an string.')

        if type(rawRequestData['maxMessagePartNo']) is not int:
            self.debug('Maximum message part no not an int')
            raise CorruptedRequestException('maxMessagePartNo is not an int.')

        if type(rawRequestData['currentMessagePartNo']) is not int:
            self.debug('Current message part no not an int')
            raise CorruptedRequestException('currentMessagePartNo is not an int.')

        return rawRequestData

    def _detectNeededPreviousState(self, requestedState):
        keys = self.transferStateOrderTable.keys()
        values = self.transferStateOrderTable.values()
        requestedStateIndex = keys[values.index(requestedState)]

        if requestedStateIndex == 0:
            return [None]

        previousStates = [self.transferStateOrderTable[requestedStateIndex - 1]]

        if requestedState == CCTransfer.STATE_Psh:
            previousStates.append(None)
        elif requestedState == CCTransfer.STATE_Ack:
            previousStates.append(CCTransfer.STATE_Ack)
            previousStates.append(None)
        elif requestedState == CCTransfer.STATE_Fin:
            previousStates.append(CCTransfer.STATE_Fin)

        return previousStates

    def getOpponentIpIndex(self):
        return self.socket.getIpIndex()


"""
driver.linePulled(
    '{"currentMessagePartNo": 0, "maxMessagePartNo": 0, "message":"{}", "requestType": "SynRequest", "requestId": 1478727169.747272}')

driver.linePulled(
    '{"currentMessagePartNo": 0, "maxMessagePartNo": 0, "message":"{}", "requestType": "AckRequest", "requestId": 1478727169.747272}')

driver.linePulled(
    '{"currentMessagePartNo": 0, "maxMessagePartNo": 0, "message":"{}", "requestType": "AckRequest", "requestId": 1478727169.747272}')

driver.linePulled(
    '{"currentMessagePartNo": 0, "maxMessagePartNo": 0, "message":"{}", "requestType": "AckRequest", "requestId": 1478727169.747272}')
"""
