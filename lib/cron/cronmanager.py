import time

from lib.config.config import Config
from lib.log.logger import Logger, ERROR, OK
from lib.utils.dynamicimport import DynamicImport

"""
CronManager — Gestionnaire de tâches CRON
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class CronManager:
    @staticmethod
    def init():
        #Initialisation des tâches CRON
        CronManager.tasks = []
        Logger.write("[CronManager] Initalizing cron tasks...")
        for task in Config.get("cron"):
            CronManager.tasks.append(DynamicImport.getInstance(className=task["task"], moduleName=task["task"], classPath="lib.cron.tasks", config=task))
        Logger.write("[CronManager] cron tasks initialized !", OK)

    #Execute toutes les tâches CRON qui doivent être executées à ce moment précis
    @staticmethod
    async def execute():
        timestamp = int(time.time())
        for task in CronManager.tasks:
            try:
                if task.testExecution(timestamp=timestamp):
                    await task.run()
            except Exception as e:
                Logger.write(f"[CronManager] task '{task.className}' failed: {str(e)}", ERROR)