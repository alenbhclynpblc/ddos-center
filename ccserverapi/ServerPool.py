class ServerPool():
    def __init__(self):
        self.servers = {}

    def addServer(self, serverName, serverObj):
        self.servers[serverName] = serverObj

    def getServer(self, serverName):
        return self.servers[serverName]
