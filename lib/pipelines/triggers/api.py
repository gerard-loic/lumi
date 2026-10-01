from lib.pipelines.triggerevent import TriggerEvent, TRIGGER_API_CALL
from lib.pipelines._abstract import Trigger

class Api(Trigger):
    def __init__(self, config:dict):
        super().__init__(type="Api", config=config)

    def executable(self, event:TriggerEvent)->bool:
        if event.getType() == TRIGGER_API_CALL:
            return True
        return super().executable(event)