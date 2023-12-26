import logging
import cmd
from .modem import Modems, lib, ffi
import readline
import rlcompleter
import code
import sys
import time
from . import audio

import pydub.generators

class FreeDVShell(cmd.Cmd):
    intro = "FreeDVTNC2 Shell - type help or ? to list commands\n"
    prompt = "(freedvtnc2) "
    callsign = None

    def do_log_level(self, arg):
        "Set the log level"
        logger = logging.getLogger()
        logger.setLevel(level=arg.upper())

    def do_test_ptt(self, arg):
        "Turns on PTT for 2 seconds"
        print("Starting TX")
        sin_wave = pydub.generators.Sine(
            440,
            sample_rate=self.modem_tx.modem.sample_rate,
            bit_depth=16,
            ).to_audio_segment(2000)
        sin_wave.set_channels(1)
        self.output_device.write(sin_wave.raw_data)
        print("Stopping TX")

    def do_mode(self, arg):
        arg = arg.upper()
        if arg not in [x.name for x in Modems]:
            print(f"Mode must be {', '.join([x.name for x in Modems])}")
        else:
            modem = {x.name:x for x in Modems}[arg]
            self.modem_rx.set_mode(modem)
            self.modem_tx.set_mode(modem)
        print(f"Set mode {arg}")

    def help_mode(self):
        print(f"Change TX Mode: mode [{', '.join([x.name for x in Modems])}]")

    def do_clear(self, arg):
        "Clears TX queues"
        self.output_device.clear()
        print("TX buffer cleared")

    def do_list_audio_devices(self, arg):
        "Lists audio device parameters"
        print(audio.devices)

    def do_send_string(self, arg):
        "Sends string over the modem"

        self.output_device.write(self.modem_tx.write(arg.encode()))

    def do_msg(self, arg):
        "Send a message"

        if not self.callsign:
            self.callsign = input("Your callsign:")

        data = self.callsign.encode() + b"\xff" + arg.encode()

        self.output_device.write(self.modem_tx.write(data, header_byte=b"\xfe"))
        
    def do_debug(self, arg):
        "Open the debug shell"

        def console_exit():
            raise SystemExit

        variables = globals().copy()
        variables.update(locals())
        
        variables['exit'] = console_exit
        sys.ps1 = "(freedvtnc2)>>> "
        sys.ps2 = "(freedvtnc2)... "

        readline.set_completer(rlcompleter.Completer(variables).complete)
        shell = code.InteractiveConsole(variables)
        try:
            shell.interact(banner="freedvtnc2 debug console")
        except SystemExit:
            pass
    def emptyline(self):
        pass