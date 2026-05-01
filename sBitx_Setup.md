# sBitx Setup 

## Determine Audio Device

* first determine the audio devices for input and output; bash `freedvtnc2 --list-audio-devices` in an sBitx terminal

- Should print something like this at the end
```
Id  Name                      In    Out    SampleRate
0  Loopback: PCM (hw:1,0)    32     32         44100
1  Loopback: PCM (hw:1,1)     2     32         48000
2  Loopback: PCM (hw:2,0)    32      2         48000
3  Loopback: PCM (hw:2,1)    32     32         44100
4  Loopback: PCM (hw:3,0)    32     32         44100
5  Loopback: PCM (hw:3,1)    32     32         44100
6  pipewire                  64     64         44100
7  pulse                     32     32         44100
8  default                   64     64         44100
```

- On the machine above the Input device is the one that shows `2` under `In` and the output shows `2` under `Out`
- The Id numbers are used  to call the device 
- To use Loopback: PCM (hw:1,1) as the input device as a command line option `--input-device 1`
- For config files `input-device =1` no spaces after `=`

## Run from Command Line 
1. To start the application by specifying the options from command line, 
```bash
freedvtnc2 --input-device 1 --output-device 2 --callsign NOCALL --mode DATAC4
```
replacing `1` and `2` with the devices you found above on your machine.

## Run from config file
1. Check for config file, in the sBitx terminal bash `nano .freedvtnc2.conf` If the file is blank exit nano `ctrl + x`

- bash `freedvtnc2` to start the application
- In the application command line type `save_config` This wiil auto generate a nearly working config file. freedvtnc2 will not be able to start from this config, you will get an error that the audio device cannot be found
- sBtix terminal again bash `nano .freedvtnc2` to open the config file. It will look something like this
```
no-cli = False
list-audio-devices = False
log-level = INFO
input-device = 
output-device = 
output-volume = 0.0
mode = DATAC4
follow = False
max-packets-combined = 5
pts = False
kiss-tcp-port = 8001
kiss-tcp-address = 127.0.0.1
rigctld-port = 4532
rigctld-host = localhost
ptt-on-delay-ms = 100
ptt-off-delay-ms = 100
callsign = 
```
- Scroll down to `input-device =` and add the audio device Id right next to the `=`, no spaces.
- Repeat for `output-device =`
- It should look like this, again no spaces after the =
```
input-device =1
output-device =2
``` 
- Change mode and add callsign if desired (this can be done inside the app as well)