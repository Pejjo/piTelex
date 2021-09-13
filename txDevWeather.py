#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
Telex Device - Open weather client
"""
__author__      = "Per Johansson"
__email__       = "per@hoj.nu"
__copyright__   = "Copyright 2021, PJ"
__license__     = "GPL3"
__version__     = "0.0.1"

import json
import requests
import datetime

import logging
log = logging.getLogger("piTelex." + __name__)

import txCode
import txBase

#######


class openweather:

  def __init__(self, apikey):
    self.params={}
    self.params['APPID']=apikey
  

  def get_dir(self, degree, lang='en'):
    dirs = {}  
    dirs['en']=['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    dirs['en']=['N', 'NNO', 'NO', 'ONO', 'O', 'OSO', 'SO', 'SSO', 'S', 'SSV', 'SV', 'VSV', 'V', 'VNV', 'NV', 'NNV']

    if not lang in dirs:
      lang='en'
    ix = round(degree / (360. / len(dirs[lang])))
    return dirs[lang][ix % len(dirs[lang])]


  def query(self, city, units='metric', language='en'):
    self.params['q']=city
    self.params['units']=units
    self.params['lang']=language

    try:
      resp = requests.get('http://api.openweathermap.org/data/2.5/forecast', params=self.params, timeout=10, verify=True)
    except requests.exceptions.SSLError as e:
      log.exception("SSL Error")
      response="SSL Error\n"
    except requests.exceptions.ConnectionError as e:
      log.exception("SSL Error")
      response="SSL Error\n"
    except requests.exceptions.Timeout:
      log.exception("API timeout")
      response="API timeout\n"
    else:

      if resp.status_code ==200: 
        try:
          data=resp.json()

          response=""

          if 'city' in data:
             response+="{}, {} Pos: {:4.2f}, {:4.2f}. Sunrise {} Sunset {}\r\n\r\n".format(data['city']['name'], data['city']['country'], data['city']['coord']['lat'], data['city']['coord']['lon'], datetime.datetime.fromtimestamp(data['city']['sunrise']).strftime("%H:%M"), datetime.datetime.fromtimestamp(data['city']['sunset']).strftime("%H:%M"))

             response+="Datum Tid        Temp Fukt Tryck  Vind     Prognos\r\n"
          if 'list' in data:
            for row in data['list'][::2]:
              response+="{:15}  {:4.1f} {:4.1f} {:4.0f}  {:2.0f}/{:<2.0f} {:3} {}\r\n".format( datetime.datetime.fromtimestamp(row['dt']).strftime("%a %m-%d %H:%M"), row['main']['temp'], row['main']['humidity'], row['main']['pressure'], row['wind']['speed'], row['wind']['gust'], self.get_dir(row['wind']['deg'], self.params['lang']), row['weather'][0]['description'])[:66]

        except:
          log.exception("Parsing")
          response='Impossible to parse API response data'

      elif resp.status_code == 400 or resp.status_code not in [401, 404, 502]:
        response="Request error " + payload
      elif resp.status_code == 401:
        response='Invalid API Key provided'
      elif resp.status_code == 404:
        response='Unable to find the resource'
      else:
        response='Unable to contact the upstream server'

    return response+"\r\n"


#######

class TelexWeather(txBase.TelexBase):
    def __init__(self, **params):
        super().__init__()

        self.id = 'Wth'
        self.params = params
        self._units=self.params.get('units')
        self._lang=self.params.get('language')

        # init Eliza
        self._weather = openweather(self.params.get('apikey'))

        self._rx_buffer = []
        self._tx_buffer = []
        self._is_online = False


    def __del__(self):
        #print('__del__ in TelexEliza')
        super().__del__()

    # =====

    def read(self) -> str:
        if self._rx_buffer:
            if self._is_online:
                return self._rx_buffer.pop(0)
            else:
                self._is_online = True
                return '\x1bA'



    def write(self, a:str, source:str):
        if len(a) != 1:
            if a == '\x1bA':
                self._is_online = True
            if a == '\x1bZ':
                self._is_online = False
            if a == '\x1bWB':
                self._is_online = True
                self._rx_buffer.append('\x1bA')
            return

        if a == '\n':
            if self._tx_buffer:
                s = ''.join(self._tx_buffer)
                qry=s.split(',')
                if len(qry)>1:
                  city=qry[0]
                  lang=qry[1]
                else:
                  city=qry[0]
                  lang=self._lang

                log.debug("Query string: " + str(qry))
                print(qry)
                r = self._weather.query(city, units=self._units, language=self._lang)
                r = txCode.BaudotMurrayCode.translate(r)
                r += '\r\n'

                for a in r:
                    self._rx_buffer.append(a)
                self._tx_buffer = []

        elif a == '\r':
            pass
        elif a not in "<>":
            self._tx_buffer.append(a)

#######

if __name__ == "__main__":
    w_client = openweather('413c90682c0ace1a9c8d47eeea062dac')

    print(w_client.query('Västervik', 'metric', 'sv'))

