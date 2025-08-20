sudo apt update
sudo apt install -y icecast2
sudo sed -i 's/^ENABLE=.*/ENABLE=true/' /etc/default/icecast2
sudo tee /etc/icecast2/icecast.xml >/dev/null << 'XML'
<icecast>
  <location>Earth</location>
  <admin>admin@localhost</admin>

  <limits>
    <clients>100</clients>
    <sources>2</sources>
    <queue-size>524288</queue-size>
    <client-timeout>30</client-timeout>
    <header-timeout>15</header-timeout>
    <source-timeout>10</source-timeout>
    <burst-on-connect>1</burst-on-connect>
    <burst-size>65535</burst-size>
  </limits>

  <authentication>
    <source-password>hackme</source-password>
    <relay-password>hackme</relay-password>
    <admin-user>admin</admin-user>
    <admin-password>hackme</admin-password>
  </authentication>

  <hostname>0.0.0.0</hostname>
  <listen-socket>
    <port>8000</port>
  </listen-socket>

  <paths>
    <basedir>/usr/share/icecast2</basedir>
    <webroot>/usr/share/icecast2/web</webroot>
    <adminroot>/usr/share/icecast2/admin</adminroot>
    <logdir>/var/log/icecast2</logdir>
    <pidfile>/run/icecast2/icecast.pid</pidfile>
  </paths>

  <logging>
    <accesslog>access.log</accesslog>
    <errorlog>error.log</errorlog>
    <loglevel>3</loglevel>   <!-- 4=debug, 3=info -->
    <logsize>10000</logsize>
  </logging>

  <security>
    <chroot>0</chroot>
  </security>

  <mount>
    <mount-name>/stream</mount-name>
    <password>hackme</password>
  </mount>

  <fileserve>1</fileserve>
</icecast>
XML

# 3) Папки/права для логов и pid
sudo mkdir -p /var/log/icecast2 /run/icecast2
sudo chown -R icecast2:icecast /etc/icecast2 /var/log/icecast2 /run/icecast2
sudo chmod 640 /etc/icecast2/icecast.xml

sudo chown icecast2:icecast -R /etc/icecast2
sudo chmod 640 /etc/icecast2/icecast.xml

sudo systemctl enable --now icecast2
sudo systemctl restart icecast2
sudo systemctl status icecast2 --no-pager -l

sudo ufw allow 8000/tcp || true



curl -I http://127.0.0.1:8000/
