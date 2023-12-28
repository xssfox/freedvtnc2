from _freedv_cffi import ffi, lib

from typing import Callable
from dataclasses import dataclass
from enum import Enum
import logging

class Modems(Enum):
    """
    Supported modems and friendly names for them
    """
    DATAC1 = lib.FREEDV_MODE_DATAC1
    DATAC3 = lib.FREEDV_MODE_DATAC3
    DATAC4 = lib.FREEDV_MODE_DATAC4

@dataclass
class FreeDVFrame:
    """
    Receive data from the FreeDV modem with meta data
    """
    data: bytes
    sync: int
    snr: float
    modem: Modems

@dataclass
class Packet():
    data: bytes
    header: int|bytes = b"\xff"
    mode: str = None

class Modem():
    def __init__(self, modem: Modems,  callback: Callable[[FreeDVFrame],None]|None=None, max_packets_combined: int = 5):
        self.modem = lib.freedv_open(modem.value)
        self.modem_name = modem.name
        self.buffer = bytearray()
        self.callback = callback
        self.max_packets_combined = max_packets_combined
        # self.stats = ffi.new('struct MODEM_STATS *')

        lib.freedv_set_frames_per_burst(self.modem, 1)

    @property
    def version(self) -> int:
        return lib.freedv_get_version()

    @property
    def nin(self) -> int:
        """
        Number of bytes that the modem is expecting to process (freedv api is number of shorts - we use bytes to make things easier)
        """
        return lib.freedv_nin(self.modem) * ffi.sizeof("short")
    
    @property
    def bytes_per_frame(self) -> int:
        """
        Max number of bytes returned for each frame of audio sent. Used to build buffers.
        """
        return lib.freedv_get_bits_per_modem_frame(self.modem)//8
    
    @property
    def snr(self) -> float:
        """
        Receivers SNR reported by the modem
        """
        sync = ffi.new("int *")
        snr = ffi.new("float *")

        lib.freedv_get_modem_stats(self.modem,sync,snr)

        return snr[0]

    # @property
    # def extendedStats(self):
    #     lib.freedv_get_modem_extended_stats(self.modem, self.stats)
    #     logging.debug(self.stats)
    #     return self.stats


    @property
    def sync(self) -> float:
        """
        Modems sync status.
        """
        sync = ffi.new("int *")
        snr = ffi.new("float *")

        lib.freedv_get_modem_stats(self.modem,sync,snr)

        return sync[0]
    
    @property
    def sample_rate(self) -> int:
        """
        Sample rate the modem is running at
        """
        return lib.freedv_get_modem_sample_rate(self.modem)
    
    def write(self, data: bytes) -> None:
        """
        Feed in audio bytes.
        """
        # add data to our internal buffer
        self.buffer += data

        # if we have enough data run the demodulator
        while (nin := self.nin) <= len(self.buffer):
            # setup the memory location where audio samples will be read from
            to_modem = ffi.from_buffer("short[]", self.buffer[:nin] )
            # remove the loaded samples from the buffer
            del self.buffer[:nin] 
            # setup a location to put the results
            from_modem = ffi.new("unsigned char packed_payload_bits[]", bytes(self.bytes_per_frame))

            # run the demodulator
            bytes_returned = lib.freedv_rawdatarx(self.modem,from_modem,to_modem)

            # check if we get returned bytes
            if bytes_returned and self.callback:
                # if we do, create a freedvframe object and return the data
                self.callback( # we should change this to do depacketization
                    FreeDVFrame(
                        data = bytes(from_modem)[:bytes_returned-2], # Remove the CRC
                        sync = self.sync,
                        snr = self.snr,
                        modem = self.modem_name
                    )
                )
    def crc(self, data: bytes) -> bytes:
        data_in = ffi.from_buffer(f"unsigned char[{self.bytes_per_frame - 2}]", data)
        return lib.freedv_gen_crc16(data_in, self.bytes_per_frame - 2).to_bytes(2, byteorder="big")

    def modulate(self, queue: list[Packet]) -> bytes:
        """
        Modulates bytes into audio samples (also bytes)
        """
        
        """
        Our packet format is. Packet must be less than 32768

        ## TODO build tests for packets exactly the max length
        
        Short packet
        0xff [2 byte short for length of data in bytes] [data]

        Long packet
        [sequence number 0-127] [data]
        """
        
        # Convert to byte array as it will be easier to slice 
        frames = []
        pop_packet_length = self.bytes_per_frame - 2 - 3 # first iteration we use 3 bytes for the header
        frame=bytearray(self.bytes_per_frame)
        used_bytes = 0

        number_combined = 0

        while queue:
            packet = queue.pop(0)
            data = bytearray(packet.data)
            chunks = []
            header_byte = packet.header
            
            while data:
                chunks.append(data[:pop_packet_length])
                del data[:pop_packet_length]
                pop_packet_length = self.bytes_per_frame - 2 - 1 # next iterations only use 1 byte for sequence


            # header
            header = header_byte + sum([len(x) for x in chunks]).to_bytes(2)
            frame[0+used_bytes:3+used_bytes] = header

            chunk = chunks[0]

            # data
            frame[3+used_bytes:3+len(chunk)+used_bytes] = chunk
            used_bytes = used_bytes + len(chunk) + len(header) 


            for header, chunk in enumerate(chunks[1:]):
                used_bytes = 0
                frames.append(frame)
                frame=bytearray(self.bytes_per_frame)
                # header
                header = header.to_bytes(1)
                frame[0:len(header)] = header
            
                frame[1:1+len(chunk)] = chunk
                used_bytes = used_bytes + len(chunk) + len(header) 

            # can we fit a little more data in?
            
            # 2 for crc
            if number_combined > self.max_packets_combined: # limit to 5 packets combined - probably turn this into an option
                if queue:
                    logging.debug("max combined frames reached")
                    frames.append(frame)
                    frame=bytearray(self.bytes_per_frame)
                    used_bytes = 0
                    pop_packet_length = self.bytes_per_frame - 2 - 3
                    number_combined = 0
            if used_bytes + 2 <= self.bytes_per_frame - 3: # we need three bytes to start the next payload
                pop_packet_length = self.bytes_per_frame - used_bytes - 2 - 3
                number_combined += 1
            else:
                if queue:
                    frames.append(frame)
                    frame=bytearray(self.bytes_per_frame)
                    used_bytes = 0
                    pop_packet_length = self.bytes_per_frame - 2 - 3
                    number_combined = 0
        frames.append(frame)

        output = bytes()
        for frame in frames:
            # calculate CRCs
            frame[-2:] = self.crc(bytes(frame)[:-2])
            #logging.debug(f"modulating {str(bytes(frame))}")

            from_modem = ffi.new(f"short mod_out[{lib.freedv_get_n_tx_modem_samples(self.modem)}]")
            
            # preamble
            samples = lib.freedv_rawdatapreambletx(self.modem, from_modem)
            output += ffi.buffer(from_modem)[:(samples*ffi.sizeof("short"))]

            to_modem = ffi.from_buffer("unsigned char *", frame)

            # setup a location to put the results
            lib.freedv_rawdatatx(self.modem, from_modem, to_modem)
            output += ffi.buffer(from_modem)[:]
            
            #postamble
            samples=lib.freedv_rawdatapostambletx(self.modem, from_modem)
            output += ffi.buffer(from_modem)[:(samples*ffi.sizeof("short"))]
        
            
        # add an extra bit of silence to clear out buffers
        output += bytes(lib.freedv_get_n_nom_modem_samples(self.modem)*ffi.sizeof("short")*2)
                
        return output



class FreeDVRX():
    def __init__(self, callback: Callable[[bytes],None], progress: Callable[[int,int],None], inhibit: Callable[[bool],None]):
        self.callback = callback
        self.progress = progress
        self.inhibit = inhibit

        # we RX all the modems at once
        self.modems = [Modem(x, callback=self.rx) for x in Modems]

        # set sample rate so that the audio processor can perform the required sampling conversion
        if len(set([x.sample_rate for x in self.modems])) != 1:
            raise NotImplemented("Not all modems are running the same sample rate - We can't handle this right now")
        else:
            self.sample_rate = self.modems[0].sample_rate

        # data for packet rx
        self.remaining_bytes = None
        self.next_seq_number = None
        self.partial_data = None
        
    def write(self, data: bytes) -> None:
        """
        Accepts bytes of data that will be read by tge modem and demodulated
        """
        sync = False
        for modem in self.modems:
            modem.write(data)
            if modem.sync:
                sync = True
        self.inhibit(sync)

    def rx(self, data_frame: FreeDVFrame):
        logging.debug(f"Received data. snr:{data_frame.snr}")
        data = bytearray(data_frame.data)
        while data:
            #logging.debug(f"Received data: {str(data)}")
            header = data.pop(0)
            if header > 200: # start of packet
                self.remaining_bytes = int.from_bytes(data[0:2])
                self.total_bytes = self.remaining_bytes
                del data[0:2]
                logging.debug(f"Found packet start - Expecting {self.remaining_bytes} bytes")
                self.next_seq_number = 0
                self.partial_data=b''
                self.header = header
            elif self.next_seq_number != None: # should be a seq number
                if self.next_seq_number != header:
                    logging.debug(f"Missing data - header seq expected {self.next_seq_number}, got {header}")
                    logging.debug(f"Full data frame: {str(data_frame.data)}")
                    self.next_seq_number = None
                    self.remaining_bytes = None
                    return
                else:
                    logging.debug(f"Received frame {header}")
                    self.next_seq_number += 1
                    
            else:
                if header != 0:
                    logging.debug(f"Not expecting data - got {header}")
                    logging.debug(f"Full data frame: {str(data_frame.data)}")
                self.next_seq_number = None
                self.remaining_bytes = None
                return
            self.partial_data += data[:self.remaining_bytes]
            received_bytes = len(data[:self.remaining_bytes])
            self.remaining_bytes -= received_bytes

            logging.debug(f"Seq: {header} Remaining data: {self.remaining_bytes}")

            self.progress(self.total_bytes, self.remaining_bytes, data_frame.modem)
            if self.remaining_bytes == 0:
                self.next_seq_number = None
                del data[:received_bytes]
                self.remaining_bytes = None
                self.callback(Packet(header=self.header, data=self.partial_data, mode=data_frame.modem))
            else:
                return


class FreeDVTX():
    def __init__(self, modem: str = Modems.DATAC1.name, max_packets_combined: int = 5):
        self.modem = Modem(modem={x.name:x for x in Modems}[modem])
    def set_mode(self,  modem: str):
        self.modem = Modem(modem={x.name:x for x in Modems}[modem])
    def write(self, data: list[Packet]):
        return self.modem.modulate(data)