import os
import re
from pathlib import Path

from lib.files.filestore import FileStore

#filesource : résolution de la valeur "source" des blocs qui manipulent un fichier (TxtReader,
#CsvReader, ExcelReader, FileDelete, FileMove). Réside dans lib/pipelines/utils pour être partagé
#par ces blocs sans les coupler.
#
#Une "source" peut être :
#  - un chemin de fichier sur le serveur (str), éventuellement templatisé : "/data/{jour}/export.csv" ;
#  - une référence de contexte réduite à un seul jeton "{var}" pointant vers :
#       * un dict de fichier de pipeline {"key"/"url"/"path", "filename", ...} (sortie d'un bloc
#         DataViewFile, ou entrée de la liste produite par un bloc Agent) ;
#       * une liste de tels dicts (resolve_file_source / resolve_file_ref -> 1er élément ;
#         resolve_file_refs -> tous les éléments) ;
#       * une chaine (URL "/files/...", clé FileStore hexadécimale, ou chemin serveur) ;
#  - un dict {"key"/"url"/"path", "filename"} fourni directement dans la config ;
#  - une URL "/files/<key>/<filename>" ou une clé FileStore (32 hexa) désignant un fichier
#    rattaché au run courant (ou à la session).
#
#  - resolve_file_source(...) -> (contenu_octets, nom_de_fichier) : pour lire le contenu.
#  - resolve_file_ref(...)    -> FileRef                          : pour agir sur le fichier lui-même.
#  - resolve_file_refs(...)   -> list[FileRef]                    : idem, en développant les listes.
#
#Toutes lèvent FileSourceError en cas de source invalide ou introuvable.

_SINGLE_TOKEN_RE = re.compile(r'^\s*\{([\w\.\[\]]+)\}\s*$')
_HEX_KEY_RE = re.compile(r'^[0-9a-f]{32}$')


class FileSourceError(Exception):
    pass


#Descripteur d'un fichier résolu, sans en charger le contenu :
#  - path : chemin sur disque du fichier réel (pour une clé FileStore : FileStore.path(key)) ;
#  - filename : nom lisible avec extension (déduction de format, nommage d'une sortie) ;
#  - key : clé FileStore si le fichier est rattaché au run / à la session, sinon None.
class FileRef:
    __slots__ = ("path", "filename", "key")

    def __init__(self, path:str, filename:str=None, key:str=None):
        self.path = str(path) if path else None
        self.filename = filename or (os.path.basename(self.path) if self.path else None) or "file"
        self.key = key

    @property
    def is_filestore(self)->bool:
        return self.key is not None

    def exists(self)->bool:
        return bool(self.path) and Path(self.path).is_file()

    #Contenu du fichier. Pour une clé FileStore, l'accès passe d'abord par FileStore.load (scope du
    #run / de la session) ; si le fichier existe sur disque mais hors scope, on le relit directement.
    def read(self)->bytes:
        if self.key is not None:
            try:
                return FileStore.load(self.key)
            except ValueError as e:
                if not self.exists():
                    raise FileSourceError(str(e))
        if self.exists():
            return Path(self.path).read_bytes()
        raise FileSourceError(f"Fichier introuvable : {self.path or self.filename}")


def resolve_file_source(raw_source, context, hint_name:str=None):
    ref = resolve_file_ref(raw_source, context, hint_name)
    return ref.read(), ref.filename


def resolve_file_ref(raw_source, context, hint_name:str=None)->FileRef:
    if isinstance(raw_source, dict):
        return _ref_from_struct(raw_source, hint_name)

    if not isinstance(raw_source, str) or raw_source.strip() == "":
        raise FileSourceError("'source' manquant ou invalide")

    #Entrée réduite à un seul jeton "{var}" : on résout la structure sous-jacente (dict / liste de
    #fichiers) plutôt que de la laisser sérialiser en chaine par le moteur de template.
    token = _SINGLE_TOKEN_RE.match(raw_source)
    if token:
        resolved = _context_get(context, token.group(1))
        if isinstance(resolved, dict):
            return _ref_from_struct(resolved, hint_name)
        if isinstance(resolved, (list, tuple)):
            if not resolved:
                raise FileSourceError(f"'{token.group(1)}' est une liste vide")
            first = resolved[0]
            return _ref_from_struct(first, hint_name) if isinstance(first, dict) \
                else _ref_from_string(str(first), context, hint_name)
        if resolved is None:
            raise FileSourceError(f"'{token.group(1)}' est nul")
        return _ref_from_string(str(resolved), context, hint_name)

    return _ref_from_string(raw_source, context, hint_name)


def resolve_file_refs(raw_source, context, hint_name:str=None)->list:
    if isinstance(raw_source, (list, tuple)):
        refs = []
        for item in raw_source:
            refs.extend(resolve_file_refs(item, context, hint_name))
        return refs

    if isinstance(raw_source, str):
        token = _SINGLE_TOKEN_RE.match(raw_source)
        if token:
            resolved = _context_get(context, token.group(1))
            if isinstance(resolved, (list, tuple)):
                refs = []
                for item in resolved:
                    refs.append(_ref_from_struct(item, hint_name) if isinstance(item, dict)
                                else _ref_from_string(str(item), context, hint_name))
                return refs

    return [resolve_file_ref(raw_source, context, hint_name)]


def _context_get(context, key:str):
    try:
        return context.get(key)
    except KeyError:
        raise FileSourceError(f"Variable de contexte introuvable : {key}")


#Chaine littérale, éventuellement templatisée ("/data/{date}/rapport.csv"), URL "/files/..." ou clé.
def _ref_from_string(raw:str, context, hint_name:str=None)->FileRef:
    source = context.transform(raw).strip()

    if "/files/" in source:
        try:
            key = FileStore.key_from_url(source)
        except ValueError as e:
            raise FileSourceError(str(e))
        return FileRef(FileStore.path(key), FileStore.filename_from_url(source) or hint_name, key=key)

    if _HEX_KEY_RE.match(source):
        return FileRef(FileStore.path(source), hint_name, key=source)

    return FileRef(str(Path(source).expanduser()), os.path.basename(source) or hint_name)


#Dict de fichier de pipeline -> FileRef. La clé FileStore (directe ou extraite de l'URL) prime ;
#à défaut on retombe sur le chemin disque.
def _ref_from_struct(struct, hint_name:str=None)->FileRef:
    if not isinstance(struct, dict):
        raise FileSourceError(f"Structure de fichier invalide : {struct!r}")

    filename = struct.get("filename") or struct.get("name") or hint_name
    key = struct.get("key")
    if not key and struct.get("url"):
        try:
            key = FileStore.key_from_url(struct["url"])
        except ValueError:
            key = None

    if key:
        return FileRef(struct.get("path") or FileStore.path(key), filename, key=key)

    path = struct.get("path")
    if path:
        return FileRef(str(Path(path).expanduser()), filename)

    raise FileSourceError(f"Fichier de contexte inaccessible : {struct!r}")
