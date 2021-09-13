#!/usr/bin/python3

"""
Fernschreiber Krisinformation client


"""
__author__ = "Per Johansson"
__email__ = "per@hoj.nu"
__copyright__ = "tbd"
__license__ = "tbd"
__version__ = "0.0.1"


import threading
import time
import datetime
import queue
from urllib.request import urlopen
import json
import textwrap
import txDevITelexCommon
import txCode
import html2text
import log
import logging

logging.basicConfig(level=logging.WARN)
logger = logging.getLogger(__name__)

def LOG(text:str, level:int=3):
    log.LOG('\033[5;30;46m<'+text+'>\033[0m', level)


class TelexMSB(txDevITelexCommon.TelexITelexCommon):
    def __init__(self, **params):
        super().__init__()
        self.id = 'MSB'
        self.running = True
        self._rx_buffer = []
        self._is_online = False
        self.msb_client = MSB_Client(params.get("poll_interval", 600), params.get("country_filter", ""), params.get("county_filter", ""), params.get("municipality_filter", ""), params.get("url",""))
        self.thread = threading.Thread(target=self.thread_function, name='MSB_Handler')
        self.thread.start()


    def exit(self):
        self.msb_client.stop()
        self.running = False
        self.thread.join()

    # =====

    def read(self) -> str:
    # To server
        if self._rx_buffer:
            if self._is_online:
                return self._rx_buffer.pop(0)
            else:
                self._is_online = True
                return '\x1bA'


    def write(self, a: str, source: str):
        if len(a) != 1:
            if a == '\x1bA':
                self._is_online = True
            if a == '\x1bZ':
                self._is_online = False
            if a == '\x1bWB':
                self._is_online = True
#                self._rx_buffer.append('\x1bA')
            return

        if a not in "<>":
            self._tx_buffer.append(a)

    # =====

    def thread_function(self):
        """
            Twitter client handler
        """
        last_date = None
        while self.running:
            try:
                data = self.msb_client.get_msg()
                if data is not None:
                    text = '\r\n'+txCode.BaudotMurrayCode.translate(data)+'\r\n\n\n'

                        # TODO: insert linebreak after 65 characters
                    for a in text:
                        self._rx_buffer.append(a)

                if self._tx_buffer:
                    self._tx_buffer.pop(0)
            except Exception as e:
               LOG(str(e),1)

        LOG('end connection', 2)
        self._connected = False


#######
class MSB_Client():

   def __init__(self, days, countries, counties, municipalities, host):
        self.url = host+'?days='+str(days)
        self.countries=countries.split(',')
        self.counties=counties.split(',')
        self.municipalities=municipalities.split(',')
        self.lastid=16176
        self.q = queue.Queue()

        self.running = True
        self.thread = threading.Thread(target=self.thread_function, name='MSB_Client')
        self.thread.start()

   def stop(self, quit_msg='Wah!'):
        self.running = False
        self.thread.join()
        #self.api.close()

        del self

   def get_msg(self):
        if self.q.empty():
            return None
        return self.q.get()

   def thread_function(self):
        timer=0

        while self.running:
           try:
               if timer==0:
                   timer=60*60
                   # store the response of URL
                   response = urlopen(self.url)
  
                   # storing the JSON response 
                   # from url in data
                   data_json = json.loads(response.read())
  
                   # print the json response
                   for itm in data_json:
                       addMe=False
                       place=""
                       if 'Area' in itm:
                           for area in itm['Area']:
                               if area['Type']=='Country' and area['Description'] in self.countries:
                                   addMe=True
                                   place=area['Description']
                                   pass
                               if area['Type']=='County':
                                   if area['Description'] in self.counties:
                                       addMe=True
                                       place=place + " " + area['Description']
                                       pass
                                   else:
                                       addMe=False
                               if area['Type']=='Municipality':
                                   if area['Description'] in self.municipalities:
                                       addMe=True
                                       place=place + " " + area['Description']
                                   else:
                                       addMe=False
                       if addMe:
                           if int(itm['Identifier'])>self.lastid:
                               self.lastid=int(itm['Identifier'])
                               message=itm['Updated'].rstrip()+'\n'
                               message=message+html2text.html2text(itm['Headline']).rstrip()+'\n\n'
                               wrapper = textwrap.TextWrapper(initial_indent="  ", subsequent_indent="  ", width=64)
                               message=message+wrapper.fill(html2text.html2text(itm['BodyText'])).rstrip()+'\n\n\n'
                               print(self.lastid)

                               self.q.put(message.replace('\n', '\r\n'))
               else:
                   timer-=1
#               self.idl = [ str(self.api.get_user(screen_name=u).id) for u in self.follow ]
#               self.listener = Twitter_Client.UserStreamListener(self)
#               self.stream = tweepy.Stream(auth=self.api.auth, listener=self.listener)
#               self.stream.filter(follow=self.idl, track=self.track)

#          self.client.q.put(status)

#          self.client.q.put(data)

               time.sleep(1)
           except Exception as e:
              LOG(str(e), 1)

if __name__ == "__main__":
    twitter_client = MSB_Client(180, 'Sverige','Kalmar län',',Västervik','http://api.krisinformation.se/v3/news')
#    thread = threading.Thread(target=self.thread_function, name='MSB_Handle')

#    thread.start()
    while True:
       msg=twitter_client.get_msg()
       if msg:
           print(msg)
       time.sleep(1)
