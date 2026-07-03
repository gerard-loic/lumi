from datetime import datetime

from lib.log.logger import Logger, INFO, ERROR, OK

class CronTask():
    def __init__(self, className:str, config:dict):
        self.className = className

        if "time" not in config:
            self.exception(text="key 'time' not defined in config")
        if "config" not in config:
            self.exception(text="key 'config' not defined in config")
        self.config = config['config']
        self.time = config['time']
        self.log(text="Initialization")
    
    def log(self, text, type=INFO):
        Logger.write(f"[CronTask {self.className}] {str(text)}", type)

    def exception(self, text):
        Logger.write(f"[CronTask {self.className}] {str(text)}", ERROR)
        raise Exception(f"[CronTask {self.className}] {str(text)}")

    def run(self):
        self.log(text="Run", type=OK)

    def testExecution(self, timestamp:int) -> bool:
        dt = datetime.fromtimestamp(timestamp)
        return self._matchField(field="minute", value=dt.minute) and self._matchField(field="heure", value=dt.hour)

    def _matchField(self, field:str, value:int) -> bool:
        if field not in self.time:
            return True

        rule = self.time[field]
        if rule == "*":
            return True
        if isinstance(rule, str) and rule.startswith("/"):
            return value % int(rule[1:]) == 0
        return int(rule) == value
        