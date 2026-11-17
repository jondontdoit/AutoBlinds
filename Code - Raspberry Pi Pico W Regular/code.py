from os import getenv

import time
import board
import digitalio
import busio
import microcontroller
from watchdog import WatchDogMode
microcontroller.watchdog.timeout = 8
microcontroller.watchdog.mode = WatchDogMode.RESET

import ipaddress
import wifi
import adafruit_connection_manager
from adafruit_httpserver import Request, Response, Server, MIMETypes

from adafruit_ina219 import ADCResolution, BusVoltageRange, INA219


############################################
# CONSTANTS
############################################
CTRL_ONLINE    = 1
DELAY_VAL      = 0.01
DEBUG_EN       = True

CURR_MAX_UP    = getenv("CIRCUITPY_CURR_MAX_UP")
CURR_MAX_DN    = getenv("CIRCUITPY_CURR_MAX_DN")
CURR_MIN       = getenv("CIRCUITPY_CURR_MIN")

MIN_TRAVEL     = getenv("CIRCUITPY_MIN_TRAVEL")
MAX_TRAVEL_UP  = getenv("CIRCUITPY_MAX_TRAVEL_UP")
MAX_TRAVEL_DN  = getenv("CIRCUITPY_MAX_TRAVEL_DN")

CURR_DELAY     = 0.5
RST_TRAVEL     = 0.2

MTR_DIR_DN     = 0
MTR_DIR_UP     = 1

STATE_IDLE     = 0
STATE_START    = 1
STATE_RUN      = 2
STATE_STOP     = 3


############################################
# INTERNAL VARIABLES
############################################

runState = STATE_IDLE
setMtrDir = MTR_DIR_DN
setMtrTime = 0
runMtrTime = 0

btnUpVal = 0
btnUpLast = 0
btnDnVal = 0
btnDnLast = 0

triggerFullUp = False
triggerFullDown = False

i2c_bus = busio.I2C(board.GP1, board.GP0)
ina219 = INA219(i2c_bus)
delCurrRead = 0


############################################
# SETUP
############################################
PIN_LS = digitalio.DigitalInOut(board.GP22)
PIN_LS.direction = digitalio.Direction.INPUT
PIN_LS.pull = digitalio.Pull.UP

PIN_BTN_UP = digitalio.DigitalInOut(board.GP21)
PIN_BTN_UP.direction = digitalio.Direction.INPUT
PIN_BTN_UP.pull = digitalio.Pull.UP

PIN_BTN_DN = digitalio.DigitalInOut(board.GP20)
PIN_BTN_DN.direction = digitalio.Direction.INPUT
PIN_BTN_DN.pull = digitalio.Pull.UP

PIN_LED = digitalio.DigitalInOut(board.LED)
PIN_LED.direction = digitalio.Direction.OUTPUT

PIN_MTR_UP = digitalio.DigitalInOut(board.GP19)
PIN_MTR_UP.direction = digitalio.Direction.OUTPUT

PIN_MTR_DN = digitalio.DigitalInOut(board.GP18)
PIN_MTR_DN.direction = digitalio.Direction.OUTPUT

##############################################
## WIFI SETTINGS
##############################################
ssid = getenv("CIRCUITPY_WIFI_SSID")
password = getenv("CIRCUITPY_WIFI_PASSWORD")
hostname = getenv("CIRCUITPY_WIFI_HOSTNAME")

# Connect to WiFi
print()
print("Connecting to WiFi")
PIN_LED.value = True

#  connect to your SSID
try:
    wifi.radio.hostname = hostname
    wifi.radio.connect(ssid, password)
except TypeError:
    print("Could not find WiFi info. Check your settings.toml file!")
    raise

print("Connected to WiFi")
PIN_LED.value = not PIN_LED.value

#  prints MAC address to REPL
print("My MAC addr:", [hex(i) for i in wifi.radio.mac_address])

#  prints IP address to REPL
print("My IP address is", wifi.radio.ipv4_address)

#  prints Hostname to REPL
print("My hostname is", wifi.radio.hostname)

PIN_LED.value = not PIN_LED.value
pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
server = Server(pool)
PIN_LED.value = not PIN_LED.value


############################################
# FUNCTIONS
############################################
def setMtr(dirVal, stateVal):
    if dirVal:
        PIN_MTR_UP.value = stateVal
    else:
        PIN_MTR_DN.value = stateVal
    return

def runFullUp():
    # (setMtrDir, setMtrTime, runState)
    return (MTR_DIR_UP, MAX_TRAVEL_UP, STATE_START)

def runFullDown():
    # (setMtrDir, setMtrTime, runState)
    return (MTR_DIR_DN, MAX_TRAVEL_DN, STATE_START)

def webpage():
    html = f"""<!DOCTYPE html>
<html>
  <head>
    <meta http-equiv="Content-type" content="text/html;charset=utf-8">
    <title>AutoBlinds</title>
  </head>
  <body>
    {hostname}
  </body>
</html>
"""
    return html

#  route default static IP
@server.route("/")
def base(request: Request):  # pylint: disable=unused-argument
    return Response(request, f"{webpage()}", content_type="text/html")

@server.route("/fullUp")
def fullUp(request: Request):  # pylint: disable=unused-argument
    global triggerFullUp
    triggerFullUp = True
    return Response(request, f"{webpage()}", content_type="text/html")

@server.route("/fullDown")
def fullDown(request: Request):  # pylint: disable=unused-argument
    global triggerFullDown
    triggerFullDown = True
    return Response(request, f"{webpage()}", content_type="text/html")

server.start(str(wifi.radio.ipv4_address), 80)

############################################
# MAIN
############################################

if DEBUG_EN:
    print("Ready!")

####################
# LOOP
####################
while True:
    microcontroller.watchdog.feed()

    ####################
    # INPUTS
    ####################
    limitSwitchVal = not PIN_LS.value
    current = abs(ina219.current)
    #print((current,))

    btnUpVal = not PIN_BTN_UP.value
    if btnUpVal and not btnUpLast:
        triggerFullUp = True
    btnUpLast = btnUpVal

    btnDnVal = not PIN_BTN_DN.value
    if btnDnVal and not btnDnLast:
        triggerFullDown = True
    btnDnLast = btnDnVal

    try:
        # poll the server for incoming/outgoing requests
        server.poll()
    except Exception as e:
        print(e)
        continue

    ####################
    # TRIGGERS
    ####################
    if triggerFullUp:
        if DEBUG_EN:
            print("Blinds Full Up")
        if runState == STATE_IDLE:
            (setMtrDir, setMtrTime, runState) = runFullUp()
        elif runState == STATE_RUN:
            runMtrTime = time.monotonic()
        triggerFullUp = False

    if triggerFullDown:
        if DEBUG_EN:
            print("Blinds Full Down")
        if runState == STATE_IDLE:
            (setMtrDir, setMtrTime, runState) = runFullDown()
        elif runState == STATE_RUN:
            runMtrTime = time.monotonic()
        triggerFullDown = False

    ####################
    # RUN
    ####################
    if runState == STATE_START:
        if setMtrTime < MIN_TRAVEL:
            setMtrTime = MIN_TRAVEL
        if setMtrDir == MTR_DIR_UP and setMtrTime > MAX_TRAVEL_UP:
            setMtrTime = MAX_TRAVEL_UP
        if setMtrDir == MTR_DIR_DN and setMtrTime > MAX_TRAVEL_DN:
            setMtrTime = MAX_TRAVEL_DN

        setMtr(setMtrDir, True)

        runMtrTime = time.monotonic() + setMtrTime
        delCurrRead = time.monotonic() + CURR_DELAY
        runState = STATE_RUN

        if DEBUG_EN:
            print("Start travel: "+str(time.monotonic()))
            print("  Run time: "+str(runMtrTime))

    if runState == STATE_RUN:
        # Wait some time before measuring current
        if time.monotonic() > delCurrRead:
            #print((current,))
            if setMtrDir == MTR_DIR_UP and current > CURR_MAX_UP:
                runState = STATE_STOP
            if setMtrDir == MTR_DIR_DN and current > CURR_MAX_DN:
                runState = STATE_STOP
            if current < CURR_MIN:
                runState = STATE_STOP
        if time.monotonic() > runMtrTime:
            runState = STATE_STOP

    PIN_LED.value = (runState == STATE_STOP)

    if runState == STATE_STOP:
        setMtr(setMtrDir, False)
        setMtr(not setMtrDir, True)

        time.sleep(RST_TRAVEL)

        setMtr(not setMtrDir, False)

        runState = STATE_IDLE

        if DEBUG_EN:
            print("Stop travel: "+str(time.monotonic()))
            #print("  Run time: "+str(stpMtrTime))


    # Delay
    PIN_LED.value = not PIN_LED.value
    time.sleep(DELAY_VAL)
