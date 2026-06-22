from datetime import date, timedelta
from typing import Annotated
from pydantic import Field
import holidays

from lib.mcp.tools import MCPTool, tool_description

_fr_holidays = holidays.France(years=range(date.today().year, date.today().year + 5))


def _is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _fr_holidays


def _next_business_day(d: date) -> date:
    d += timedelta(days=1)
    while not _is_business_day(d):
        d += timedelta(days=1)
    return d


class DateTimeTools(MCPTool):
    name = "datetime"
    description = "Outils de calendrier et jours ouvrés"

    @tool_description(name="Calcul de jours ouvrés")
    def get_business_days(
        self,
        date_start: Annotated[str, Field(description="Date de début au format YYYY-MM-DD (incluse)")],
        date_end: Annotated[str, Field(description="Date de fin au format YYYY-MM-DD (incluse)")],
    ) -> dict:
        """
        Calcule le nombre de jours ouvrés entre deux dates (hors week-ends et jours fériés français,
        incluant Alsace-Moselle si pertinent). Retourne aussi la liste des jours fériés tombant dans la plage.
        Utiliser dès qu'une question porte sur des délais en jours ouvrés, des échéances, ou la durée
        entre deux dates en excluant week-ends et fériés.
        """
        start = date.fromisoformat(date_start)
        end = date.fromisoformat(date_end)

        if end < start:
            raise ValueError("date_end doit être postérieure ou égale à date_start")

        years_needed = range(start.year, end.year + 1)
        fr = holidays.France(years=years_needed)

        count = 0
        public_holidays_in_range = []
        current = start
        while current <= end:
            if current in fr:
                public_holidays_in_range.append({
                    "date": current.isoformat(),
                    "name": fr[current],
                })
            elif current.weekday() < 5:
                count += 1
            current += timedelta(days=1)

        return {
            "business_days": count,
            "date_start": date_start,
            "date_end": date_end,
            "public_holidays": public_holidays_in_range,
        }

    @tool_description(name="Prochain jour ouvré")
    def next_business_day(
        self,
        from_date: Annotated[str, Field(description="Date de référence au format YYYY-MM-DD")],
    ) -> dict:
        """
        Retourne le prochain jour ouvré (hors week-ends et jours fériés français) après une date donnée.
        Utiliser quand l'utilisateur demande 'le prochain jour ouvré après le X' ou pour calculer
        une échéance à J+1 ouvré.
        """
        ref = date.fromisoformat(from_date)
        fr = holidays.France(years=range(ref.year, ref.year + 2))

        nxt = ref + timedelta(days=1)
        while nxt.weekday() >= 5 or nxt in fr:
            nxt += timedelta(days=1)

        return {
            "next_business_day": nxt.isoformat(),
            "day_name": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"][nxt.weekday()],
        }

    @tool_description(name="Jours fériés")
    def get_public_holidays(
        self,
        year: Annotated[int, Field(description="Année (ex: 2025)")],
    ) -> list[dict]:
        """
        Retourne la liste complète des jours fériés français pour une année donnée.
        Utiliser quand l'utilisateur demande les jours fériés d'une année ou veut savoir
        si une date précise est fériée.
        """
        fr = holidays.France(years=year)
        return sorted(
            [{"date": d.isoformat(), "name": name} for d, name in fr.items()],
            key=lambda x: x["date"],
        )
