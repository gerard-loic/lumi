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
    offer_name: str                             = Field(description="Nom de l'offre souscrite")
    offer_bandwidth: int                        = Field(description="Débit en Mb/s")
    offer_delay_weeks: int                      = Field(description="Délai de déploiement en semaines")
    offer_monthly_subscription_price: float     = Field(description="Prix mensuel en EUR")
    offer_commitment_month: int                 = Field(description="Durée d'engagement en mois")
    offer_construction_price: float             = Field(description="Frais de raccordement en EUR")
    gtr: Optional[str]                         = Field(None, description="Garantie de Temps de Rétablissement")
    workflow_actions: list[ActionWorkflow]      = Field(description="Actions disponibles à l'étape courante")
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
    RestApi.setBasicAuthentification(basicToken="213|lkYOJK3HFfNHvzQqu4qE9pZk1yzv5LaoFQ1KfMXieec5bf73")
    data = RestApi.show(endpoint="order", id=id, relations=["status","operator"])

    print(data, file=sys.stderr, flush=True)
    #return CommandeDetail.model_validate(data)

    return CommandeDetail(
        reference=data["reference"],
        status=Statut(**data["status"]),
        city=data.get("city"),
        zipcode=data.get("zipcode"),
        offer_name=data["offer_name"],
        offer_bandwidth=data["offer_bandwidth"],
        offer_delay_weeks=data["offer_delay_weeks"],
        offer_monthly_subscription_price=data["offer_monthly_subscription_price"],
        offer_commitment_month=data["offer_commitment_month"],
        offer_construction_price=data["offer_construction_price"],
        gtr=data.get("gtr"),
        workflow_actions=[ActionWorkflow(**a) for a in data.get("workflow_actions", [])],
        url="http://moi.fr/6372539"
    )


