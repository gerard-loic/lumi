import json
from lib.config.config import Config
from lib.log.logger import Logger, ERROR, WARNING, OK, INFO
from pathlib import Path
from lib.utils.dynamicimport import DynamicImport
from lib.pipelines.trigger import triggerEvent
from lib.pipelines.block import Block

class Pipeline:
    def __init__(self, pipeline_uid:str):
        self._triggers = []
        self._blocks = {}
        
        self._pipeline_uid = pipeline_uid
        self._log(text=f"Loading the pipeline...", type=WARNING)
        self._loadConfigFile()
        self._loadTriggers()  
        self._loadBlocks()

        self._log(text=f"Pipeline loaded !", type=OK) 

    def trigger(self, event:triggerEvent)->bool:
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
        with open(f"{Config.get('custom_pipelines','config/pipelines')}/{self._pipeline_uid}/pipeline.json", encoding='utf-8') as f:
            self._conf = json.load(f)
            self._log(text=f"Config file loaded !")

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
            next_block = None
            if "next_block" in block:
                next_block = block["next_block"]
            self._blocks[block_uid] = DynamicImport.getInstance(
                className=block["class"],
                moduleName=str(block["class"]).lower(),
                classPath="lib.pipelines.blocks",
                config=block["config"],
                next_block=next_block
            )
        self._log(text="Blocks loaded !")

    
        


    def _exception(self, text:str):
        text = f"[Pipeline {self._pipeline_uid}] {text}"
        Logger.write(text=text, type=ERROR)
        raise Exception(text)

    def _log(self, text:str, type=INFO):
        text = f"[Pipeline {self._pipeline_uid}] {text}"
        Logger.write(text=text, type=type)

