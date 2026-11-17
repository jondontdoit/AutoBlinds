#!/usr/bin/env python

import logging
from datetime import datetime
import time
from dateutil import tz
import suntime
import urllib.request
from socket import timeout
from flask import Flask, jsonify, render_template, request, redirect, url_for
import threading

log_file = 'autoblinds.log'

controllerIP = "11.22.333.100"
controllerList = {}
controllerList['A'] = "11.22.333.101" # AutoBlind-A
controllerList['B'] = "11.22.333.102" # AutoBlind-B
controllerList['C'] = "11.22.333.103" # AutoBlind-C
controllerList['D'] = "11.22.333.104" # AutoBlind-D

sBrightness = 0
sBrightnessMax = 19082
wBrightness = 0
wBrightnessMax = 2483131393

sun = suntime.Sun(43.67, -79.36)  # Toronto
sunriseTime = 0
middayTime = 0
preSunsetTime = 0
sunsetTime = 0

nowTime = 0
dnTime = {}
upTime = {}
lsFlag = {}
dnFlag = {}
dnFlag['A'] = False
dnFlag['B'] = False
dnFlag['C'] = False
dnFlag['D'] = False
message = ''

logging.basicConfig(filename=log_file, encoding='utf-8', level=logging.DEBUG)

#########################
# TIMER THREAD
#########################

def map_values(x, in_min, in_max, out_min, out_max):
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def dump_log():
  log_out  = "It's now:   "+str(nowTime)+"\n"
  log_out += "Sunrise:     "+str(sunriseTime)+"\n"
  log_out += "Midday:     "+str(middayTime)+"\n"
  log_out += "PreSunset:  "+str(preSunsetTime)+"\n"
  log_out += "Sunset:     "+str(sunsetTime)+"\n"
  log_out += "S Bright:   "+str(sBrightness)+"\n"
  log_out += "W Bright:   "+str(wBrightness)+"\n"
  print(log_out)
  logging.info(log_out)

def threadTimer():
  """thread worker function"""
  global sun
  global controllerList
  global nowTime
  global dnTime, upTime
  global dnFlag
  global sBrightness, sBrightnessMax
  global wBrightness, wBrightnessMax

  nowTimeLast = 0

  print("AutoBlinds Timer Ready!")
  logging.info("AutoBlinds Timer Ready!")

  # LOOP
  while True:

    now = datetime.now()
    nowTime = (now.hour * 100) + now.minute

    if nowTime != nowTimeLast:
    
      # Grab sensor data every 10 mins
      if nowTimeLast == 0 or nowTime % 10 == 0:

        # Grab south light sensor
        sBrightnessRaw = 0
        try:
          sBrightnessRaw = int(int(urllib.request.urlopen('http://'+controllerList['B'], timeout=10).read().decode('utf-8')))
          sBrightness = map_values(sBrightnessRaw, 0, sBrightnessMax, 0, 1000)
          sBrightness = int(sBrightness)
        except:
          pass
        logging.info("S Brightness: "+str(sBrightnessRaw))
        if sBrightnessRaw > sBrightnessMax:
          sBrightnessMax = sBrightnessRaw
          print("S Brightness Max: "+str(sBrightnessMax))
          logging.info("S Brightness Max: "+str(sBrightnessMax))

        # Grab west light sensor
        wBrightnessRaw = 0
        try:
          wBrightnessRaw = int(int(urllib.request.urlopen('http://'+controllerList['D'], timeout=10).read().decode('utf-8')))
          wBrightness = map_values(wBrightnessRaw, 65540, wBrightnessMax, 0, 1000)
          wBrightness = int(wBrightness)
        except:
          pass
        logging.info("W Brightness: "+str(wBrightnessRaw))
        if wBrightnessRaw > wBrightnessMax:
          wBrightnessMax = wBrightnessRaw
          print("W Brightness Max: "+str(wBrightnessMax))
          logging.info("W Brightness Max: "+str(wBrightnessMax))
          
        dump_log()

      # Log weather brightness online every hour
      if nowTimeLast == 0 or nowTime % 100 == 0:
        try:
          url = 'https://dev.jhwarren.com/light/capture.php?amb='+str(sBrightness)+'&lux='+str(wBrightness)
          urllib.request.urlopen(url, timeout=10).read()
        except:
          pass

      # Update sunrise/sunset time at boot and daily at midnight
      if nowTimeLast == 0:
        # Fetch and process timing
        sunrise = sun.get_sunrise_time(now, tz.gettz('America/Toronto'))
        sunriseTime = int(sunrise.strftime('%H%M'))

        sunset = sun.get_sunset_time(now, tz.gettz('America/Toronto'))
        sunsetTime = int(sunset.strftime('%H%M'))

        middayTime = int((sunriseTime + sunsetTime) / 2)
        if middayTime % 100 > 59:
          middayTime += 100
          middayTime -= 60

        # DOWN - 1 hour after sunrise
        postSunriseTime = sunriseTime + 100

        # UP - 30 mins before sunset
        preSunsetTime = sunsetTime
        if preSunsetTime % 100 < 30:
          preSunsetTime -= 100
          preSunsetTime += 30
        else:
          preSunsetTime -= 30

        # Use Brightness sensors to lower blinds?
        enableBrightnessSensor = True
        
        # During the Spring & Summer (July/Aug)
        if False:
          dnTime['A'] = postSunriseTime
          dnTime['B'] = postSunriseTime
          dnTime['C'] = middayTime - 200    # 2h before midday
          dnTime['D'] = middayTime - 200    # 2h before midday

          upTime['A'] = middayTime + 200    # 2h after midday
          upTime['B'] = middayTime + 400    # 4h after midday
          upTime['C'] = sunsetTime
          upTime['D'] = preSunsetTime

        # During the Early Fall (Sept/Oct)
        if True:
          dnTime['A'] = postSunriseTime
          dnTime['B'] = postSunriseTime
          dnTime['C'] = middayTime - 100    # 1h before midday
          dnTime['D'] = middayTime - 100    # 1h before midday

          upTime['A'] = middayTime + 100    # 1h after midday
          upTime['B'] = middayTime + 200    # 2h after midday
          upTime['C'] = preSunsetTime
          upTime['D'] = sunsetTime

        # During the Fall & Winter (Oct/Nov)
        if False:
          dnTime['A'] = postSunriseTime
          dnTime['B'] = postSunriseTime
          dnTime['C'] = middayTime          # At midday
          dnTime['D'] = middayTime          # At midday
          
          upTime['A'] = middayTime + 100    # 1h after midday
          upTime['B'] = middayTime + 200    # 2h after midday
          upTime['C'] = sunsetTime
          upTime['D'] = preSunsetTime

        # During the Winter Proper (Jan/Feb)
        if False:
          enableBrightnessSensor = False
          dnTime['A'] = 0					# Midnight
          dnTime['B'] = 0
          dnTime['C'] = 0
          dnTime['D'] = 0
          
          upTime['A'] = sunriseTime    		# Sunrise
          upTime['B'] = sunriseTime
          upTime['C'] = sunriseTime
          upTime['D'] = preSunsetTime

        dump_log()

      # See if it's time to move the blinds up or down
      if True:

        # Set flags if it's too dark to lower blinds but if the sensor is dead follow the schedule
        lsFlag['A'] = ((sBrightness > 300) or (sBrightness < 1) or not enableBrightnessSensor)
        lsFlag['B'] = ((sBrightness > 300) or (sBrightness < 1) or not enableBrightnessSensor)
        lsFlag['C'] = ((wBrightness > 250) or (wBrightness < 1) or not enableBrightnessSensor)
        lsFlag['D'] = ((wBrightness > 250) or (wBrightness < 1) or not enableBrightnessSensor)

        for key in dnTime.keys():
          if nowTime == dnTime[key]:
            dnFlag[key] = True
          if dnFlag[key] and lsFlag[key]:
            print("Scheduled Blinds DOWN for "+key)
            logging.info("Scheduled Blinds DOWN for "+key)
            try:
              urllib.request.urlopen("http://"+controllerList[key]+"/fullDown", timeout=10).read()
            except:
              pass
            dnFlag[key] = False
        for key in upTime.keys():
          if nowTime == upTime[key]: # or nowTime == sunsetTime:
            print("Scheduled Blinds UP for "+key)
            logging.info("Scheduled Blinds UP for "+key)
            try:
              urllib.request.urlopen("http://"+controllerList[key]+"/fullUp", timeout=10).read()
            except:
              pass
            dnFlag[key] = False

      nowTimeLast = nowTime

    time.sleep(5)
  return

t = threading.Thread(name='threadTimer', target=threadTimer)
t.start()


#########################
# FLASK (WEB) FUNCTIONS
#########################
app = Flask(__name__)

@app.route('/')
def home():
  global nowTime
  global dnTime
  global upTime
  global message
  global sBrightness
  global wBrightness

  return render_template('autoblinds.html', val_message=message, val_now=nowTime, val_s_brightness=sBrightness, val_w_brightness=wBrightness,  \
  val_up_a=upTime['A'], val_dn_a=dnTime['A'], \
  val_up_b=upTime['B'], val_dn_b=dnTime['B'], \
  val_up_c=upTime['C'], val_dn_c=dnTime['C'], \
  val_up_d=upTime['D'], val_dn_d=dnTime['D'], \
  val_ip=controllerIP, \
  val_ip_a=controllerList['A'], \
  val_ip_b=controllerList['B'], \
  val_ip_c=controllerList['C'], \
  val_ip_d=controllerList['D'])


@app.route('/data')
def data():
  global controllerList
  global nowTime
  global message
  global sBrightness, wBrightness
  global upTime, dnTime
  global lsFlag, dnFlag

  json_output = {}
  json_output['controllerList'] = controllerList
  json_output['nowTime'] = nowTime
  json_output['message'] = message
  json_output['sBrightness'] = sBrightness
  json_output['wBrightness'] = wBrightness
  json_output['upTime'] = upTime
  json_output['dnTime'] = dnTime
  json_output['lsFlag'] = lsFlag
  json_output['dnFlag'] = dnFlag

  return jsonify(json_output)

if __name__ == '__main__':
	app.run(debug=False, host='0.0.0.0', port=80)