import urllib.request
import re
import base64
import os
import datetime
print(datetime.datetime.now(),"vpngate download - start")
#os.mkdir('output')



with urllib.request.urlopen('http://www.vpngate.net/api/iphone/') as f:
    csv = f.read().decode('utf-8')

for root, dirs, files in os.walk('/ovpn'):
    for f in files:
        os.unlink(os.path.join(root, f))



p = re.compile("^([^,]{3,}),.+,([a-zA-Z0-9+=]{100,})",flags=re.MULTILINE)
for m in p.finditer(csv):
    b64 = m.group(2)
    name = m.group(1)
    ovpnText = base64.b64decode(b64).decode('utf-8')

    with open('/ovpn/'+name+'.ovpn', 'w') as f:
        f.write(ovpnText)
    print(datetime.datetime.now(), "vpngate - download - write: "+ name)

print(datetime.datetime.now(), "vpngate - download - end")