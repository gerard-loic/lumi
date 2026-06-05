import os
import re
import sys
import logging
from datetime import datetime
from lib.utils.dict import Dict

#Types de logs avec couleur
ERROR   = "\033[91m"
OK      = "\033[92m"
WARNING = "\033[33m"
INFO    = "\033[0m"
RESET   = "\033[0m"

#Labels correspondants
_TYPE_LABELS = {
    ERROR:   "ERROR",
    OK:      "OK",
    WARNING: "WARNING",
    INFO:    "INFO",
}

#Prefixes en fonction des types de logs
_LOGGER_PREFIXES = {
    'uvicorn':        'UVICORN',
    'uvicorn.access': 'UVICORN',
    'uvicorn.error':  'UVICORN',
    'litellm':        'LITELLM',
    'LiteLLM':        'LITELLM',
}

#Pour le retraitement des logs issus de LiteLLM ou de Uvicorn
_ANSI_RE = re.compile(
    r'\x1b(?:'
    r'\[[0-9;]*[A-Za-z]'                    # CSI : ESC [ ... <lettre>
    r'|\][^\x07\x1b]*(?:\x07|\x1b\\)'       # OSC : ESC ] ... BEL ou ST (hyperliens)
    r'|[^[\]]'                               # séquences 2-chars
    r')'
)

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


"""
_PrefixFormatter — Gestion des prefixes des logs
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class _PrefixFormatter(logging.Formatter):
    def __init__(self, prefix, original=None):
        super().__init__()
        self._prefix = prefix
        self._original = original

    def format(self, record):
        msg = self._original.format(record) if self._original else super().format(record)
        return f"[{self._prefix}] {msg}"

"""
_LogStream — Gestion du flux de logs
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class _LogStream:
    def __init__(self, original, terminal_enabled=True, log_dir=None):
        self._original = original
        self._terminal_enabled = terminal_enabled
        self._log_dir = log_dir
        self._log_file = None
        self._current_date = None
        self._pending = ""

    def _rotate_if_needed(self):
        if self._log_dir is None:
            return
        today = datetime.now().strftime("%Y%m%d")
        if today != self._current_date:
            if self._log_file:
                self._log_file.close()
            self._log_file = open(os.path.join(self._log_dir, f"{today}.log"), 'a', encoding='utf-8', buffering=1)
            self._current_date = today

    def write(self, text, type:str=INFO):
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            plain = (self._stamp(line, type) if line else "") + "\n"
            if self._terminal_enabled:
                colored = (f"{type}{plain.rstrip()}{RESET}\n" if line else "\n")
                self._original.write(colored)
            self._rotate_if_needed()
            if self._log_file:
                self._log_file.write(_strip_ansi(plain))

    def _stamp(self, line, type:str=INFO):
        from lib.http.auth import Auth
        ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        label = _TYPE_LABELS.get(type, "INFO")
        session_id = Auth.getSessionId()
        if session_id:
            return f"[{ts}] [{label}] [#{session_id}] {line}"
        else:
            return f"[{ts}] [{label}] {line}"

    def flush(self):
        if self._terminal_enabled:
            self._original.flush()
        if self._log_file:
            self._log_file.flush()

    def close(self):
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def fileno(self):
        return self._original.fileno()

    def isatty(self):
        return self._original.isatty()

    def __getattr__(self, name):
        return getattr(self._original, name)


"""
Logger — Gestion des logs
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Logger:
    _stdout_stream = None
    _stderr_stream = None
    destinations = {}

    @staticmethod
    def init(configuration={}):
        Logger.destinations = {
            'output': {'enabled': True},
            'file': {'enabled': False, 'path': 'logs'},
        }
        Logger.destinations = Dict.mergeDicts(Logger.destinations, configuration)

        log_dir = None
        if Logger.destinations['file']['enabled']:
            log_dir = Logger.destinations['file'].get('path', 'logs')
            os.makedirs(log_dir, exist_ok=True)

        terminal_enabled = Logger.destinations['output']['enabled']
        Logger._stdout_stream = _LogStream(sys.__stdout__, terminal_enabled=terminal_enabled, log_dir=log_dir)
        Logger._stderr_stream = _LogStream(sys.__stderr__, terminal_enabled=terminal_enabled, log_dir=log_dir)
        sys.stdout = Logger._stdout_stream
        sys.stderr = Logger._stderr_stream
        Logger._patch_logging_handlers()

    @staticmethod
    def _patch_logging_handlers():
        """Redirige les StreamHandlers (uvicorn, LiteLLM…) vers les streams wrappés et ajoute les préfixes source."""
        replacement = {sys.__stdout__: sys.stdout, sys.__stderr__: sys.stderr}
        all_loggers = [logging.root] + list(logging.Logger.manager.loggerDict.values())
        for lgr in all_loggers:
            if not isinstance(lgr, logging.Logger):
                continue
            prefix = _LOGGER_PREFIXES.get(lgr.name)
            for handler in lgr.handlers:
                if not isinstance(handler, logging.StreamHandler):
                    continue
                if handler.stream in replacement:
                    handler.stream = replacement[handler.stream]
                if prefix and not isinstance(handler.formatter, _PrefixFormatter):
                    handler.setFormatter(_PrefixFormatter(prefix, handler.formatter))

    @staticmethod
    def overwriteConfigurationValue(configurationPart):
        Logger.destinations = Dict.mergeDicts(Logger.destinations, configurationPart)

    @staticmethod
    def write(text, type:str=INFO):
        sys.stderr.write(str(text) + "\n", type=type)

    @staticmethod
    def sessionWrite(text, type:str=INFO):
        from lib.http.auth import Auth
        sys.stderr.write(f"#{Auth.getSessionId()} : {text}\n", type=type)

    @staticmethod
    def close():
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        if Logger._stdout_stream:
            Logger._stdout_stream.close()
            Logger._stdout_stream = None
        if Logger._stderr_stream:
            Logger._stderr_stream.close()
            Logger._stderr_stream = None
