import uuid


class Uuid:
    @staticmethod
    def get():
        return uuid.uuid4().hex
        