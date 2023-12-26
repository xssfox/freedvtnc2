import logging
logging.basicConfig(level=logging.DEBUG)

import unittest
from unittest.mock import Mock, call
from . import modem

class TestModem(unittest.TestCase):
    def testMultiRX(self):
        callback = Mock()
        rx = modem.FreeDVRX(callback)
        for freedv_modem in rx.modems:
            freedv_modem.callback = callback
        with open("c01.raw","rb") as f:
            while chunk := f.read(100):
                rx.write(chunk) # spoon feed in data to make sure buffering is working

        self.assertEqual(callback.call_count, 10)
        for mocked_call in callback.call_args_list:
            self.assertEqual(len(mocked_call[0]),1)
            self.assertIsInstance(mocked_call[0][0], modem.FreeDVFrame)
            self.assertIsInstance(mocked_call[0][0].snr, float)
            self.assertIsInstance(mocked_call[0][0].sync, int)
            self.assertEqual(mocked_call[0][0].modem, 'DATAC1')
    def testTX(self):
        tx = modem.FreeDVTX()
        callback = Mock()
        rx = modem.FreeDVRX(callback)
        tx_output = tx.write(b'test')
        tx_output += tx.write(b'test'*200)
        rx.write(tx_output)
        self.assertEqual(callback.call_args_list[0][0][0],modem.Packet(data=b'test',header=255))
        self.assertEqual(callback.call_args_list[1][0][0],modem.Packet(data=b'test'*200,header=255))

if __name__ == '__main__':
    unittest.main()