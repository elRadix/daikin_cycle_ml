"""Alert texts, Dutch (#463). Same keys and placeholders as _en / _fr."""
from __future__ import annotations

LEVELS = {
    "info": "Geen actie nodig",
    "watch": "Houd het in de gaten",
    "act": "Actie nodig",
}

WORDS = {"see": "Bekijk:", "or": " · of ", "test": "TEST"}

CARDS = {"eff": "Rendement-kaart", "daily": "Dagoverzicht-kaart"}
TABS = {
    "eff": {"live": "Live", "today": "Vandaag", "eff": "Rendement", "curve": "Stooklijn", "advice": "Advies"},
    "daily": {"today": "Vandaag", "overview": "Overzicht", "quality": "Kwaliteit", "cycles": "Cycli",
              "duration": "Duur", "events": "Events"},
}
GRAPHS = {
    "water": "Watertemperaturen", "compressor": "Compressor", "hydraulics": "Debiet en ΔT",
    "comfort": "Comfort", "strip": "Backup-heater en ontdooien", "balance": "Warmtebalans",
}

ALERTS = {
    "pendulum_hourly": {
        "title": "Veel starts dit uur",
        "what": "{cph} compressorstarts in het laatste uur (je grens: {target_cph}).",
        "what_plain": "Veel compressorstarts in het laatste uur.",
        "todo": "Bij zacht weer kan het laagste vermogen van de warmtepomp meer zijn dan het huis nodig heeft; wat aan/uit draaien is dan normaal, ook na het opwarmen van de boiler of een ontdooiing. Houdt het aan, zet dan alle radiatorkranen en vloergroepen open; zijn de kamers warmer dan nodig, verlaag dan de offset van de stooklijn 1–2 °C op de Daikin-bediening of in de Onecta-app.",
    },
    "pendulum_daily": {
        "title": "Veel runs vandaag",
        "what": "{cycles_today} runs vandaag (je grens: {target_cpd}).",
        "what_plain": "Veel runs vandaag.",
        "todo": "Lange, rustige runs zijn het zuinigst. Gebeurt dit elke dag, zet dan alle radiatorkranen en vloergroepen open; zijn de kamers warmer dan nodig, verlaag dan de offset van de stooklijn 1–2 °C, anders vraag je installateur.",
    },
    "short_run": {
        "title": "Korte run",
        "what": "De compressor draaide {duration_min} min, korter dan {threshold_min} min.",
        "what_plain": "De compressor stopte na een korte run.",
        "todo": "Een korte run na het opwarmen van de boiler, rond een ontdooiing of bij zacht weer is normaal. Alleen als ze blijven komen: volg het advies bij de melding 'Herhaalde korte runs'.",
    },
    "short_cycling_pattern": {
        "title": "Herhaalde korte runs",
        "what": "{min_cycles} of meer korte runs binnen {window_min} min.",
        "what_plain": "Meerdere korte runs in korte tijd.",
        "todo": "Dit is pendelen: het kost rendement en slijt de compressor. Zet alle radiatorkranen en vloergroepen open en verlaag, als de kamers warmer zijn dan nodig, de offset van de stooklijn 1–2 °C; houdt het dagen aan, vraag dan je installateur.",
    },
    "short_off": {
        "title": "Korte pauze tussen runs",
        "what": "De compressor startte opnieuw na {off_min} min (minder dan {threshold_min} min).",
        "what_plain": "De compressor startte opnieuw na een korte pauze.",
        "todo": "De warmtepomp beschermt de compressor met een eigen minimale pauze; dit is vaak een wissel tussen verwarmen en warmtapwater of een ontdooiing. Alleen als het vaak gebeurt samen met korte runs: bekijk de compressorgrafiek.",
    },
    "ml_anomaly": {
        "title": "Ongewoon gedrag",
        "what": "Deze run gedroeg zich anders dan je warmtepomp gewoonlijk doet bij {outdoor} °C buiten.",
        "what_plain": "Deze run gedroeg zich anders dan je warmtepomp gewoonlijk doet bij dit weer.",
        "todo": "Meestal verklaard door een gewijzigde instelling, warmtapwater, een ontdooiing of een plotselinge weersomslag. Herhaalt het zich een paar dagen zonder zo'n reden, bekijk dan de grafieken of vraag je installateur.",
    },
    "setpoint_osc": {
        "title": "Gewenste aanvoertemperatuur wisselt steeds",
        "what": "De gewenste aanvoertemperatuur veranderde {osc_count} keer in {window_min} min.",
        "what_plain": "De gewenste aanvoertemperatuur verandert vaak.",
        "todo": "Meestal onschuldig: de stooklijn verschuift het doel een graad als de buitentemperatuur rond een stap schommelt, of de bediening past het aan op de kamertemperatuur. Wijzigt een app of Home Assistant-automatisering het doel of de offset, laat die dan minder vaak schakelen.",
    },
    "cop_degradation": {
        "title": "COP lager dan vorige week",
        "what": "De COP veranderde {week_pct} % t.o.v. vorige week bij dezelfde buitentemperatuur.",
        "what_plain": "De COP is lager dan vorige week bij dezelfde buitentemperatuur.",
        "todo": "Houd de buitenunit vrij van bladeren en sneeuw (krab nooit ijs van de lamellen: de unit ontdooit zelf) en controleer of de stooklijn of kamertemperatuur niet verhoogd is. Blijft de daling twee weken of blijft er ijs op de unit, vraag dan je installateur.",
    },
    "defrost_excessive": {
        "title": "Veel ontdooiingen",
        "what": "{count_7d} ontdooiingen in de laatste 7 dagen; tot {threshold} is normaal bij dit weer en {run_h_7d} u draaien.",
        "what_plain": "Meer ontdooiingen dan normaal voor het weer in de laatste 7 dagen.",
        "todo": "Vaak ontdooien is normaal bij vochtig weer tussen ongeveer −5 en +7 °C, maar niet bij 10 °C of warmer. Houd sneeuw en bladeren weg van de unit, zorg dat smeltwater weg kan en dat de koude lucht niet terug de unit in blaast (krab nooit ijs weg). Blijft er ijs op de unit of blijft dit terugkomen, vraag dan je installateur.",
    },
    "buh_excessive": {
        "title": "Elektrische bijverwarming vaak gebruikt",
        "what": "De elektrische bijverwarming (backup-heater) stond aan tijdens {buh_count_7d} runs in de laatste 7 dagen, een groot deel van de looptijd.",
        "what_plain": "De elektrische bijverwarming (backup-heater) stond een groot deel van de looptijd aan in de laatste 7 dagen.",
        "todo": "Normaal op zeer koude dagen, bij de wekelijkse desinfectie van de boiler en bij 'krachtig' warmtapwater; anders kost het stroom, want de warmtepomp maakt uit 1 kWh meerdere kWh warmte. Kijk op de Daikin-bediening of in de Onecta-app of er een storing of noodbedrijf is; zo niet en houdt het aan, vraag je installateur de instellingen van de backup-heater na te kijken.",
    },
    "source_stale": {
        "title": "Geen data van ESPAltherma",
        "what": "Geen update sinds {age_s} s. Runs, COP en meldingen staan stil.",
        "what_plain": "ESPAltherma stuurt geen data meer. Runs, COP en meldingen staan stil.",
        "todo": "De warmtepomp verwarmt gewoon door; alleen de bewaking staat stil, en een korte herstart van de ESP lost zichzelf meestal op. Duurt het langer, controleer dan of het ESPAltherma-apparaat stroom en wifi heeft, en of de MQTT- of ESPHome-koppeling in Home Assistant werkt.",
    },
    "cop_physically_impossible": {
        "title": "Onmogelijke COP-waarde",
        "what": "{count} natuurkundig onmogelijke COP-waarde(n) werden vandaag genegeerd.",
        "what_plain": "Natuurkundig onmogelijke COP-waarden werden vandaag genegeerd.",
        "todo": "Meestal een kWh-meter die te weinig meet (alleen de binnenunit gemeten, een ontbrekende fase, kW gelezen als W) of een verkeerde debietwaarde. Controleer de kWh-meter in de opties van de integratie (Apparaat); één waarde bij een start of stop mag je negeren.",
    },
    "missing_attributes": {
        "title": "Waarden ontbreken bij ESPAltherma",
        "what": "{missing_count} waarde(n) worden niet gestuurd: {missing_list}.",
        "what_plain": "Sommige waarden worden niet door ESPAltherma gestuurd.",
        "todo": "De detectie werkt door waar het kan. Voor alle functies: zet deze waarden aan in je ESPAltherma-definitie en flash opnieuw.",
    },
    "dhw_pendulum": {
        "title": "Boiler warmt vaak op",
        "what": "{dhw_cph} boileropwarmingen in het laatste uur (grens {target_cph}).",
        "what_plain": "Veel boileropwarmingen in het laatste uur.",
        "todo": "Meerdere opwarmingen in een uur zijn normaal terwijl er warm water wordt gebruikt (douchen, bad). Gebeurt het zonder veel verbruik, vraag dan je installateur de hysterese voor herverwarmen van de boiler en de warmtapwatermodus na te kijken.",
    },
    "high_cycle_rate": {
        "title": "Zeer veel starts dit uur",
        "what": "{cph} starts in het laatste uur, ruim boven je doel van {target_cph}.",
        "what_plain": "Zeer veel starts in het laatste uur.",
        "todo": "Veel meer starts dan je grens kosten rendement en slijten de compressor. Controleer of radiatorkranen en vloergroepen open staan en of geen thermostaat of automatisering de warmtepomp aan en uit schakelt; houdt het aan, vraag dan je installateur.",
    },
    "cop_vs_datasheet_low": {
        "title": "COP onder de datasheet",
        "what": "De COP wijkt {pct_diff} % af van de datasheetwaarde ({cop_expected}) bij dit weer.",
        "what_plain": "De COP ligt onder de datasheetwaarde bij dit weer.",
        "todo": "Vaak een meeteffect: bij lage warmtevraag is het temperatuurverschil klein, en je meter kan de circulatiepomp en de besturing meetellen. Blijft de COP ook op koudere dagen laag, vraag dan je installateur de unit na te kijken.",
    },
    "db_retention_warning": {
        "title": "Database wordt niet opgeruimd",
        "what": "{stale_alerts} oude meldingen en {stale_cycles} oude runs zijn niet verwijderd.",
        "what_plain": "Oude meldingen en runs zijn niet verwijderd.",
        "todo": "Het nachtelijke opruimen (03:00) is niet gelopen. Controleer of opruimen aan staat in de opties van de integratie en herstart Home Assistant; komt dit terug, kijk dan in het logboek naar Daikin Cycle ML-fouten.",
    },
    "kmeans_retrain_stale": {
        "title": "Leren gepauzeerd",
        "what": "Het wekelijkse leren van je runpatronen is al {hours_since_ok} u niet afgerond.",
        "what_plain": "Het wekelijkse leren van je runpatronen is niet afgerond.",
        "todo": "Geen actie nodig als je warmtepomp de laatste tijd weinig runs had. Anders: herstart Home Assistant.",
    },
    "energy_daily_anomaly": {
        "title": "Hoog stroomverbruik vandaag",
        "what": "Het stroomverbruik van vandaag ({today_el_kwh} kWh) ligt ver boven je gewone dag ({baseline_el_mean} kWh).",
        "what_plain": "Het stroomverbruik van vandaag ligt ver boven je gewone dag.",
        "todo": "Vaak een koude dag, een hogere kamertemperatuur, extra warmtapwater of de backup-heater. Geldt geen van deze, bekijk dan de grafieken van vandaag.",
    },
}

# Titles of the two messages built outside build_rich_alert
# (status_report.build_cop_low_message / build_stooklijn_message).
OTHER_TITLES = {"cop_low": "Lage dag-COP", "stooklijn_advies": "Stooklijn-advies"}

KMEANS_REASONS = {
    "too_few": "Nog niet genoeg runs om van te leren. Geen actie nodig: het leren hervat vanzelf.",
    "fetch_failed": "De database kon niet gelezen worden. Herstart Home Assistant; komt het terug, kijk dan in het logboek.",
    "kmeans_failed": "De leerstap is mislukt. Meld het op GitHub (Daikin Cycle ML issues).",
    "no_db": "De database van de integratie is niet geladen. Herstart Home Assistant.",
    None: "Het wekelijkse leren is niet gelopen. Herstart Home Assistant.",
}
