import pyaudio
from dataclasses import dataclass
from tabulate import tabulate
import logging
import audioop as pyaudioop
import time
from threading import Lock, Thread
from typing import Callable
#from pydub import pyaudioop
import pydub
import math
from .modem import FreeDVTX, Packet

p = pyaudio.PyAudio()

FORMAT = pyaudio.paInt16


class AudioDevices:
    """
    Gets info of all audio devices
    """
    devices = []
    def __init__(self):
        for x in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(x)
            self.devices.append(AudioDevice(
                input_channels = device_info['maxInputChannels'],
                output_channels = device_info['maxOutputChannels'],
                sample_rate = int(device_info['defaultSampleRate']),
                name = device_info['name'],
                id = x
            ))
    def __str__(self):
        rows = [
            ["Id","Name","In", "Out", "SampleRate"]
        ]
        for device in self.devices:
            rows.append(
                [
                    device.id,
                    device.name,
                    device.input_channels,
                    device.output_channels,
                    device.sample_rate
                ]
            )
        return tabulate(rows, tablefmt="plain", headers="firstrow")
        
@dataclass
class AudioDevice:
    """
    Information about an audio device
    """ 
    input_channels: int
    output_channels: int
    sample_rate: int
    name: str
    id: int
   
devices = AudioDevices()

default_input_device = devices.devices[p.get_default_input_device_info()['index']]
default_output_device = devices.devices[p.get_default_output_device_info()['index']]


class InputDevice():
    """
    Handles receiving audio from an input device

    Sample rate is the expected modem sample rate
    """

    rate_state = None # used for sample rate conversions
    input_level = -99

    def __init__(self, callback: Callable[[bytes], None], sample_rate:int, name_or_id:str|int|None=None):
        self.sample_rate = sample_rate
        self.callback = callback
        self.bit_depth = pyaudio.get_sample_size(FORMAT)

        if  name_or_id != None:
            try:
                self.device = next(
                    device for device in devices.devices
                    if (device.name == name_or_id or
                    device.id == name_or_id) and device.input_channels > 0
                )
            except StopIteration:
                raise ValueError(f"Could not find audio device {name_or_id}")
        else:
            self.device = default_input_device
            

        logging.debug(f"Opening {self.device.name} for input")

        if self.device.input_channels >= 2:
            logging.warning("Stereo (or more) input detected - Only the first/left channel will be used")

        if self.device.sample_rate < sample_rate:
            logging.critical(f"Input audio device sample rate {self.device.sample_rate} is less than modems sample rate {sample_rate} - this will cause problems")

        self.stream = p.open(format=FORMAT,
                    channels=self.device.input_channels,
                    rate=self.device.sample_rate,
                    output=False,
                    input=True,
                    stream_callback=self.pa_callback,
                    input_device_index=self.device.id,
                    frames_per_buffer=4096
                )

    def close(self):
        self.stream.close()

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def pa_callback(self, in_data: bytes, frame_count: int, time_info, status_flag):
        max_audio = pyaudioop.max(in_data,pyaudio.get_sample_size(FORMAT))
        if max_audio:
            self.input_level = 20*math.log10(max_audio/(2**(self.bit_depth*8-1)))
        else:
            self.input_level = -99

        if self.device.input_channels == 2:
            in_data = pyaudioop.tomono(
                in_data,
                pyaudio.get_sample_size(FORMAT),
                1,
                0
            )

        if self.device.sample_rate != self.sample_rate:
            (in_data, self.rate_state) = pyaudioop.ratecv(
                in_data, 
                pyaudio.get_sample_size(FORMAT),
                1,
                self.device.sample_rate,
                self.sample_rate,
                self.rate_state
            )

        self.callback(in_data)

        return (None, pyaudio.paContinue)
    
class OutputDevice():
    """
    Handles sending audio from an output device

    Sample rate is the expected modem sample rate
    """

    rate_state = None # used for sample rate conversions

    buffer = bytearray()

    output_buffer_lock = Lock()
    send_queue_lock = Lock()

    inhibit = False
    output_buffer_thread = None

    @property
    def queue_ms(self):
        return (len(self.buffer)/self.bit_depth/self.device.sample_rate)*1000

    def __init__(self, 
                 sample_rate: int,
                 modem: FreeDVTX,
                 name_or_id:int|str|None=None, 
                 ptt_trigger:Callable[[],None]=None, 
                 ptt_release:Callable[[],None]=None, 
                 ptt_on_delay_ms:int=0, 
                 ptt_off_delay_ms:int=0,
                 db:float=0
                 ):
        self.sample_rate = sample_rate
        self.bit_depth = pyaudio.get_sample_size(FORMAT)
        self.ptt_on_delay_ms = ptt_on_delay_ms
        self.ptt_off_delay_ms = ptt_off_delay_ms
        self.db = db
        self.send_queue = []
        self.modem = modem

        if name_or_id != None:
            try:
                self.device = next(
                    device for device in devices.devices 
                    if (device.name == name_or_id or
                    device.id == name_or_id) and device.output_channels > 0
                )
            except StopIteration:
                raise ValueError(f"Could not find audio device {name_or_id}")
        else:
            self.device = default_output_device
            

        logging.debug(f"Opening {self.device.name} for output")

        if self.device.output_channels > 2:
            logging.warning("Output detected with more than 2 channels. We'll try to open the device with 2 channels")
            self.device.output_channels = 2

        if self.device.sample_rate < sample_rate:
            logging.critical(f"Output audio device sample rate {self.device.sample_rate} is less than modems sample rate {sample_rate} - this will cause problems")

        self.ptt_trigger = ptt_trigger
        self.ptt_release = ptt_release
        self.ptt = False

        self.stream = p.open(format=FORMAT,
                    channels=self.device.output_channels,
                    rate=self.device.sample_rate,
                    output=True,
                    input=False,
                    output_device_index=self.device.id,
                    stream_callback=self.pa_callback,
                    frames_per_buffer=4096
                )



    def write_raw(self,data:bytes):
        if self.device.sample_rate != self.sample_rate:
            (data, self.rate_state) = pyaudioop.ratecv(
                data, 
                pyaudio.get_sample_size(FORMAT),
                1,
                self.sample_rate,
                self.device.sample_rate,
                self.rate_state,
            )
        
        if self.db:
            data = pyaudioop.mul(data, 2, 10**(self.db/20.0))

        if self.device.output_channels == 2:
                    data = pyaudioop.tostereo(
                        data,
                        pyaudio.get_sample_size(FORMAT),
                        1,
                        1
                    )
        with self.output_buffer_lock:
            self.buffer += data

    def write(self, data: Packet):
        with self.send_queue_lock:
            self.send_queue.append(data)
    
    def audio_buffer(self):
        logging.debug("Populating audio buffer")
        # ptt delay
        pre_silence = pydub.AudioSegment.silent(duration=self.ptt_on_delay_ms, frame_rate=self.device.sample_rate)
        pre_silence = pre_silence.set_channels(self.device.output_channels)
        write_buffer = pre_silence.raw_data
        
        with self.send_queue_lock:
            send_queue = self.send_queue
            self.send_queue = []
        data = self.modem.write(send_queue)

        if self.device.sample_rate != self.sample_rate:
            (data, self.rate_state) = pyaudioop.ratecv(
                data, 
                pyaudio.get_sample_size(FORMAT),
                1,
                self.sample_rate,
                self.device.sample_rate,
                self.rate_state,
            )
        
        if self.db:
            data = pyaudioop.mul(data, 2, 10**(self.db/20.0))

        if self.device.output_channels == 2:
                    data = pyaudioop.tostereo(
                        data,
                        pyaudio.get_sample_size(FORMAT),
                        1,
                        1
                    )
        
        write_buffer += data
        
        # ptt delay
        post_silence = pydub.AudioSegment.silent(duration=self.ptt_off_delay_ms, frame_rate=self.device.sample_rate)
        post_silence = post_silence.set_channels(self.device.output_channels)
        write_buffer += post_silence.raw_data

        with self.output_buffer_lock:
            self.buffer += write_buffer
        logging.debug("wrote to output buffer")

    def pa_callback(self, in_data, frame_count, time_info, status):
        buffer_size = frame_count * pyaudio.get_sample_size(FORMAT) * self.device.output_channels

        output = bytearray(buffer_size)

        ptt = False


        # if we aren't transmitting and we have inhibited tx then skip
        if self.inhibit == True and self.ptt == False:
            return (bytes(output), pyaudio.paContinue)

        with self.output_buffer_lock:
            chunk_size = min(len(self.buffer), buffer_size)
            output[:chunk_size] = self.buffer[:chunk_size]
            if self.buffer:
                ptt = True
            elif self.send_queue and (not self.output_buffer_thread or not self.output_buffer_thread.is_alive()):
                # if we have no output buffer and queued messages we should start a thread to generate an output buffer
                self.output_buffer_thread = Thread(target=self.audio_buffer)
                self.output_buffer_thread.start()
            del self.buffer[:chunk_size]

        if self.ptt != ptt:
            if ptt and self.ptt_trigger:
                logging.debug("Triggering PTT")
                self.ptt_trigger()
            elif ptt == False and self.ptt_release:
                logging.debug("Releasing PTT")
                self.ptt_release()
            self.ptt = ptt

        return (bytes(output), pyaudio.paContinue)
    
    def clear(self):
        with self.output_buffer_lock:
            self.buffer = bytearray()
        return
    def close(self):
        self.stream.close()