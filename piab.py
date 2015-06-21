import struct
import random
import socket
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor

SERVER_IP = '192.168.56.1'
CLIENT_IP = '192.168.56.7'
BROADCAST_IP = '192.168.56.255'
TFTP_ROOT = '/private/tftpboot/'
BOOTFILE = 'pxelinux.0'

def dhcp_pack(op, htype, hlen, hops, xid, secs, flags,
	ciaddr, yiaddr, siaddr, giaddr, chaddr, cookie, options=[]):

    out = struct.pack('!BBBBIHHIIII', op, htype, hlen, hops, xid, secs,
	    flags, ciaddr, yiaddr, siaddr, giaddr)

    out += struct.pack('!IIII', *chaddr)
    out += '\x00' * 192
    out += struct.pack('!I', cookie)

    options.append((255, '\x01'))
    for option in options:
	out += struct.pack('BB', option[0], len(option[1]))
	out += option[1]

    return out

def dhcp_unpack(data):
    op, htype, hlen, hops = struct.unpack('BBBB', data[:4])
    xid = struct.unpack('!I', data[4:8])[0]
    secs, flags = struct.unpack('!HH', data[8:12])
    ciaddr, yiaddr, siaddr, giaddr = struct.unpack('!IIII', data[12:28])
    chaddr = struct.unpack('!IIII', data[28:44])
    cookie = struct.unpack('!I', data[236:240])[0]

    options = {}
    i = 240
    while i < len(data):
	code = struct.unpack('B', data[i])[0]
	size = struct.unpack('B', data[i+1])[0]
	options[code] = data[i+2:i+2+size]

	if code == 255:
	    break

	i = i+2+size

    return dict(op=op, htype=htype, hlen=hlen, hops=hops, xid=xid, secs=secs,
	    flags=flags, ciaddr=ciaddr, yiaddr=yiaddr, siaddr=siaddr, giaddr=giaddr,
	    chaddr=chaddr, cookie=cookie, options=options)

class DHCPServer(DatagramProtocol):
    def datagramReceived(self, data, (host, port)):
	packet = dhcp_unpack(data)

	options = [(53, '\x01' if packet['options'][53] == '\x01' else '\x05'),
		(1, '\xff\xff\xff\x00'), (51, struct.pack('!I',3600)),
		(54, socket.inet_aton(SERVER_IP)),
		(66, SERVER_IP),
		(67, BOOTFILE)]

	siaddr = int(socket.inet_aton(SERVER_IP).encode('hex'),16)
	yiaddr = int(socket.inet_aton(CLIENT_IP).encode('hex'),16)

	offer = dhcp_pack(2, 1, 6, 0, packet['xid'], 0, 0, 0, yiaddr, siaddr,
		0, packet['chaddr'], packet['cookie'], options)

	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.bind((SERVER_IP, 0))
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
	sock.sendto(offer, (BROADCAST_IP, 68))

class TFTPSession(DatagramProtocol):
    def __init__(self, filename, addr):
	self.filename = filename
	self.block = 1
	self.addr = addr

    def send_block(self, block):
	packet = '\x00\x03' + struct.pack('!H', block) + \
	    self.data[(block-1) * 512 : block * 512]

	self.transport.write(packet)

    def send_error(self, code, msg):
	packet = '\x00\x05' + struct.pack('!H', code) + \
	    msg + '\x00'

	self.transport.write(packet)

    def startProtocol(self):
	print 'Started transfer for client (%s, %d), file: %s' % \
		(self.addr[0], self.addr[1], self.filename)

	self.transport.connect(*self.addr)

	try:
	    self.data = file(self.filename, 'rb').read()
	except:
	    print 'File Not Found: %s' % self.filename
	    self.send_error(1, 'File Not Found')
	    return

	self.send_block(1)
	self.block = 2

    def datagramReceived(self, data, (host, port)):
	self.send_block(self.block)
	self.block += 1


class TFTPServer(DatagramProtocol):
    def datagramReceived(self, data, (host, tid)):
	options = data[2:].split('\x00')
	filename = options[0]

	filename = TFTP_ROOT + filename
	reactor.listenUDP(0, TFTPSession(filename, (host, tid)))

reactor.listenUDP(67, DHCPServer())
reactor.listenUDP(69, TFTPServer())
reactor.run()
