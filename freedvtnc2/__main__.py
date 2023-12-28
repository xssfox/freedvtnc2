from .modem import FreeDVRX, FreeDVTX, Modems, Packet
from . import audio
from .shell import FreeDVShell
import logging
import configargparse
from . import tnc
import time
from . import rigctl
import traceback
from prompt_toolkit.formatted_text import HTML, to_formatted_text

logging.basicConfig()

def main():
    p = configargparse.ArgParser(default_config_files=['~/.freedvtnc2.conf'], config_file_parser_class=configargparse.DefaultConfigFileParser)
    p.add('-c', '-config', required=False, is_config_file=True, help='config file path')

    p.add('--no-cli', action='store_true', env_var="FREEDVTNC2_CLI")
    p.add('--list-audio-devices', action='store_true', default=False)

    p.add('--log-level', type=str, default="INFO", env_var="FREEDVTNC2_LOG_LEVEL", choices=logging._nameToLevel.keys())

    p.add('--input-device', type=str, default=None, env_var="FREEDVTNC2_INPUT_DEVICE")
    p.add('--output-device', type=str, default=None, env_var="FREEDVTNC2_OUTPUT_DEVICE")
    p.add('--output-volume', type=float, default=0, env_var="FREEDVTNC2_OUTPUT_DB", help="in db. postive = louder, negative = quiter")

    p.add('--mode', type=str, choices=[x.name for x in Modems], default=Modems.DATAC1.name, help="The TX mode for the modem. The modem will receive all modes at once")
    p.add('--follow', action="store_true", default=False, env_var="FREEDVTNC2_FOLLOW", help="When enabled change TX mode to the mode being received. This is useful for stations operating automatically.")
    p.add('--max-packets-combined', default=5, type=int, env_var="FREEDVTNC2_MAX_PACKETS", help="How many kiss packets to combine into a single transmission")

    p.add('--pts', default=False, action='store_true', env_var="FREEDVTNC2_PTS", help="Disables TCP and instead creates a PTS 'fake serial' interface")
    p.add('--kiss-tcp-port', default=8001, type=int, env_var="FREEDVTNC2_KISS_TCP_PORT")
    p.add('--kiss-tcp-address', default="127.0.0.1", type=str, env_var="FREEDVTNC2_KISS_TCP_ADDRESS")

    p.add('--rigctld-port', type=int, default=4532, env_var="FREEDVTNC2_RIGTCTLD_PORT", help="TCP port for rigctld - set to 0 to disable rigctld support")
    p.add('--rigctld-host', type=str, default="localhost", env_var="FREEDVTNC2_RIGTCTLD_HOST", help="Host for rigctld")
    p.add('--ptt-on-delay-ms', type=int, default=100, env_var="FREEDVTNC2_PTT_ON_DELAY_MS", help="Delay after triggering PTT before sending data")
    p.add('--ptt-off-delay-ms', type=int, default=100, env_var="FREEDVTNC2_PTT_OFF_DELAY_MS", help="Delay after sending data before releasing PTT")

    p.add('--callsign', type=str, env_var="FREEDVTNC2_CALLSIGN", help="Currently only used for chat")
    
    options = p.parse_args()

    logger = logging.getLogger()
    logger.setLevel(level=options.log_level)
    logging.debug("Starting")


    class LogHandler(logging.StreamHandler):
        shell = None
        def __init__(self):
            super().__init__()
            self.log_buffer = ""
        def emit(self, record):
            for message in record.msg.split("\n"):
                if record.name == "root" and record.module == "__main__":
                    msg = HTML(f"<log.{record.levelname.lower()}.msg>{{}}</log.{record.levelname.lower()}.msg>\n").format(message).value
                else:
                    msg = HTML(f"<log.{record.levelname.lower()}.name>{{}}</log.{record.levelname.lower()}.name>").format(record.name).value
                    msg += HTML(f":<log.{record.levelname.lower()}.module>{{}}</log.{record.levelname.lower()}.module>").format(record.module).value
                    msg += HTML(f": <log.{record.levelname.lower()}.msg>{{}}</log.{record.levelname.lower()}.msg>\n").format(message).value

            if options.no_cli:
                print(self.format(record))
            else:
                if not self.shell:
                    print(self.format(record))
                    self.log_buffer += msg
                else:
                    self.shell.add_text(msg)

        

    while logger.hasHandlers(): # remove existing handlers
        logger.removeHandler(logger.handlers[0])
    log_handler = LogHandler()

    kiss_loggers = logging.getLogger('kissfix.classes')

    while kiss_loggers.hasHandlers(): # remove existing handlers
        kiss_loggers.removeHandler(kiss_loggers.handlers[0])

    log_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(module)s: %(message)s"))
    logger.addHandler(log_handler)
    kiss_loggers.addHandler(log_handler)
    
    


    if options.list_audio_devices:
        print(
            audio.devices
        )
    else:
        modem_tx = FreeDVTX(modem=options.mode, max_packets_combined=options.max_packets_combined)
        logging.info(f"Initialised TX FreeDV Modem - version: {modem_tx.modem.version} mode: {modem_tx.modem.modem_name}")
        def tx(data):
            try:
                logging.debug(f"Sending {str(data)}")
                output_device.write(Packet(data))
            except:
                logging.critical(
                    traceback.format_exc()
                )
        
        def progress(total:int, remaining:int, mode:str):
            if not options.no_cli:
                shell.progress(total, remaining, mode)

        def rx(data: Packet):
            logging.debug(f"[{str(data.mode)}] {str(data.header)} / {str(data.data)}")
            try:
                if data.header == 255:
                    tnc_interface.tx(data.data)
                elif data.header == 254: # Chat interface
                    call, message = data.data.split(b"\xff")
                    # this is all hack to make the input line when receiving a message not clobber the input
                    # ignoring debug messages - this is the only place where we have this issues - if we add more threaded output
                    # we should move this into a dedicated function
                    if not options.no_cli: 
                        shell.add_text(
                            HTML("<chat.callsign>&lt;{}&gt;</chat.callsign> <chat.message>{}</chat.message>\n").format(call.decode(), message.decode()).value
                        )
                    else:
                        print(f"\n<{call.decode()}> {message.decode()}")
                
                if options.follow and data.mode != modem_tx.modem.modem_name:
                    logging.info(f"Follow mode active. Switching to {data.mode}")
                    modem_tx.set_mode(modem=data.mode)
            except:
                logging.critical(
                    traceback.format_exc()
                )
                
        if options.pts:
            tnc_interface = tnc.KissInterface(tx)
            logging.info(f"Initialised KISS TNC PTS Interface at {tnc_interface.ttyname}")
        else:
            tnc_interface = tnc.KissTCPInterface(tx, port=options.kiss_tcp_port, address=options.kiss_tcp_address)
            logging.info(f"Initialised KISS TNC TCP Interface at {options.kiss_tcp_address}:{options.kiss_tcp_port}")
        
        

        def inhibit(state):
            if "output_device" in  locals():
                output_device.inhibit = state

        modem_rx = FreeDVRX(callback=rx, progress=progress, inhibit=inhibit)
        for rx_modem in modem_rx.modems:
            logging.info(f"Initialised RX FreeDV Modem - version: {modem_tx.modem.version} mode: {rx_modem.modem_name}")

        input_device_name_or_id = options.input_device
        output_device_name_or_id = options.output_device

        try:
            input_device_name_or_id = int(input_device_name_or_id)
            output_device_name_or_id = int(output_device_name_or_id)
        except:
            pass
        
        if options.rigctld_port != 0:
            rig = rigctl.Rigctld(hostname=options.rigctld_host, port=options.rigctld_port)
            logging.info(f"Initialised Rigctl at {options.rigctld_host}:{options.rigctld_port}")
            ptt_trigger = rig.ptt_enable
            ptt_release = rig.ptt_disable
        else:
            ptt_trigger = None
            ptt_release = None
        
        input_device = audio.InputDevice(modem_rx.write, modem_rx.sample_rate, name_or_id=input_device_name_or_id)
        logging.info(f"Initialised Input Audio: {input_device.device.name}")
        output_device = audio.OutputDevice(
            modem_rx.sample_rate,
            modem = modem_tx,
            name_or_id=output_device_name_or_id,
            ptt_release=ptt_release,
            ptt_trigger=ptt_trigger,
            ptt_on_delay_ms=options.ptt_on_delay_ms,
            ptt_off_delay_ms=options.ptt_off_delay_ms,
            db=options.output_volume
        )
        logging.info(f"Initialised Output Audio: {output_device.device.name}")

        try:
            if not options.no_cli:
                logging.debug(f"Starting shell")
                shell = FreeDVShell(modem_rx, modem_tx
                , output_device, input_device, p, options, log_handler.log_buffer)
                log_handler.shell = shell
                shell.run()
            else:
                while 1:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            log_handler.shell = None
            if "rig" in locals():
                rig.ptt_disable()
            input_device.close()
            output_device.close()
if __name__ == '__main__':
    main()