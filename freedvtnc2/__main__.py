from .modem import FreeDVRX, FreeDVTX, Modems, Packet
from . import audio
from .shell import FreeDVShell
import logging
import configargparse
from . import tnc
import time
from . import rigctl
import readline
import sys,struct,fcntl,termios
import traceback
logging.basicConfig()

if __name__ == '__main__':
    p = configargparse.ArgParser(default_config_files=['/etc/freedvtnc2.conf', '~/.freedvtnc2.conf'])
    p.add('-c', '-config', required=False, is_config_file=True, help='config file path')

    p.add('--no-cli', action='store_true', env_var="FREEDVTNC2_CLI")
    p.add('--list-audio-devices', action='store_true', default=False)

    p.add('--log-level', type=str, default="INFO", env_var="FREEDVTNC2_LOG_LEVEL", choices=logging._nameToLevel.keys())

    p.add('--input-device', type=str, default=None, env_var="FREEDVTNC2_INPUT_DEVICE")
    p.add('--output-device', type=str, default=None, env_var="FREEDVTNC2_OUTPUT_DEVICE")
    p.add('--output-volume', type=float, default=0, env_var="FREEDVTNC2_OUTPUT_DB", help="in db. postive = louder, negative = quiter")

    p.add('--mode', type=str, choices=[x.name for x in Modems], default=Modems.DATAC1.name, help="The TX mode for the modem. The modem will receive all modes at once")
    p.add('--follow', action="store_true", default=False, env_var="FREEDVTNC2_FOLLOW", help="When enabled change TX mode to the mode being received. This is useful for stations operating automatically.")

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

    if options.list_audio_devices:
        print(
            audio.devices
        )
    else:
        modem_tx = FreeDVTX(modem=options.mode)

        def tx(data):
            try:
                logging.debug(f"Sending {str(data)}")
                output_device.write(modem_tx.write(data))
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
                        shell.add_text(f"<{call.decode()}> {message.decode()}\n")
                    else:
                        print(f"\n<{call.decode()}> {message.decode()}")
                
                if options.follow and data.mode != modem_tx.modem.modem_name:
                    logging.info(f"Switching to {data.mode}")
                    modem_tx.set_mode(modem=data.mode)
            except:
                logging.critical(
                    traceback.format_exc()
                )
                
        if options.pts:
            tnc_interface = tnc.KissInterface(tx)
        else:
            tnc_interface = tnc.KissTCPInterface(tx, port=options.kiss_tcp_port, address=options.kiss_tcp_address)
            
        def inhibit(state):
            output_device.inhibit = state

        modem_rx = FreeDVRX(callback=rx, progress=progress, inhibit=inhibit)

        input_device_name_or_id = options.input_device
        output_device_name_or_id = options.output_device

        try:
            input_device_name_or_id = int(input_device_name_or_id)
            output_device_name_or_id = int(output_device_name_or_id)
        except:
            pass
        
        if options.rigctld_port != 0:
            rig = rigctl.Rigctld(hostname=options.rigctld_host, port=options.rigctld_port)
            ptt_trigger = rig.ptt_enable
            ptt_release = rig.ptt_disable
        else:
            ptt_trigger = None
            ptt_release = None
        
        input_device = audio.InputDevice(modem_rx.write, modem_rx.sample_rate, name_or_id=input_device_name_or_id)
        output_device = audio.OutputDevice(
            modem_rx.sample_rate,
            name_or_id=output_device_name_or_id,
            ptt_release=ptt_release,
            ptt_trigger=ptt_trigger,
            ptt_on_delay_ms=options.ptt_on_delay_ms,
            ptt_off_delay_ms=options.ptt_off_delay_ms,
            db=options.output_volume
        )

        try:
            if not options.no_cli:
                shell = FreeDVShell(modem_rx, modem_tx, output_device, input_device)
                if options.callsign:
                    shell.shell_commands.callsign = options.callsign
                shell.run()
            else:
                while 1:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            input_device.close()
            output_device.close()