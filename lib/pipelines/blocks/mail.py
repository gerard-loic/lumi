import smtplib
import imaplib
import os
import re
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders, message_from_bytes
from email.header import decode_header

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR, OK

#Bloc Mail : envoie un email (SMTP) ou lit une boite de réception (IMAP). Le résultat est écrit dans le contexte sous la clé "result".
#
#Paramètres de configuration communs (clé "config" du bloc) :
#  - action        (str,  défaut "send")   : "send" (envoi), "list" (liste des emails d'un dossier) ou "read" (contenu d'un email).
#  - username      (str)                   : identifiant du compte, sert aussi d'adresse d'expéditeur.
#  - password      (str)                   : mot de passe / mot de passe d'application du compte.
#
#Paramètres SMTP (action "send") :
#  - smtp_host     (str)                   : serveur SMTP.
#  - smtp_port     (int,  défaut 587)      : port SMTP.
#  - smtp_use_ssl  (bool, défaut False)    : connexion SSL directe (SMTP_SSL).
#  - smtp_use_tls  (bool, défaut True)     : STARTTLS après connexion (ignoré si smtp_use_ssl).
#  - to            (str | list[str])       : destinataire(s) ; transformé via le contexte.
#  - subject       (str,  défaut "")       : sujet ; transformé via le contexte.
#  - body          (str,  défaut "")       : corps texte brut ; transformé via le contexte.
#  - attachments   (list, défaut [])       : pièces jointes. Chaque entrée peut être :
#                                            - un chemin de fichier local (str), transformé via le contexte ;
#                                            - une référence de contexte "{var}" (jeton unique) pointant vers une
#                                              pièce jointe ou une liste de pièces jointes, ex. "{files}" =
#                                              fichiers produits par un bloc Agent, "{report}" = sortie d'un bloc
#                                              DataViewFile. Contrairement à une interpolation classique (qui
#                                              sérialiserait la liste en chaine), la structure est ici résolue ;
#                                            - un dict {"path": ..., "filename": ...} (structure de fichier de pipeline) ;
#                                            - une liste imbriquée de ce qui précède (aplatie).
#                                            Le nom présenté au destinataire vient de "filename" (les fichiers de
#                                            pipeline sont stockés sans extension) ; le type MIME en est déduit.
#                                            Les fichiers introuvables sont ignorés.
#
#Paramètres IMAP (actions "list" et "read") :
#  - imap_host     (str,  défaut smtp_host): serveur IMAP.
#  - imap_port     (int,  défaut 993)      : port IMAP.
#  - imap_use_ssl  (bool, défaut True)     : connexion SSL (IMAP4_SSL).
#  - folder        (str,  défaut "INBOX")  : dossier ciblé.
#  - limit         (int,  défaut 20)       : nombre max d'emails retournés (action "list").
#  - email_id      (str)                   : identifiant IMAP de l'email à lire (action "read").

# -  output        (str)                   : nom de la variable de contexte ou mettre le mail ou les mails (actions "list" et "read")
class Mail(Block):
    def __init__(self, block_uid:str, config:dict, on_success_block:str=None, on_error_block:str=None):
        super().__init__("Mail", block_uid, config, on_success_block=on_success_block, on_error_block=on_error_block)

    def execute(self, context:PipelineContext):
        action = context.getConfig(key="action", default="send")
        output_var = context.getConfig(key="output", default="content")

        to = context.getConfig(key="to", default=[])
        subject = context.getConfig(key="subject", default="")
        body = context.getConfig(key="body", default="")
        #On part de la config brute (non interpolée) : une entrée "{var}" doit être résolue en
        #structure (dict/list de fichiers) plutôt que sérialisée en chaine par le moteur de template.
        attachments = self._resolveAttachments(self._config.get("attachments", []), context)
        folder = context.getConfig(key="folder", default="INBOX")
        limit = context.getConfig(key="limit", default=20)
        email_id = context.getConfig(key="email_id", default=0)

        
        username = context.getConfig(key="username", default="")
        password = context.getConfig(key="password", default="")

        smtp_host = context.getConfig(key="smtp_host", default="")
        smtp_port = context.getConfig(key="smtp_port", default=587)
        smtp_use_ssl = context.getConfig(key="smtp_use_ssl", default=False)

        imap_host = context.getConfig(key="imap_host", default="")
        imap_port = context.getConfig(key="imap_port", default=993)
        imap_use_ssl = context.getConfig(key="imap_use_ssl", default=True)


        try:
            if action == "send":
                result = self._sendEmail(
                    to=to,
                    subject=subject,
                    body=body,
                    attachments=attachments,
                    smtp_host=smtp_host, 
                    smtp_port=smtp_port, 
                    username=username, 
                    password=password, 
                    smtp_use_ssl=smtp_use_ssl
                )
            elif action == "list":
                result = self._listEmails(
                    folder=folder,
                    limit=limit,
                    imap_host=imap_host, 
                    imap_port=imap_port, 
                    username=username, 
                    password=password, 
                    imap_use_ssl=imap_use_ssl
                )
            elif action == "read":
                result = self._readEmail(
                    email_id=email_id,
                    folder=folder,
                    imap_host=imap_host, 
                    imap_port=imap_port, 
                    username=username, 
                    password=password, 
                    imap_use_ssl=imap_use_ssl
                )
            else:
                Logger.write(f"[Block Smtp] Unknown action {action}", type=ERROR)
                return False
        except Exception as e:
            Logger.write(f"[Block Smtp] Action {action} failed : {e}", type=ERROR)
            return False

        context.set(output_var, result)
        return True

    #Jeton d'interpolation unique, ex. "{files}" ou "{report.path}" (rien autour).
    _SINGLE_TOKEN_RE = re.compile(r'^\s*\{([\w\.\[\]]+)\}\s*$')

    #Aplatit la configuration "attachments" en une liste de dicts {"path","filename"} : "path" est le
    #chemin du fichier sur disque, "filename" le nom (avec extension) proposé au destinataire — les
    #fichiers de pipeline sont stockés sous une clé hexadécimale sans extension, le nom lisible est porté
    #à part. Chaque entrée de config peut être : un chemin (str) transformé via le contexte, une
    #référence de contexte "{var}" (jeton unique) pointant vers une structure de fichier
    #{"path","filename",...} ou une liste de telles structures (ex. "{files}" = sortie d'un bloc Agent),
    #un dict {"path":...,"filename":...}, ou une liste imbriquée de tout cela.
    def _resolveAttachments(self, value, context:PipelineContext, _seen=None)->list:
        _seen = _seen if _seen is not None else set()
        items = []

        if value is None or value == "":
            return items

        if isinstance(value, (list, tuple)):
            for item in value:
                items.extend(self._resolveAttachments(item, context, _seen))
            return items

        if isinstance(value, dict):
            path = value.get("path")
            if path:
                items.append({"path": path, "filename": value.get("filename") or os.path.basename(path)})
            else:
                Logger.write(f"[Block Smtp] Attachment entry without 'path' ignored : {value}", type=ERROR)
            return items

        if isinstance(value, str):
            match = self._SINGLE_TOKEN_RE.match(value)
            #Entrée réduite à un seul jeton "{var}" : on résout la structure sous-jacente
            #(dict/list de fichiers) au lieu de la laisser sérialiser en chaine par le template.
            if match and match.group(1) not in _seen:
                _seen.add(match.group(1))
                try:
                    resolved = context.get(match.group(1))
                except KeyError:
                    resolved = None
                if resolved is not None and not isinstance(resolved, str):
                    return self._resolveAttachments(resolved, context, _seen)
            #Sinon : chemin littéral, éventuellement templatisé (ex. "/data/{date}/rapport.pdf").
            path = context.transform(value)
            items.append({"path": path, "filename": os.path.basename(path)})
            return items

        Logger.write(f"[Block Smtp] Unsupported attachment entry ignored : {value!r}", type=ERROR)
        return items

    #Ouvre une connexion SMTP authentifiée, utilisée pour l'envoi
    def _connectSmtp(self, host, port, username, password, use_ssl)->smtplib.SMTP:
        

        connection = smtplib.SMTP_SSL(host, port) if use_ssl else smtplib.SMTP(host, port)
        if not use_ssl and self._config.get("smtp_use_tls", True):
            connection.starttls()
        if username:
            connection.login(username, password)

        return connection

    #Ouvre une connexion IMAP authentifiée, utilisée pour la lecture des emails
    #(le protocole SMTP ne gère que l'envoi, la lecture d'une boite de réception nécessite IMAP)
    def _connectImap(self, host, port, username, password, use_ssl)->imaplib.IMAP4:
        

        connection = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        connection.login(username, password)

        return connection

    #Retourne la liste des emails d'un dossier (par défaut la boite de réception), du plus récent au plus ancien
    def _listEmails(self, folder:str="INBOX", limit:int=20, imap_host:str="", imap_port:int=993, username:str="", password:str="", imap_use_ssl:bool=False)->list:
        
        connection = self._connectImap(imap_host, imap_port, username, password, imap_use_ssl)
        emails = []
        try:
            connection.select(folder, readonly=True)
            status, data = connection.search(None, "ALL")
            if status != "OK":
                return emails

            email_ids = data[0].split()
            email_ids.reverse()
            for email_id in email_ids[:limit]:
                status, msg_data = connection.fetch(email_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                if status != "OK" or not msg_data or msg_data[0] is None:
                    continue

                headers = message_from_bytes(msg_data[0][1])
                emails.append({
                    "id":      email_id.decode(),
                    "subject": self._decodeHeader(headers.get("Subject", "")),
                    "from":    self._decodeHeader(headers.get("From", "")),
                    "date":    headers.get("Date", "")
                })
        finally:
            connection.logout()

        Logger.write(text=emails)
        return emails

    #Récupère le contenu complet d'un email (corps + pièces jointes) à partir de son identifiant IMAP
    def _readEmail(self, email_id, folder:str="INBOX", imap_host:str="", imap_port:int=993, username:str="", password:str="", imap_use_ssl:bool=False)->dict:
        connection = self._connectImap(imap_host, imap_port, username, password, imap_use_ssl)
        try:
            connection.select(folder, readonly=True)

            raw_id = email_id.encode() if isinstance(email_id, str) else email_id
            status, msg_data = connection.fetch(raw_id, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                raise Exception(f"Email {email_id} not found in {folder}")

            message = message_from_bytes(msg_data[0][1])

            body = ""
            attachments = []
            if message.is_multipart():
                for part in message.walk():
                    content_disposition = str(part.get("Content-Disposition", ""))
                    content_type = part.get_content_type()

                    if "attachment" in content_disposition:
                        attachments.append({
                            "filename":     self._decodeHeader(part.get_filename() or "fichier"),
                            "content_type": content_type,
                            "size":         len(part.get_payload(decode=True) or b"")
                        })
                    elif content_type == "text/plain" and not body:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            else:
                payload = message.get_payload(decode=True)
                if payload:
                    body = payload.decode(message.get_content_charset() or "utf-8", errors="replace")

            return {
                "id":          email_id if isinstance(email_id, str) else email_id.decode(),
                "subject":     self._decodeHeader(message.get("Subject", "")),
                "from":        self._decodeHeader(message.get("From", "")),
                "to":          self._decodeHeader(message.get("To", "")),
                "date":        message.get("Date", ""),
                "body":        body,
                "attachments": attachments
            }
        finally:
            connection.logout()

    #Envoie un email, avec en pièces jointes une liste optionnelle de dicts {"path","filename"}
    #("path" = chemin sur disque, "filename" = nom présenté au destinataire).
    def _sendEmail(self, to, subject:str, body:str, attachments:list=None, smtp_host:str="", smtp_port:int=993, username:str="", password:str="", smtp_use_ssl:bool=False)->bool:
        recipients = to if isinstance(to, list) else [to]

        message = MIMEMultipart()
        message["From"]    = username
        message["To"]      = ", ".join(recipients)
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain", "utf-8"))

        for attachment in (attachments or []):
            file_path = attachment["path"]
            filename = attachment.get("filename") or os.path.basename(file_path)
            if not os.path.isfile(file_path):
                Logger.write(f"[Block Smtp] Attachment {file_path} not found, ignored", type=ERROR)
                continue

            #Type MIME déduit du nom présenté (les fichiers de pipeline sont stockés sans extension).
            content_type, _ = mimetypes.guess_type(filename)
            maintype, subtype = (content_type.split("/", 1) if content_type else ("application", "octet-stream"))

            part = MIMEBase(maintype, subtype)
            with open(file_path, "rb") as f:
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            message.attach(part)

        connection = self._connectSmtp(smtp_host, smtp_port, username, password, smtp_use_ssl)
        try:
            connection.sendmail(message["From"], recipients, message.as_string())
        finally:
            connection.quit()

        Logger.write(f"[Block Smtp] Email sent to {recipients}", type=OK)
        return True

    #Décode un header MIME potentiellement encodé (ex : =?utf-8?...?=)
    def _decodeHeader(self, value:str)->str:
        if not value:
            return ""
        decoded = ""
        for text, charset in decode_header(value):
            if isinstance(text, bytes):
                decoded += text.decode(charset or "utf-8", errors="replace")
            else:
                decoded += text
        return decoded
