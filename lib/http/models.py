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
    profile: Optional[str] = None
    language: Optional[str] = None

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


"""
PipelineStartRequest — Format requête HTTP démarrage d'un pipeline via API
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PipelineStartRequest:
    def __init__(self, pipeline: str):
        self.pipeline = pipeline


"""
PipelineStartBody — Corps JSON optionnel du démarrage d'un pipeline via API
Le contenu de "payload" est transmis tel quel au contexte du pipeline (clé "trigger.data").
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PipelineStartBody(BaseModel):
    payload: Optional[dict] = None


"""
PipelineInfoRequest — Format requête HTTP info d'un pipeline via API
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PipelineInfoRequest:
    def __init__(self, process_uid: str):
        self.process_uid = process_uid


"""
PipelineStepInfoRequest — Format requête HTTP détail d'une étape d'un process via API
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PipelineStepInfoRequest:
    def __init__(self, process_uid: str, id: int):
        self.process_uid = process_uid
        self.id = id


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
HealthResponse - Format retour endpoint GET auth
"""
class AuthSessionResponse(BaseModel):
    followup_questions: bool
    language: str
    attachements: bool
    attachements_max_file_size_mb: int
    attachements_max_files: int
    attachements_allowed_extensions: list

"""
UsageResponse - Format retour endpoint usage
"""
class UsageResponse(BaseModel):
    year: str
    month: str
    token_used: int
    request_count: int
    token_limit: int
    request_limit: int


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

"""
FileUploadResponse - Format retour upload d'une pièce jointe conversationnelle
"""
class FileUploadResponse(BaseModel):
    key: str
    filename: str
    tokens: int


"""
PipelineStartResponse — Format retour HTTP PipelineStart
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PipelineStartResponse(BaseModel):
    pipelines:list

"""
PipelineInfoResponse — Format retour HTTP PipelineInfo
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PipelineInfoResponse(BaseModel):
    pipeline_uid: str
    process_uid: str
    created_at: str
    started_at: str
    ended_at: str
    is_ended:bool
    is_success:bool
    steps:list

"""
PipelineStepInfoResponse — Format retour HTTP détail d'une étape d'un process
Auteur : Loic Gerard <loic.gerard@e-kodo.fr>
"""
class PipelineStepInfoResponse(BaseModel):
    id: int
    process_uid: str
    pipeline_uid: str
    name: str
    created_at: str
    is_success: bool
    logs: str