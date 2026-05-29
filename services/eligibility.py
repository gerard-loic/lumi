import urllib.parse
import secrets
from lib.com.database import DataBase
from lib.com.restapi import RestApi
from lib.mcp.crudtools import CrudTools
from lib.config.config import Config
import httpx
import sys
from pydantic import BaseModel
from pydantic import Field
from typing import Annotated
from typing import Optional
from typing import Literal


class AdresseRedirect(BaseModel):
    action: str = Field(description="Action à effectuer côté client ('redirect' = redirection vers l'URL).")
    url: str = Field(description="URL vers laquelle rediriger l'utilisateur pour sélectionner son adresse.")
    message: str = Field(description="Message à afficher à l'utilisateur pendant la redirection.")

class Statut(BaseModel):
    name: str = Field(description="Libellé du statut")
    uid: str  = Field(description="Identifiant machine: INPROGRESS | DELIVERED | ...")

class ActionWorkflow(BaseModel):
    name: str                  = Field(description="Action disponible à l'étape courante")
    confirmation_message: str  = Field(description="Message à afficher avant confirmation")

class EtapeWorkflow(BaseModel):
    name: str          = Field(description="Nom de l'étape")
    is_an_anomaly: bool = Field(description="True si cette étape est une anomalie")
    status: Statut

class CommandeDetail(BaseModel):
    reference: str
    status: Statut
    city: Optional[str]                         = None
    zipcode: Optional[str]                      = None
    created_at: str                             = Field(description="Date de création de la commande")
    offer_name: str                             = Field(description="Nom de l'offre souscrite")
    offer_bandwidth: int                        = Field(description="Débit en Mb/s")
    offer_delay_weeks: int                      = Field(description="Délai de déploiement en semaines")
    offer_monthly_subscription_price: float     = Field(description="Prix mensuel en EUR")
    offer_commitment_month: int                 = Field(description="Durée d'engagement en mois")
    offer_construction_price: float             = Field(description="Frais de raccordement en EUR")
    gtr: Optional[str]                         = Field(None, description="Garantie de Temps de Rétablissement")
    workflow_actions: list[ActionWorkflow]      = Field(default=[], description="Actions disponibles à l'étape courante")
    url: str                                    = Field(description="Url pour voir la commande dans l'interface, à afficher au client")


def recherche_adresse(
    localisation: Annotated[str, Field(description="Adresse complète ou partielle (ex: '15 rue de la Paix, Paris 75001')")]
) -> AdresseRedirect:
    """
    Recherche une adresse pour vérifier l'éligibilité aux offres fibre.
    À utiliser dès que l'utilisateur mentionne une adresse ou demande à vérifier son éligibilité.
    """
    token = secrets.token_urlsafe(16)
    params = urllib.parse.urlencode({"q": localisation, "token": token})
    url = f"https://votre-app.com/recherche-adresse?{params}"

    return AdresseRedirect(
        action="redirect",
        url=url,
        message="Vous allez être redirigé vers la page vous permettant de rechercher votre adresse et votre éligibilité aux offres.",
    )

def recherche_commande(
        reference: Annotated[str, Field(description="Référence de la commande, alphanumérique ou numérique (ex: 'TEF35632' ou 3635)")]
    ) -> CommandeDetail:
    """
    Recherche une commande par sa référence et retourne tous ses détails : statut, offre souscrite, tarifs (abonnement mensuel, frais de raccordement), délais, engagement.
    À utiliser dès que l'utilisateur mentionne une référence de commande ou pose une question sur une commande (tarif, état, délai, offre, abonnement...).
    """

    id = DataBase.findRessourceId(entity="orders", reference=reference, attributes=["id:int","reference:str"])
    RestApi.setBasicAuthentification(basicToken="272|AUdbZUiWvTCEcEGYvZ9Df1iVg4kF1T2PYPRfF4vD82f58852")
    data = RestApi.show(endpoint="order", id=id, relations=["status","operator"])

    print(data, file=sys.stderr, flush=True)
    if data is None:
        raise ValueError(f"Commande introuvable : {reference}")

    return CommandeDetail.model_validate({**data, "url": "http://moi.fr/6372539"})


def liste_commandes(
        ordonnancement: Annotated[
            Literal["reference", "created_at", "offer_name", "offer_bandwidth",
                "offer_monthly_subscription_price", "offer_commitment_month",
                "offer_construction_price", "city", "zipcode"],
                Field(description="Attribut alphanumérique par lequel ordonner les commandes retournées")
        ],
        ordonnancement_sens: Annotated[
            Literal["ASC", "DESC"],
            Field(description="Ordonner par ordre croissant (ASC) ou décroissant (DESC)")
        ],
        limite: Annotated[int, Field(description="Nombre maximal de résultats à retourner")],
        filtres: Annotated[
            Optional[list[dict]],
            Field(
                default=None,
                description=(
                    "Filtres à appliquer sur la liste de commandes. "
                    "Liste de conditions, chacune sous la forme {\"field\": ..., \"op\": ..., \"value\": ..., \"logic\": \"and\"|\"or\"}. "
                    "Champs filtrables : reference, created_at, city, zipcode, offer_name, offer_bandwidth, "
                    "offer_monthly_subscription_price, offer_commitment_month, offer_construction_price. "
                    "Opérateurs disponibles : eq (égal), neq (différent), gt/lt/gte/lte (comparaisons numériques), "
                    "ilk/nilk (correspondance partielle insensible à la casse, fonctionne comme SQL LIKE : % est un joker qui remplace zéro ou plusieurs caractères. Exemples : '%paris%' contient 'paris', 'paris%' commence par 'paris', '%paris' finit par 'paris'. nilk est la négation de ilk), "
                    "in/nin (dans une liste — value doit être une liste), "
                    "btw/nbtw (entre deux valeurs — value doit être [min, max]), ist/isf (vrai/faux). "
                    "Le champ 'logic' relie la condition à la précédente (défaut: 'and'). "
                    "Exemple — commandes de Paris avec débit >= 100 Mb/s : "
                    "[{\"field\": \"city\", \"op\": \"eq\", \"value\": \"Paris\"}, "
                    "{\"field\": \"offer_bandwidth\", \"op\": \"gte\", \"value\": 100, \"logic\": \"and\"}]"
                )
            )
        ] = None,
    ) -> list:
    """
    Lister les commandes et en retourner tous es détails : statut, offre souscrite, tarifs (abonnement mensuel, frais de raccordement), délais, engagement.
    À utiliser dès que l'utilisateur souhaite connaitre l'historique de ses commandes ou si la demande nécessite d'aller consulter l'historique des commandes de l'utilisateur.
    """

    print(f"Tool : liste_commande // {ordonnancement}:{ordonnancement_sens}:{str(limite)}", file=sys.stderr, flush=True)

    RestApi.setBasicAuthentification(basicToken="272|AUdbZUiWvTCEcEGYvZ9Df1iVg4kF1T2PYPRfF4vD82f58852")
    data = RestApi.list(endpoint="order", relations=["status","operator"], order=f"{ordonnancement}.{ordonnancement_sens}", limit=limite, filters=filtres)
    print(data, file=sys.stderr, flush=True)

    return [CommandeDetail.model_validate({**item, "url": f"http://moi.fr/{item['id']}"}) for item in data]

    