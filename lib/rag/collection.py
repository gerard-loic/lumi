from lib.config.config import Config
from lib.log.logger import Logger, ERROR

"""
RagCollection — Accès à la configuration d'une collection RAG (clé rag.collections.<nom> de la configuration)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>

Une collection porte tout ce qui conditionne la compatibilité de ses vecteurs : l'embedder (classe, modèle, api),
la dimension, le découpage et le stockage. Indexation et recherche d'une même collection utilisent donc toujours
le même embedder. Un profil ne référence qu'une collection (profiles.<profil>.rag.collection).
"""
class RagCollection:
    #Configuration de la collection `name`. Une collection non déclarée est une erreur (pas de repli silencieux :
    #un autre embedder que celui de la collection fausserait les recherches sans le signaler)
    @staticmethod
    def get(name: str) -> dict:
        collections = Config.get("rag.collections", {})
        if name not in collections:
            Logger.write(text=f"[RAG] Collection '{name}' is not declared in rag.collections", type=ERROR)
            raise Exception(f"RAG collection '{name}' is not declared in rag.collections")
        return collections[name]

    #Noms des collections déclarées
    @staticmethod
    def names() -> list[str]:
        return list(Config.get("rag.collections", {}).keys())

    #Collection du profil `profile` (objet Profile), ou à défaut celle du profil "default" (utilisé hors contexte de session)
    @staticmethod
    def ofProfile(profile=None) -> str:
        from lib.agent.profile import ProfileManager
        collection = profile.getConfigValue("rag.collection") if profile else None
        return collection or ProfileManager.getProfile("default").getConfigValue("rag.collection")
