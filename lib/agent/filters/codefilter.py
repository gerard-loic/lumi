import re
from lib.agent.filters.llmfilter import LLMFilter

"""
CodeFilter — Filtre utilisé en entrée LLM pour filtrer du code éventuellement transmis par le client
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class CodeFilter(LLMFilter):
    _FENCED_BLOCK = re.compile(r'```[\s\S]*?```|~~~[\s\S]*?~~~', re.MULTILINE)
    _INLINE_CODE  = re.compile(r'`[^`\n]+`')
    # Indicateurs forts de code brut (Python et autres langages courants)
    _CODE_LINE    = re.compile(
        r'^[^\S\n]*('
        r'import\s+\w[\w.]*'               # import os / import os.path
        r'|from\s+\w[\w.]*\s+import\b'     # from os import path
        r'|def\s+\w+\s*\('                 # def foo(
        r'|class\s+\w+[\s:(]'              # class Foo: / class Foo(Bar):
        r'|if\s+__name__\s*=='             # if __name__ ==
        r'|@\w[\w.]*\s*$'                  # @decorator
        r'|<\?php\b'                       # PHP
        r'|#include\s*[<"]'               # C/C++
        r').*$',
        re.MULTILINE
    )
    # Appels dangereux — supprime la ligne entière contenant l'appel
    _DANGEROUS_CALL = re.compile(
        r'^[^\n]*\b(exec|eval|__import__|compile)\s*\([^\n]*$'
        r'|^[^\n]*\bos\s*\.\s*system\s*\([^\n]*$'
        r'|^[^\n]*\bsubprocess\s*\.\s*\w+\s*\([^\n]*$'
        r"|^[^\n]*\bopen\s*\([^)\n]*[\"'][wax][\"'][^\n]*$",
        re.MULTILINE
    )

    def __init__(self, configuration = ...):
        super().__init__(configuration)

    def filter(self, text = ""):
        text = super().filter(text)
        text = self._FENCED_BLOCK.sub('', text)
        text = self._INLINE_CODE.sub('', text)
        text = self._CODE_LINE.sub('', text)
        text = self._DANGEROUS_CALL.sub('', text)
        return text.strip()