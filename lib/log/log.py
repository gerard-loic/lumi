import sys
from lib.utils.dict import Dict
from datetime import datetime
import os

class Log:
    @staticmethod
    def init(configuration = {}):
        Log.destinations = {
            'output' : {
                'enabled' : True
            },
        }
        Log.destinations = Dict.mergeDicts(Log.destinations, configuration)
        print(Log.destinations)

    @staticmethod
    def overwriteConfigurationValue(configurationPart):
        Log.destinations = Dict.mergeDicts(Log.destinations, configurationPart)
        if Log.destinations['file']['enabled']:
            Log._initFileDestination()

    @staticmethod
    def write(text):
        print(Log.destinations)
        text = str(text)
        if Log.destinations['output']['enabled']:
            Log._writeInOutput(text)

    @staticmethod
    def _writeInOutput(text):
        shortDate = datetime.today().strftime("%d/%m/%Y %H:%M:%S")
        print("#"+shortDate+":"+text)
