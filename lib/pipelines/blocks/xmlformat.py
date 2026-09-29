from lxml import etree

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR

#Bloc XmlFormat : parse une chaine XML du contexte, la valide optionnellement contre un XML Schema (XSD), et écrit la structure obtenue.
#
#Paramètres de configuration (clé "config" du bloc) :
#  - input  (str,         défaut "")    : clé du contexte contenant la chaine XML sérialisée à parser (une valeur non-str provoque une erreur).
#  - format (str | False, défaut False) : XML Schema (XSD) de validation sous forme de chaine ; si False, aucune validation n'est effectuée.
#  - output (str,         défaut "")    : clé du contexte où stocker la structure désérialisée.
#
#Conversion XML -> structure : {racine: contenu}, où le contenu d'un élément est
#  - sa valeur texte (str) s'il n'a ni attribut ni enfant, None s'il est vide ;
#  - sinon un dict : attributs préfixés par "@", enfants par nom local (liste si l'élément est répété), texte sous "#text".
class XmlFormat(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("XmlFormat", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        #Récupération de la configuration
        format = context.getConfig(key="format", default=False)
        input = context.getConfig(key="input", default="")
        output = context.getConfig(key="output", default="")

        input_val = context.get(key=input)

        if not isinstance(input_val, str):
            Logger.write(f"[Block XmlFormat] Initial value must be a string", type=ERROR)
            return False

        try:
            root = etree.fromstring(input_val.strip().encode("utf-8"), parser=self._parser())
        except etree.XMLSyntaxError as e:
            Logger.write(f"[Block XmlFormat] Invalid XML on input '{input}' : {e}", type=ERROR)
            return False

        #format est un XSD : on valide le document quand il est fourni (format != False)
        if format is not False:
            try:
                schema = etree.XMLSchema(etree.fromstring(str(format).strip().encode("utf-8"), parser=self._parser()))
            except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as e:
                Logger.write(f"[Block XmlFormat] Invalid XML Schema : {e}", type=ERROR)
                return False
            if not schema.validate(root):
                Logger.write(f"[Block XmlFormat] Schema validation failed on input '{input}' : {schema.error_log.last_error}", type=ERROR)
                return False

        context.set(output, {etree.QName(root).localname: self._toValue(root)})
        return True

    #Parser durci : pas de résolution d'entités (XXE), pas d'accès réseau, pas de DTD
    def _parser(self):
        return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False, remove_comments=True, remove_pis=True)

    def _toValue(self, element):
        text = (element.text or "").strip()
        children = [child for child in element if isinstance(child.tag, str)]

        if not element.attrib and not children:
            return text if text else None

        value = {f"@{etree.QName(k).localname}": v for k, v in element.attrib.items()}
        for child in children:
            name = etree.QName(child).localname
            child_value = self._toValue(child)
            if name in value:
                if not isinstance(value[name], list):
                    value[name] = [value[name]]
                value[name].append(child_value)
            else:
                value[name] = child_value
        if text:
            value["#text"] = text
        return value
