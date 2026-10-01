from lib.rag.collection import RagCollection
from lib.utils.dynamicimport import DynamicImport

"""
Embedder — Génération de vecteurs d'embedding
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class Embedder:
    #`collection` : collection RAG dont l'embedder (rag.collections.<collection>.embedder) est utilisé :
    #indexation et recherche d'une collection encodent ainsi toujours avec le même modèle.
    def __init__(self, collection: str):
        config = RagCollection.get(collection)["embedder"]
        className = config["class"]

        #La classe XxxEmbedder est définie dans lib/agent/llmembedder/xxx.py
        self.embedder = DynamicImport.getInstance(
            className=className,
            moduleName=className.removesuffix("Embedder"),
            classPath="lib.agent.llmembedder",
            config=config
        )

        #Identifiant du modèle d'embedding : des vecteurs ne sont comparables que s'ils ont le même identifiant
        self.model_id = f"{className}:{config['api_base']}:{config['model']}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.embedder.embed(texts=texts)
