import json
from pathlib import Path
from lib.config.config import Config
from lib.log.logger import Logger, OK

ENABLED_LANGUAGES = {
    'fr': 'français',
    'en': 'anglais',
    'de': 'allemand',
    'es': 'espagnol',
    'it': 'italien',
    'pt': 'portugais',
    'nl': 'néerlandais',
    'pl': 'polonais',
    'ro': 'roumain',
    'el': 'grec',
    'cs': 'tchèque',
    'sk': 'slovaque',
    'hu': 'hongrois',
    'bg': 'bulgare',
    'hr': 'croate',
    'sr': 'serbe',
    'sl': 'slovène',
    'lt': 'lituanien',
    'lv': 'letton',
    'et': 'estonien',
    'fi': 'finnois',
    'sv': 'suédois',
    'da': 'danois',
    'no': 'norvégien',
    'is': 'islandais',
    'ga': 'irlandais',
    'mt': 'maltais',
    'ru': 'russe',
    'uk': 'ukrainien',
    'be': 'biélorusse',
    'tr': 'turc',
    'ar': 'arabe',
    'he': 'hébreu',
    'fa': 'persan',
    'ur': 'ourdou',
    'hi': 'hindi',
    'bn': 'bengali',
    'pa': 'pendjabi',
    'ta': 'tamoul',
    'te': 'télougou',
    'ml': 'malayalam',
    'mr': 'marathi',
    'gu': 'goujrati',
    'zh': 'chinois',
    'ja': 'japonais',
    'ko': 'coréen',
    'vi': 'vietnamien',
    'th': 'thaï',
    'id': 'indonésien',
    'ms': 'malais',
    'tl': 'tagalog',
    'km': 'khmer',
    'lo': 'lao',
    'my': 'birman',
    'sw': 'swahili',
    'am': 'amharique',
    'ha': 'haoussa',
    'yo': 'yoruba',
    'ig': 'igbo',
    'zu': 'zoulou',
    'af': 'afrikaans',
    'sq': 'albanais',
    'hy': 'arménien',
    'az': 'azéri',
    'ka': 'géorgien',
    'kk': 'kazakh',
    'uz': 'ouzbek',
    'mn': 'mongol',
    'ne': 'népalais',
    'si': 'cinghalais',
    'km': 'khmer',
    'ca': 'catalan',
    'eu': 'basque',
    'gl': 'galicien',
    'cy': 'gallois',
    'gd': 'gaélique écossais',
    'br': 'breton',
    'lb': 'luxembourgeois',
}

"""
Language : Classe de gestion d'une langue
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Language:
    def __init__(self, code:str):
        self._code = code
        self._name = ENABLED_LANGUAGES[code]
        self._translations = {}
        self._loadLanguageFiles()


    def _loadLanguageFiles(self):
        #Chargement des fichiers de language de base
        basePath = Config.get("directories.languages_dir")
        languagePath = Path(f"{basePath}/{self._code}")
        for filePath in languagePath.glob("*.json"):
            self._loadLanguageFile(basePath, filePath.stem)

        #Chargement des fichiers de language surchargés
        basePath = Config.get("directories.custom_languages_dir")
        languagePath = Path(f"{basePath}/{self._code}")
        for filePath in languagePath.glob("*.json"):
            self._loadLanguageFile(basePath, filePath.stem)
            

    def _loadLanguageFile(self, folder:str, fileName:str):
        filePath = Path(f"{folder}/{self._code}/{fileName}.json")
        with filePath.open(encoding="utf-8") as f:
            self._translations.update(json.load(f))

    def getCode(self)->str:
        return self._code

    def getName(self)->str:
        return self._name

    def getTraduction(self, code:str)->str:
        if code in self._translations:
            return self._translations[code]
        return f"[{code}]"


"""
LanguageManager : Gestion du chargement des langues et helpers pour accès aux langues
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class LanguageManager:
    @staticmethod
    def init():
        LanguageManager._languages = {}
        basePath = Config.get("directories.languages_dir")
        for code in ENABLED_LANGUAGES:
            languagePath = Path(f"{basePath}/{code}")
            if languagePath.is_dir():
                LanguageManager._languages[code] = Language(code=code)

        Logger.write(f"[LanguageManager] {len(LanguageManager._languages)} languages loaded", OK)

    @staticmethod
    def languageExists(code:str)->bool:
        if code in LanguageManager._languages:
            return True
        return False

    @staticmethod
    def getLanguage(code:str)->Language:
        if code in LanguageManager._languages:
            return Language(code=code)
        return None