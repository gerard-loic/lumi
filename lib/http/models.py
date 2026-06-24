from pydantic import BaseModel
from typing import Optional
from fastapi import Form, File, UploadFile

#-------------------------------------------------------------------
#Format request

"""
AuthRequest — Format requête HTTP auth
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class AuthRequest(BaseModel):
    authorization: dict

"""
RagIndexRequest — Format requête HTTP indexation RAG (form-data + fichier optionnel)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class RagIndexRequest:
    def __init__(
        self,
        text:       Optional[str]        = Form(default=None),
        file:       Optional[UploadFile] = File(default=None),
        source:     Optional[str]        = Form(default=None),
        collection: Optional[str]        = Form(default=None),
    ):
        self.text = text
        self.file = file
        self.source = source
        self.collection = collection

"""
RagDeleteDocumentRequest — Format requête HTTP suppression document RAG (path params)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class RagDeleteDocumentRequest:
    def __init__(self, collection: str, source: str):
        self.collection = collection
        self.source = source

"""
RagDeleteCollectionRequest — Format requête HTTP suppression collection RAG (path params)
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class RagDeleteCollectionRequest:
    def __init__(self, collection: str):
        self.collection = collection


#-------------------------------------------------------------------
#Format retour endpoints

"""
ToolInfo — Format retour HTTP tools
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class ToolInfo(BaseModel):
    name: str
    description: str


"""
HealthResponse - Format retour endpoint health
"""
class HealthResponse(BaseModel):
    status: str
    services: list
    active_ws: int 
    version: str 
    version_name: str

"""
UsageResponse - Format retour endpoint usage
"""
class UsageResponse(BaseModel):
    year: str
    month: str
    token_used: int
    request_count: int


"""
AuthResponse - Format retour endpoint auth
"""
class AuthResponse(BaseModel):
    token: str

"""
RagAddDocumentResponse - Format retour ajout document RAG
"""
class RagAddDocumentResponse(BaseModel):
    chunks_indexed: int
    collection: str


"""
RagStatResponse - Format retour statistiques RAG
"""
class RagStatResponse(BaseModel):
    total_chunks: int
    collections: list


"""
RagDeleteDocumentResponse - Format retour suppression RAG
"""
class RagDeleteDocumentResponse(BaseModel):
    deleted_chunks: int
    source: str
    collection: str

"""
RagDeleteCollectionResponse - Format retour suppression collection RAG
"""
class RagDeleteCollectionResponse(BaseModel):
    deleted_chunks: int
    collection: str