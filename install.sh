apt-get update;
apt-get -y install python python-pip build-essential libssl-dev libffi-dev python-dev gcc;
pip install twisted fabric cmd2 ipaddress tabulate structlog;

mv `pwd` /etc/cc-server/;
ip=$(ifconfig eth0 | grep 'inet addr:' | cut -d: -f2 | awk '{ print $1}');

echo "[BotInitializer]
server_ip=$ip
server_port=62000" > /etc/cc-server/modules/cc-bot/master.ini;