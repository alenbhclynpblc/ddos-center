class DataCenterMethodNotImplemented(Exception):
    pass


# PUT => Update
# GET => Fetch
# DELETE => Remove
# BUILD => Create

class BaseDatacenter():
    def __init__(self, connectionConfig={}):
        self.connectionConfig = connectionConfig
        self.defaultImage = None
        self.defaultLocation = None
        self.defaultResourceSize = None

    def getServerTypes(self):
        raise DataCenterMethodNotImplemented

    def getServers(self):
        raise DataCenterMethodNotImplemented

    def getSshKeys(self):
        raise DataCenterMethodNotImplemented

    def getLocations(self):
        raise DataCenterMethodNotImplemented

    def getImages(self):
        raise DataCenterMethodNotImplemented

    def getResourceSizes(self):
        raise DataCenterMethodNotImplemented

    def buildSshKey(self, keyName, keyData):
        raise DataCenterMethodNotImplemented

    def buildServer(self, image=None, location=None, resourceSize=None, tags=[]):
        raise DataCenterMethodNotImplemented

    def destroyServer(self, serverInstance):
        raise DataCenterMethodNotImplemented


import digitalocean


class Digitalocean(BaseDatacenter):
    def destroyServer(self, serverInstance):
        return BaseDatacenter.destroyServer(self, serverInstance)

    def getLocations(self):
        return BaseDatacenter.getLocations(self)

    def buildServer(self, image=None, location=None, resourceSize=None, tags=[]):
        return BaseDatacenter.buildServer(self, image, location, resourceSize, tags)

    def getSshKeys(self):
        return digitalocean.manager.get_all_sshkeys()

    def getResourceSizes(self):
        return BaseDatacenter.getResourceSizes(self)

    def getImages(self):
        return BaseDatacenter.getImages(self)

    def getServers(self):
        return BaseDatacenter.getServers(self)

    def getServerTypes(self):
        return BaseDatacenter.getServerTypes(self)

    def __init__(self, connectionConfig={}):
        BaseDatacenter.__init__(self, connectionConfig)

    def buildSshKey(self, keyName, keyData):
        return BaseDatacenter.buildSshKey(self, keyName, keyData)
