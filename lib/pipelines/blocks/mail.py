import smtplib
import imaplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders, message_from_bytes
from email.header import decode_header

from lib.pipelines.block import Block
from lib.pipelines.pipelinecontext import PipelineContext
from lib.log.logger import Logger, ERROR, OK

class Mail(Block):
    def __init__(self, config:dict, next_block:str=None):
        super().__init__("Mail", config, next_block)

    def execute(self, context:PipelineContext):
        action = self._config.get("action", "send")

        try:
            if action == "send":
                result = self._sendEmail(
                    to=context.transform(self._config.get("to", [])),
                    subject=context.transform(self._config.get("subject", "")),
                    body=context.transform(self._config.get("body", "")),
                    attachments=self._config.get("attachments", [])
                )
            elif action == "list":
                result = self._listEmails(
                    folder=self._config.get("folder", "INBOX"),
                    limit=self._config.get("limit", 20)
                )
            elif action == "read":
                result = self._readEmail(
                    email_id=self._config.get("email_id"),
                    folder=self._config.get("folder", "INBOX")
                )
            else:
                Logger.write(f"[Block Smtp] Unknown action {action}", type=ERROR)
                return False
        except Exception as e:
            Logger.write(f"[Block Smtp] Action {action} failed : {e}", type=ERROR)
            return False

        context.set("result", result)
        return True

    #Ouvre une connexion SMTP authentifiée, utilisée pour l'envoi
    def _connectSmtp(self)->smtplib.SMTP:
        host     = self._config.get("smtp_host")
        port     = int(self._config.get("smtp_port", 587))
        username = self._config.get("username")
        password = self._config.get("password")
        use_ssl  = self._config.get("smtp_use_ssl", False)

        connection = smtplib.SMTP_SSL(host, port) if use_ssl else smtplib.SMTP(host, port)
        if not use_ssl and self._config.get("smtp_use_tls", True):
            connection.starttls()
        if username:
            connection.login(username, password)

        return connection

    #Ouvre une connexion IMAP authentifiée, utilisée pour la lecture des emails
    #(le protocole SMTP ne gère que l'envoi, la lecture d'une boite de réception nécessite IMAP)
    def _connectImap(self)->imaplib.IMAP4:
        host     = self._config.get("imap_host", self._config.get("smtp_host"))
        port     = int(self._config.get("imap_port", 993))
        username = self._config.get("username")
        password = self._config.get("password")
        use_ssl  = self._config.get("imap_use_ssl", True)

        connection = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        connection.login(username, password)

        return connection

    #Retourne la liste des emails d'un dossier (par défaut la boite de réception), du plus récent au plus ancien
    def _listEmails(self, folder:str="INBOX", limit:int=20)->list:
        connection = self._connectImap()
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

        return emails

    #Récupère le contenu complet d'un email (corps + pièces jointes) à partir de son identifiant IMAP
    def _readEmail(self, email_id, folder:str="INBOX")->dict:
        connection = self._connectImap()
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

    #Envoie un email, avec en pièces jointes une liste optionnelle de chemins de fichiers locaux
    def _sendEmail(self, to, subject:str, body:str, attachments:list=None)->bool:
        recipients = to if isinstance(to, list) else [to]

        message = MIMEMultipart()
        message["From"]    = self._config.get("username")
        message["To"]      = ", ".join(recipients)
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain", "utf-8"))

        for file_path in (attachments or []):
            if not os.path.isfile(file_path):
                Logger.write(f"[Block Smtp] Attachment {file_path} not found, ignored", type=ERROR)
                continue

            part = MIMEBase("application", "octet-stream")
            with open(file_path, "rb") as f:
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(file_path)}"')
            message.attach(part)

        connection = self._connectSmtp()
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
