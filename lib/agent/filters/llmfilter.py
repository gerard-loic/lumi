import importlib
from lib.config.config import Config
from lib.log.logger import Logger, ERROR

_ALLOWED_FILTERS = {
    "CodeFilter": ("lib.agent.filters.codefilter", "CodeFilter"),
}

class LLMFilter:
    def __init__(self, configuration:dict={}):
        self._configuration = configuration

    def filter(self, text:str=""):
        return text

class LLMFilterManager:
    _filters = []

    @staticmethod
    def init():
        filters = Config.get("llm.filters")
        for filter_name in filters:
            if filter_name in _ALLOWED_FILTERS:
                module_path, class_name = _ALLOWED_FILTERS[filter_name]
                cls = getattr(importlib.import_module(module_path), class_name)
                LLMFilterManager._filters.append(cls(configuration=filters[filter_name]))
            else:
                Logger.write(text=f"LLM filter {filter_name} not allowed !", type=ERROR)
                raise Exception(f"LLM filter {filter_name} not allowed !")

    @staticmethod
    def filter(text:str=""):
        for f in LLMFilterManager._filters:
            text = f.filter(text=text)
        return text