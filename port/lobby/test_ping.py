import socket, time
from test_lobby2 import ServiceTests
from ping_service import PingService, MAGIC


class PingTests(ServiceTests):
    # Reuse only setup/helpers, not all room tests.
    def test_server_rtt_challenge_and_stale_value(self):
        self.config['ping']={'listen':'127.0.0.1','host':'127.0.0.1','port':1}
        ping=PingService(self.service)
        # Choose an ephemeral UDP port without changing production configuration.
        self.config['ping']['port']=0
        # start() needs a configured port; reserve one on a temporary socket.
        reserve=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);reserve.bind(('127.0.0.1',0))
        self.config['ping']['port']=reserve.getsockname()[1];reserve.close()
        a=self.enter();b=self.enter('乙');ping.start()
        client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(3)
        try:
            probe=self.call('poll',a)['room']['probe']
            self.assertNotEqual(probe['key'],self.call('poll',b)['room']['probe']['key'])
            endpoint=('127.0.0.1',probe['port'])
            client.sendto(MAGIC+b'R'+probe['key'].encode(),endpoint)
            # The registration key cache refreshes once a second.
            packet,_=client.recvfrom(256)
            self.assertEqual(len(packet),17);self.assertEqual(packet[:9],MAGIC+b'P')
            time.sleep(.080);client.sendto(MAGIC+b'O'+packet[9:],endpoint)
            until=time.monotonic()+2
            while time.monotonic()<until:
                measured=self.call('poll',a)['room']['seats'][0]['ping']
                if measured>=0:break
                time.sleep(.02)
            self.assertGreaterEqual(measured,20);self.assertLess(measured,500)
            self.assertEqual(self.call('poll',a)['room']['seats'][1]['ping'],-1)
            # Stale UDP RTT is independent of a healthy HTTP presence heartbeat.
            for step in (4,4,3):
                self.now+=step;self.call('poll',a)
            self.assertEqual(self.call('poll',a)['room']['seats'][0]['ping'],-1)
        finally:client.close();ping.close()


# Inheritance supplies helpers without rerunning the base class's tests here.
for _name in list(vars(ServiceTests)):
    if _name.startswith('test_'):setattr(PingTests,_name,None)

if __name__=='__main__':
    import unittest
    unittest.main(verbosity=2)
