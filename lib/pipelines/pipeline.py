import json
from lib.config.config import Config
from lib.log.logger import Logger, ERROR, WARNING, OK, INFO
from pathlib import Path
from lib.utils.dynamicimport import DynamicImport
from lib.pipelines.triggerevent import TriggerEvent
from lib.pipelines._abstract import Block
from lib.utils.configfilechecker import ConfigFileChecker

class Pipeline:
    def __init__(self, pipeline_uid:str):
        self._triggers = []
        self._blocks = {}
        self._services = {}
        
        self._pipeline_uid = pipeline_uid

        self._log(text=f"Loading the pipeline...", type=WARNING)
        self._loadConfigFile()
        self._loadServices()
        self._loadTriggers()  
        self._loadBlocks()

        self._log(text=f"Pipeline loaded !", type=OK) 

    def getUid(self)->str:
        return self._pipeline_uid

    def getServices(self)->dict:
        return self._services

    def getService(self, service:str)->dict:
        return self._services[service]

    def trigger(self, event:TriggerEvent)->bool:
        for trigger in self._triggers:
            if trigger.executable(event=event):
                return True
        return False

    def getBlock(self, block_uid:str)->Block:
        if block_uid not in self._blocks:
            self._exception(text=f"Block {block_uid} is not defined !")

        return self._blocks[block_uid]

    def getRootBlock(self)->Block:
        if "_root" not in self._blocks:
            self._exception(text=f"Root block is not defined !")

        return self._blocks["_root"]

    def _loadConfigFile(self):
        self._log(text="Loading config file...")
        fichier = Path(f"{Config.get('directories.custom_pipelines')}/{self._pipeline_uid}/pipeline.json")
        if not fichier.is_file():
            self._exception(f"File {Config.get('directories.custom_pipelines')}/{self._pipeline_uid}/pipeline.json does not exists")
        with open(fichier, encoding='utf-8') as f:
            self._conf = json.load(f)
            cfc = ConfigFileChecker(schemaPath="lib/_references/pipeline.schema.json")
            if not cfc.check(data=self._conf):
                self._exception(text=f"Config file {fichier} does not match required JSON format")

            self._log(text=f"Config file loaded !")

    def _loadServices(self):
        self._log(text="Loading services...")
        if "services" in self._conf:
            self._services = self._conf["services"]  
        self._log(text="Services loaded !")

    def _loadTriggers(self):
        self._log(text="Loading triggers...")
        
        for trigger in self._conf["trigger"]:
            self._log(text=f"Trigger {trigger['class']} loaded !")
            self._triggers.append(
                DynamicImport.getInstance(
                    className=trigger["class"],
                    moduleName=str(trigger["class"]).lower(),
                    classPath="lib.pipelines.triggers",
                    config=trigger["config"]
                )
            )
        
    def _loadBlocks(self):
        self._log(text="Loading blocks...")

        for block_uid in self._conf["blocks"]:
            block = self._conf["blocks"][block_uid]
            on_success_block = None
            on_error_block = None
            if "on_success" in block:
                on_success_block = block["on_success"]
            if "on_error" in block:
                on_error_block = block["on_error"]
            self._blocks[block_uid] = DynamicImport.getInstance(
                className=block["class"],
                block_uid=block_uid,
                moduleName=str(block["class"]).lower(),
                classPath="lib.pipelines.blocks",
                config=block["config"],
                on_success_block=on_success_block,
                on_error_block=on_error_block
            )
            self._blocks[block_uid].setPipelineDir(Path(f"{Config.get('directories.custom_pipelines')}/{self._pipeline_uid}"))
        self._log(text="Blocks loaded !")

    

    def _exception(self, text:str):
        text = f"[Pipeline {self._pipeline_uid}] {text}"
        Logger.write(text=text, type=ERROR)
        raise Exception(text)

    def _log(self, text:str, type=INFO):
        text = f"[Pipeline {self._pipeline_uid}] {text}"
        Logger.write(text=text, type=type)

