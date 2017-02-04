class ApplicationType():
    Server = 'Server'
    Manager = 'Manager'
    Bot = 'Bot'
    SubModules = 'SubModules'


class BaseApplication():
    def __init__(self):
        self.configDict = None

    def load(self, configDict):
        self.configDict = configDict

    def patch(self, target, optionalTargetName=None):
        if self.configDict is None:
            raise NotConfigured

        if optionalTargetName is not None:
            lookedConfigName = optionalTargetName
        else:
            lookedConfigName = target.__class__.__name__

        if lookedConfigName in self.configDict:
            for key, value in self.configDict[lookedConfigName].items():
                setattr(target, key, value)

    def get(self, target, optionalTargetName=None):
        if self.configDict is None:
            raise NotConfigured

        if optionalTargetName is not None:
            lookedConfigName = optionalTargetName
        else:
            lookedConfigName = target.__class__.__name__

        return self.configDict[lookedConfigName]


class Server(BaseApplication):
    pass


class Manager(BaseApplication):
    pass


class Bot(BaseApplication):
    pass


class SubModules():
    pass


class BaseConfigPointer():
    def getAsDict(self):
        raise ConfigPointerNotImplemented


class FileConfigPointer(BaseConfigPointer):
    def __init__(self, filePath):
        import os
        if not os.path.exists(filePath):
            raise FileConfigPointerFileNotExists

        self.filePath = filePath

    def getAsDict(self):
        import ConfigParser
        config = ConfigParser.ConfigParser()
        config.optionxform = str
        config.read(self.filePath)
        dataDict = config._sections
        for name, value in config._sections.items():
            del dataDict[name]['__name__']

        for key in dataDict:
            dataDict[key] = dict(**dataDict[key])
            dataDict[key].pop('__name__', None)

        return dict(dataDict)


server = Server()
manager = Manager()
bot = Bot()
_type = None


def configure(type, configPointer):
    if not isinstance(configPointer, BaseConfigPointer):
        raise ConfigPointerNotAccepted

    global _type
    _type = type

    configObject = _get(type)

    configDict = {}
    import re
    import importlib
    import sys
    for configBlockName, subConfig in configPointer.getAsDict().items():
        searchDict = re.search('([\w, \.]*)\{(.*)\}', configBlockName)
        searchArr = re.search('(\w*)\((.*)\)', configBlockName)
        if searchDict is not None:
            (className, configBlockName) = (searchDict.group(1), searchDict.group(2))
            if className not in configDict:
                configDict[className] = {}

            if configBlockName not in configDict[className]:
                configDict[className][configBlockName] = {}

            for indexName, indexValue in subConfig.items():
                configDict[className][configBlockName][indexName] = indexValue

                # module = importlib.import_module(className)
        elif searchArr is not None:
            (className, configBlockName) = (searchArr.group(1), searchArr.group(2))
            if className not in configDict:
                configDict[className] = {}

            if configBlockName not in configDict[className]:
                configDict[className][configBlockName] = []

            for indexName, indexValue in subConfig.items():
                configDict[className][configBlockName].append(indexValue)
        else:
            if configBlockName not in configDict:
                configDict[configBlockName] = {}

            configDict[configBlockName].update(subConfig)

    configObject.load(configDict)
    return configObject


def _get(type):
    if type == ApplicationType.Server:
        global server
        return server
    elif type == ApplicationType.Manager:
        global manager
        return manager
    elif type == ApplicationType.Bot:
        global bot
        return bot

    raise TypeNotFound()


def get(type=None):
    global _type
    if type is None:
        type = _type

    return _get(type)


def patch(target, type=None):
    configurer = get()
    configurer.patch(target)


class TypeNotFound(Exception):
    pass


class ConfigPointerNotImplemented(Exception):
    pass


class FileConfigPointerFileNotExists(Exception):
    pass


class ConfigPointerNotAccepted(Exception):
    pass


class NotConfigured(Exception):
    pass
