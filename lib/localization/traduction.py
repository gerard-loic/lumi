import re
from lib.localization.language import Language

class Traduction:
    @staticmethod
    def translate(language:Language, text:str)->str:
        return re.sub(r'\[([\w.]+)\]', lambda m: language.getTraduction(m.group(1)), text)

    def __init__(self, language:Language):
        self._language = language

    def trad(self, text:str):
        return Traduction.translate(language=self._language, text=text)