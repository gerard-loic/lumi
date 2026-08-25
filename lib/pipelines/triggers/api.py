from lib.pipelines.trigger import Trigger, triggerEvent, TRIGGER_API_CALL

class Api(Trigger):
    def __init__(self, config:dict):
        super().__init__(type="Api", config=config)

    def executable(self, event:triggerEvent)->bool:
        if event.getType() == TRIGGER_API_CALL:
            return True
        return super().executable(event)