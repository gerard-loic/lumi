import os
import re
from datetime import datetime

from lib.cron.tasks.crontask import CronTask
from lib.config.config import Config

_LOG_FILE_RE = re.compile(r"^(\d{8})\.log$")

"""
Shredding — Classe tâche CRON de délestage
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Shredding(CronTask):
    def __init__(self, config:dict):
        super().__init__(
            className="Shredding",
            config=config
        )

    def run(self):
        super().run()

        if "log_max_days" not in self.config:
            self.exception(text="key 'log_max_days' not defined in config")
        log_max_days = self.config["log_max_days"]

        log_dir = Config.get("logger.file.path", default="logs")
        if not os.path.isdir(log_dir):
            return

        today = datetime.now().date()
        for filename in os.listdir(log_dir):
            match = _LOG_FILE_RE.match(filename)
            if not match:
                continue

            file_date = datetime.strptime(match.group(1), "%Y%m%d").date()
            if (today - file_date).days < log_max_days:
                continue

            file_path = os.path.join(log_dir, filename)
            os.remove(file_path)
            self.log(text=f"Deleted log file '{file_path}'")
