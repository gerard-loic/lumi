class Dict:
    @staticmethod
    def mergeDicts(dict1, dict2):
        #Fusionne récursivement deux dictionnaires.
        #Les valeurs de dict2 écrasent celles de dict1.
        result = dict1.copy()
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Utils.mergeDicts(result[key], value)
            else:
                result[key] = value

        return result
