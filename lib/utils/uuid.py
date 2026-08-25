
import time
import random
import uuid

class Uuid:
    @staticmethod
    def getUuid()->str:
        timestamp = int(time.time() * 1000000)  # microseconds
        random_part = random.randint(1000, 9999)
        return f"{timestamp}{random_part}"

    def get():
        return uuid.uuid4().hex
        
