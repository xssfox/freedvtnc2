from prompt_toolkit import  Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window, VSplit
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.processors import Transformation, Processor
from prompt_toolkit.layout.dimension import LayoutDimension
from prompt_toolkit.widgets import TextArea, ProgressBar
from prompt_toolkit.document import Document
from prompt_toolkit.styles import Style
from io import StringIO
import re

from prompt_toolkit.formatted_text import HTML, fragment_list_to_text, to_formatted_text
from prompt_toolkit.key_binding.bindings.page_navigation import scroll_page_up, scroll_page_down
import logging
from prompt_toolkit.completion import NestedCompleter
import sys
from . import audio
import readline
import code
import rlcompleter
import pydub.generators
from .modem import Modems, FreeDVRX, FreeDVTX, Packet
import traceback
from pathlib import Path
import argparse
import configargparse


class LogHandler(logging.StreamHandler):
    def __init__(self, callback: callable):
        self.callback = callback
        super().__init__()
    def emit(self, record):
        self.callback(record + "\n")

class FreeDVShellCommands():
    def __init__(self, modem_tx: FreeDVTX, output_device: audio.OutputDevice, parser: configargparse.ArgParser, options:argparse.Namespace):
        self.modem_tx = modem_tx
        self.output_device = output_device
        self.p = parser
        self.options = options

    @property
    def commands(self):
        return [func[3:] for func in dir(self) if func.startswith("do_")]
    
    @property
    def completion(self):
        return {
            func[3:] : getattr(self, f"completion_{func[3:]}")() if hasattr(self, f"completion_{func[3:]}") else None
            for func in dir(self) if func.startswith("do_")
        }

    @property
    def help(self):
        return {
            func[3:] : getattr(self, f"help_{func[3:]}")() if hasattr(self, f"help_{func[3:]}") else getattr(self,func).__doc__ 
            for func in dir(self) if func.startswith("do_")
            }
    
    def do_log_level(self, arg):
        "Set the log level"
        arg=arg.upper()
        if arg not in logging._nameToLevel.keys():
            return f"Must be one of : {','.join(logging._nameToLevel.keys())}"
        logger = logging.getLogger()
        logger.setLevel(level=arg)
        self.options.log_level = arg
        return f"Set log level to {arg}"

    def completion_log_level(self):
        return {
            x : None for x in logging._nameToLevel.keys()
        }

    def do_test_ptt(self, arg):
        "Turns on PTT for 2 seconds"
        sin_wave = pydub.generators.Sine(
            440,
            sample_rate=self.modem_tx.modem.sample_rate,
            bit_depth=16,
            ).to_audio_segment(2000, volume=-6)
        sin_wave.set_channels(1)
        
        self.output_device.write_raw(sin_wave.raw_data)

    def help_mode(self):
        return f"Change TX Mode: mode [{', '.join([x.name for x in Modems])}]"
    
    def do_mode(self, arg):
        if arg == "":
            return f"Current mode: {self.modem_tx.modem.modem_name}"
            
        
        arg = arg.upper()

        if arg not in [x.name for x in Modems]:
            return f"Mode must be {', '.join([x.name for x in Modems])}"
        else:
            self.modem_tx.set_mode(arg)
            self.options.mode = arg
            return f"Set mode {arg}"
    def completion_mode(self):
        return {
            x.name : None for x in Modems
        }

    def do_clear(self, arg):
        "Clears TX queues"
        self.output_device.clear()
        with self.output_device.send_queue_lock:
            self.output_device.send_queue = []
        return "TX buffer cleared"

    def do_list_audio_devices(self, arg):
        "Lists audio device parameters"
        return audio.devices
    
    def do_help(self, arg):
        "This help"
        header = "\nFreeDVTNC2 Help\n---------------\n"
        commands = "\n".join([f"{command}\n   {help_string}" for command, help_string in self.help.items()])
        return header+commands+"\n"

    def do_send_string(self, arg):
        "Sends string over the modem"
        if not arg:
            return "Usage: send_string meow"
        self.output_device.write(Packet(arg.encode()))
        return "Queued for sending"

    def do_volume(self,arg):
        "Set the volume gain in db for output level - you probably want to use soundcard configuration or radio configuration rather than this."
        if arg == "":
            return f"volume: {self.options.output_volume}"
        try: 
            self.output_device.db = float(arg)
            self.options.output_volume = float(arg)
        except ValueError:
            return "Usage is: volume -4.5"
        return f"Set TX volume to {float(arg)} db"
    def do_max_packets_combined(self,arg):
        "Set the max number of packets to combine together for a single transmission"
        if arg == "":
            return f"max_packets_combined: {self.options.max_packets_combined}"
        try: 
            self.modem_tx.max_packets_combined = int(arg)
            self.options.max_packets_combined = int(arg)
        except ValueError:
            return "Usage is: max_packets_combined 5"
        return f"Set max_packets_combined to {int(arg)}"
    
    def do_callsign(self,arg):
        "Sets callsign - example: callsign N0CALL"
        self.options.callsign = arg
        return f"Callsign set to {arg}"
    def do_msg(self, arg):
        "Send a message"

        if not self.options.callsign:
           return "Set callsign with the callsign command first\n"

        data =  self.options.callsign.encode() + b"\xff" + arg.encode()
        self.output_device.write(Packet(data, header=b"\xfe"))
        
    def do_exit(self, arg):
        "Exits FreeDVTNC2"
        raise KeyboardInterrupt
    
    def do_debug(self, arg):
        "Open the debug shell"

        def console_exit():
            raise SystemExit

        variables = globals().copy()
        variables.update(locals())
        
        variables['exit'] = console_exit
        sys.ps1 = "(freedvtnc2)>>> "
        sys.ps2 = "(freedvtnc2)... "

        if 'libedit' in readline.__doc__: # macos hack
            readline.parse_and_bind ("bind ^I rl_complete")
        readline.set_completer(rlcompleter.Completer(variables).complete)
        shell = code.InteractiveConsole(variables)
        try:
            shell.interact(banner="freedvtnc2 debug console")
        except SystemExit:
            pass
    def do_follow(self,arg):
        "Allows the tx modem to change to the mode last received - follow on"
        if arg not in ["on", "off"]:
            return "Usage: follow on or follow off"
        if arg == "on":
            self.options.follow = True
        else:
            self.options.follow = False
        return f"Set follow mode to {arg}"
    def completion_follow(self):
        return {
            "on": None,
            "off": None
        }        
    
    def do_exception(self, arg):
        "Raises and exemption to test the shell"
        raise NotImplementedError("woof\nwoof\n")

    def do_save_config(self, arg):
        "Save a config file to ~/.freedvtnc2.conf. Warning this will override your current config"
        path = str(Path.home() / ".freedvtnc2.conf")
        with open(path, "w") as f: 
            f.write(
                configargparse.DefaultConfigFileParser().serialize({ key.replace("_","-"): str(value) if value != None else "" for key,value in vars(self.options).items() if key != "c"})
            )

        return (f"Saved config to {path}")
    

    
class FormatText(Processor):
    def apply_transformation(self, transformation_input):
        fragments = to_formatted_text(HTML(fragment_list_to_text(transformation_input.fragments)))
        return Transformation(fragments)
class FreeDVShell():
    style = Style(
        [
            ("output-field", "#ffffff"),
            ("status.red", "#ff0000"),
            ("status.green", "#00ff00"),
            ("status.yellow", "#ffff00"),
            ("input-field", "#ffffff bg:#000000"),
            ("line", "#004400"),
            ("progress-bar.used","reverse"),
            ("progress-bar","bg:#bbbbbb"),
            ("log.debug","#757575"),
            ("log.info.name", 'bold'),
            ("log.info.module", 'bold'),
            ("log.warning", 'bold'),
            ("log.warning.name", 'bold #ffff00'),
            ("log.warning.module", 'bold #ffff00'),
            ("log.error.name", 'bold #ff0000'),
            ("log.error.module", 'bold #ff0000'),
            ("log.critical.name", 'bold #ff0000'),
            ("log.critical.module", 'bold #ff0000'),
            ("log.critical.msg", 'bold #ff0000'),
            ("chat.callsign", 'bold #00ff00'),
            ("commandoutput.error", 'bold #ff0000'),
        ]
    )
    def __init__(self, modem_rx: FreeDVRX, modem_tx: FreeDVTX, output_device: audio.OutputDevice, input_device: audio.InputDevice, parser:  configargparse.ArgParser, options: argparse.Namespace, logs:str):
        self.modem_tx = modem_tx
        self.modem_rx = modem_rx
        self.output_device = output_device
        self.input_device = input_device

        self.logger = logging.getLogger()
        self.shell_commands = FreeDVShellCommands(modem_tx, output_device, parser, options)
        self.log_text_area = TextArea(
            text="",
            scrollbar=True,
            line_numbers=False,
            input_processors=[FormatText()]
        )
    
        self.logs = ""
        
        
        self.add_text(logs)


    def add_text(self, text: str):
        self.logs += text
        # out_html += f"<{log[0].replace('class:','')}>{line}</{log[0].replace('class:','')}>"
        self.log_text_area.buffer.document = Document(
            text=self.logs, cursor_position=len(self.logs)
        )



    def progress(self, total:int, remaining:int, mode:str):
        self.pb.percentage = ((total - remaining)/total)*100
        self.pb_text.buffer.document = Document(f" {(total - remaining)}/{total} bytes [{mode}]")
    def run(self):
        
        def accept(buff):
            try:
                input_text = input_field.text.replace("\n","")
                self.add_text(HTML("<userinput>&gt; {}</userinput>\n").format(input_text).value)

                command, arg = input_text.split(" ", 1)
            except ValueError:
                command = input_text
                arg = ""
            additional_class="info"
            try:
                command = getattr(self.shell_commands, "do_" + command)
                try:
                    command_result = command(arg)
                    if command_result:
                        output = str(command_result) + "\n"
                    else:
                        output = ""
                    if command == "debug": # special case the debug shell
                        logging.debug("debug shell")
                except KeyboardInterrupt:
                    raise KeyboardInterrupt
                except:
                    additional_class = "error"
                    output = traceback.format_exc() + "\n"
            except Exception:
                output = "Invalid command. Valid commands: " + ", ".join(self.shell_commands.commands) + "\n"
            if output:
                for line in output.split("\n"):
                    self.add_text(HTML(f"<commandoutput.{additional_class}>{{}}</commandoutput.{additional_class}>\n").format(line).value)
            
        input_field = TextArea(
            height=3,
            prompt="(freedvtnc2) ",
            style="class:input-field",
            multiline=False,
            wrap_lines=False,
            accept_handler=accept,
            completer=NestedCompleter.from_nested_dict(self.shell_commands.completion)
        )


        

        def get_statusbar_text():
                if self.input_device.input_level > -5.0:
                    dbfs_color = "red"
                elif self.input_device.input_level < -90:
                    dbfs_color = "red"
                elif self.input_device.input_level < -50:
                    dbfs_color = "yellow"
                else:
                    dbfs_color = "green"
                statuses = [
                    # input level
                    # ptt status
                    # tx queue (in seconds?)
                    # each modem snr
                ("class:status", f"Input level: "),

                (f"class:status.{dbfs_color}",f"{self.input_device.input_level:6.2f}"),
                ("class:status",f" dBFS | "),

                ("class:status", f"PTT: "),
                (f"class:status.{ 'red' if self.output_device.ptt else 'green' }", f"{ ' on' if self.output_device.ptt else 'off' }"),
                ("class:status", f" | "),

                ("class:status", f"Audio Queue: { (self.output_device.queue_ms / 1000) :5.1f}s | "),
                ("class:status", f"TX Queue: { len(self.output_device.send_queue) :3.0f} | "),
                ("class:status", f"Channel: "),
                (f"class:status.{'red' if self.output_device.inhibit else 'green'}", f"{'busy' if self.output_device.inhibit else 'clear'}"),
                ("class:status", f" | TX Mode: "),
                (f"class:status", f"{self.modem_tx.modem.modem_name}"),
                ("class:status", " |\n"),
                ]

                nl = "\n"
                snrs = [
                    ("class:status", f'{x[1].modem_name}: {x[1].snr:6.2f}db {"|" +nl if x[0] == len(self.modem_rx.modems)-1 else "| "}' ) for x in enumerate(self.modem_rx.modems)
                ]


                syncs = []
                for x in self.modem_rx.modems:
                    syncs.append(("class:status", f"{x.modem_name}: "))
                    syncs.append((f"class:status.{'red' if x.sync == 0 else 'green'}",f"{x.sync:8}"))
                    syncs.append(("class:status",f" | " ))
                    
                
                statuses += snrs
                statuses += syncs
                return statuses
        self.pb =  ProgressBar(

        )
        self.pb_text = TextArea(height=1, width=30,multiline=False,wrap_lines=False,)
        self.pb.percentage = 0

        self.pbsplit = VSplit(
            [
                self.pb,
                self.pb_text 
            ]
        )

        root_container = HSplit([
            Window(
                content=FormattedTextControl(get_statusbar_text),
                height=LayoutDimension.exact(3),
                style="class:status",
            ),
            Window(height=1, char="-", style="class:line"),
            self.log_text_area,
            Window(height=1, char="-", style="class:line"),
            self.pbsplit,
            input_field
        ])

        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("c-q")
        @kb.add("c-d")
        def _(event):
            "Pressing Ctrl-Q or Ctrl-C will exit the user interface."
            raise KeyboardInterrupt
    
        @kb.add("pageup")
        def _(event):
            w = event.app.layout.current_window
            event.app.layout.focus(self.log_text_area)
            scroll_page_up(event)
            event.app.layout.focus(w)

        @kb.add("pagedown")
        def _(event):
            w = event.app.layout.current_window
            event.app.layout.focus(self.log_text_area)
            scroll_page_down(event)
            event.app.layout.focus(w)



        self.app = Application(
             layout=Layout(root_container, focused_element=input_field),
             full_screen=True,
             key_bindings=kb,
             mouse_support=False,
             refresh_interval=0.2,
             style=self.style
             )
        self.app.run()