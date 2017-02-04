import fabric
from fabric.api import run, env, put, parallel, execute, cd
from fabric.contrib.files import exists
from fabric.contrib.project import upload_project
from fabric.tasks import Task


class CommandNotFound(Exception):
    pass


class BotBuilder(Task):
    conf = {
        'coreModule': 'cc-bot',
        'indexPythonScript': 'main.py'
    }

    local = {
        'basePath': '/etc/cc-server/',
        'modulesPath': '/etc/cc-server/modules/',
        'configPath': '/etc/cc-server/master.conf',
        'apiPath': '/etc/cc-server/ccapi/'
    }

    remote = {
        'basePath': '/etc/cc-bot/',
        'modulePath': '/etc/cc-bot/modules/',
        'configPath': '/etc/cc-bot/master.conf'
    }

    fabricLogStateOutput = {
        'status': 1,
        'aborts': 0,
        'warnings': 0,
        'running': 1,
        'stdout': 0,
        'stderr': 0,
        'exceptions': 0,
        'debug': 0,
        'user': 1
    }

    def __init__(self, hosts=[], envSettings={}, alias=None, aliases=None, default=False,
                 name=None, *args, **kwargs):
        if type(hosts) is str:
            hosts = [hosts]

        from ccapi import Configurer
        Configurer.patch(self)
        print self.fabricLogStateOutput

        env.hosts = hosts
        env.warn_only = False
        env.exceptions = ['everything']
        env.abort_exception = Exception
        for key, value in self.fabricLogStateOutput.items():
            fabric.state.output[key] = bool(value)

        for key, value in envSettings.items():
            if hasattr(env, key):
                setattr(env, key, value)

        Task.__init__(self, alias, aliases, default, name, *args, **kwargs)

    def deploy(self):
        execute(self._deploy)

    def loadModule(self, moduleName):
        execute(self._loadModule, moduleName=moduleName)

    def removeModule(self, moduleName):
        execute(self._removeModule, moduleName=moduleName)

    def start(self):
        execute(self._start)

    def kill(self):
        execute(self._kill)

    @parallel(100)
    def _deploy(self):
        run('apt-get update')
        run('apt-get -y install python python-pip build-essential libssl-dev libffi-dev python-dev gcc')
        run('pip install twisted tabulate structlog')
        if exists(self.remote['basePath']):
            run('rm -r ' + self.remote['basePath'])

        run('mkdir -p ' + self.remote['modulePath'])

        from os import path
        from fabric.contrib.project import upload_project

        localPath = path.join(self.local['modulesPath'], self.conf['coreModule'])
        remotePath = path.join(self.remote['basePath'], '..')
        upload_project(local_dir=localPath, remote_dir=remotePath)

        localPath = self.local['apiPath']
        remotePath = self.remote['basePath']
        upload_project(local_dir=localPath, remote_dir=remotePath)

        put(self.local['configPath'], self.remote['configPath'], 0500)

    @parallel(100)
    def _loadModule(self, moduleName):
        from os import path
        localPath = path.join(self.local['modulesPath'], moduleName)
        remotePath = self.remote['modulePath']

        upload_project(local_dir=localPath, remote_dir=remotePath)

    @parallel(100)
    def _removeModule(self, moduleName):
        from os import path
        remotePath = path.join(self.remote['modulePath'], moduleName)
        run(("rm -r %s" % remotePath))

    @parallel(100)
    def _start(self):
        from os import path
        remotePath = path.join(self.remote['basePath'], self.conf['indexPythonScript'])
        run("nohup python %s >& /dev/null < /dev/null &" % remotePath, pty=False)

    @parallel(100)
    def _kill(self):
        run('killall python')
