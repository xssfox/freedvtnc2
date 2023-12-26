import logging
logging.basicConfig(level=logging.DEBUG)

import unittest
from unittest.mock import Mock, call
from . import audio
import time

class TestAudio(unittest.TestCase):
    def test_audio_list_devices(self):
        audio.devices # just test that this function doesn't error - we can probably mock out pyaudio for proper tests
        callback = Mock()
        with audio.InputDevice(callback, 8000):
            time.sleep(0.1) # enough time to give an audio sample
        callback.assert_called()
