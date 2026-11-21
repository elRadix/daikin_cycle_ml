"""Alert texts, French (#463). Same keys and placeholders as _en / _nl."""
from __future__ import annotations

LEVELS = {
    "info": "Aucune action requise",
    "watch": "À surveiller",
    "act": "Action requise",
}

WORDS = {"see": "Voir :", "or": " · ou ", "test": "TEST"}

CARDS = {"eff": "carte Rendement", "daily": "carte Résumé quotidien"}
TABS = {
    "eff": {"live": "Direct", "today": "Aujourd'hui", "eff": "Rendement", "curve": "Loi d'eau", "advice": "Conseil"},
    "daily": {"today": "Aujourd'hui", "overview": "Synthèse", "quality": "Qualité", "cycles": "Cycles",
              "duration": "Durée", "events": "Événements"},
}
GRAPHS = {
    "water": "Températures d'eau", "compressor": "Compresseur", "hydraulics": "Débit et ΔT",
    "comfort": "Confort", "strip": "Appoint et dégivrage", "balance": "Bilan thermique",
}

ALERTS = {
    "pendulum_hourly": {
        "title": "Beaucoup de démarrages cette heure",
        "what": "{cph} démarrages du compresseur dans la dernière heure (votre limite : {target_cph}).",
        "what_plain": "Beaucoup de démarrages du compresseur dans la dernière heure.",
        "todo": "Par temps doux, la puissance minimale de la pompe à chaleur peut dépasser le besoin de la maison : un peu de marche/arrêt est alors normal, aussi après une production d'ECS ou un dégivrage. Si cela continue, ouvrez tous les robinets de radiateurs et boucles de plancher ; si les pièces sont plus chaudes que nécessaire, baissez le décalage de la loi d'eau de 1–2 °C sur la commande Daikin ou l'app Onecta.",
    },
    "pendulum_daily": {
        "title": "Beaucoup de cycles aujourd'hui",
        "what": "{cycles_today} cycles aujourd'hui (votre limite : {target_cpd}).",
        "what_plain": "Beaucoup de cycles aujourd'hui.",
        "todo": "De longs cycles réguliers sont les plus efficaces. Si cela arrive chaque jour, ouvrez tous les robinets de radiateurs et boucles de plancher ; si les pièces sont plus chaudes que nécessaire, baissez le décalage de la loi d'eau de 1–2 °C, sinon demandez à votre installateur.",
    },
    "short_run": {
        "title": "Cycle court",
        "what": "Le compresseur a tourné {duration_min} min, moins de {threshold_min} min.",
        "what_plain": "Le compresseur s'est arrêté après un cycle court.",
        "todo": "Un cycle court après une production d'ECS, autour d'un dégivrage ou par temps doux est normal. Seulement s'ils se répètent : suivez le conseil de l'alerte « Cycles courts répétés ».",
    },
    "short_cycling_pattern": {
        "title": "Cycles courts répétés",
        "what": "{min_cycles} cycles courts ou plus en {window_min} min.",
        "what_plain": "Plusieurs cycles courts en peu de temps.",
        "todo": "C'est du fonctionnement en cycles courts : il coûte du rendement et use le compresseur. Ouvrez tous les robinets de radiateurs et boucles de plancher et, si les pièces sont plus chaudes que nécessaire, baissez le décalage de la loi d'eau de 1–2 °C ; si cela dure plusieurs jours, demandez à votre installateur.",
    },
    "short_off": {
        "title": "Pause courte entre deux cycles",
        "what": "Le compresseur a redémarré après {off_min} min (moins de {threshold_min} min).",
        "what_plain": "Le compresseur a redémarré après une courte pause.",
        "todo": "La pompe à chaleur protège son compresseur par sa propre pause minimale : c'est souvent un passage entre chauffage et ECS ou un dégivrage. Seulement si cela arrive souvent avec des cycles courts, regardez le graphique du compresseur.",
    },
    "ml_anomaly": {
        "title": "Comportement inhabituel",
        "what": "Ce cycle s'est comporté autrement que d'habitude pour votre pompe à chaleur à {outdoor} °C extérieur.",
        "what_plain": "Ce cycle s'est comporté autrement que d'habitude pour votre pompe à chaleur par ce temps.",
        "todo": "Souvent expliqué par un réglage modifié, l'ECS, un dégivrage ou un changement brusque de temps. Si cela se répète plusieurs jours sans raison de ce type, regardez les graphiques ou demandez à votre installateur.",
    },
    "setpoint_osc": {
        "title": "La consigne de départ change sans cesse",
        "what": "La consigne de température de départ a changé {osc_count} fois en {window_min} min.",
        "what_plain": "La consigne de température de départ change souvent.",
        "todo": "En général sans gravité : la loi d'eau déplace la consigne d'un degré quand la température extérieure oscille autour d'un palier, ou la commande l'ajuste selon la température intérieure. Si une app ou une automatisation Home Assistant modifie la consigne ou le décalage, faites-la changer moins souvent.",
    },
    "cop_degradation": {
        "title": "COP plus bas que la semaine dernière",
        "what": "Le COP a varié de {week_pct} % par rapport à la semaine dernière à même température extérieure.",
        "what_plain": "Le COP est plus bas que la semaine dernière à même température extérieure.",
        "todo": "Gardez l'unité extérieure libre de feuilles et de neige (ne grattez jamais la glace des ailettes : l'unité dégivre seule) et vérifiez que la loi d'eau ou la température intérieure n'a pas été relevée. Si la baisse dure deux semaines ou si la glace reste sur l'unité, demandez à votre installateur.",
    },
    "defrost_excessive": {
        "title": "Beaucoup de dégivrages",
        "what": "{count_7d} dégivrages ces 7 derniers jours ; jusqu'à {threshold} sont normaux pour ce temps et {run_h_7d} h de fonctionnement.",
        "what_plain": "Plus de dégivrages que la normale pour la météo ces 7 derniers jours.",
        "todo": "Des dégivrages fréquents sont normaux par temps humide entre environ −5 et +7 °C, mais pas à 10 °C ou plus. Écartez neige et feuilles de l'unité, veillez à ce que l'eau de fonte s'évacue et que l'air froid ne soit pas réaspiré par l'unité (ne grattez jamais la glace). Si la glace reste sur l'unité ou si cela continue, demandez à votre installateur.",
    },
    "buh_excessive": {
        "title": "Appoint électrique souvent utilisé",
        "what": "L'appoint électrique était en marche pendant {buh_count_7d} cycles ces 7 derniers jours, une grande part du temps de fonctionnement.",
        "what_plain": "L'appoint électrique était en marche une grande part du temps de fonctionnement ces 7 derniers jours.",
        "todo": "Normal par grand froid, pour la désinfection hebdomadaire du ballon et en ECS « puissante » ; sinon il coûte de l'électricité, car la pompe à chaleur produit plusieurs kWh de chaleur avec 1 kWh. Vérifiez sur la commande Daikin ou l'app Onecta s'il y a une erreur ou un mode secours ; sinon, et si cela continue, demandez à votre installateur de contrôler les réglages de l'appoint.",
    },
    "source_stale": {
        "title": "Plus de données d'ESPAltherma",
        "what": "Aucune mise à jour depuis {age_s} s. Cycles, COP et alertes sont en pause.",
        "what_plain": "ESPAltherma n'envoie plus de données. Cycles, COP et alertes sont en pause.",
        "todo": "La pompe à chaleur continue de chauffer normalement ; seule la surveillance est en pause, et un bref redémarrage de l'ESP se règle en général tout seul. Si cela dure, vérifiez que le module ESPAltherma est alimenté et connecté au Wi-Fi, et que sa liaison MQTT ou ESPHome dans Home Assistant fonctionne.",
    },
    "cop_physically_impossible": {
        "title": "Valeur de COP impossible",
        "what": "{count} valeur(s) de COP physiquement impossibles ont été ignorées aujourd'hui.",
        "what_plain": "Des valeurs de COP physiquement impossibles ont été ignorées aujourd'hui.",
        "todo": "En général un compteur d'énergie qui mesure trop peu (seule l'unité intérieure mesurée, une phase manquante, des kW lus comme des W) ou une valeur de débit fausse. Vérifiez le compteur dans les options de l'intégration (Appareil) ; une valeur isolée au démarrage ou à l'arrêt peut être ignorée.",
    },
    "missing_attributes": {
        "title": "Valeurs manquantes d'ESPAltherma",
        "what": "{missing_count} valeur(s) ne sont pas envoyées : {missing_list}.",
        "what_plain": "Certaines valeurs ne sont pas envoyées par ESPAltherma.",
        "todo": "La détection continue là où elle le peut. Pour toutes les fonctions, activez ces valeurs dans votre définition ESPAltherma et reflashez le module.",
    },
    "dhw_pendulum": {
        "title": "Le ballon d'ECS se réchauffe souvent",
        "what": "{dhw_cph} relances de l'ECS dans la dernière heure (limite {target_cph}).",
        "what_plain": "Beaucoup de relances de l'ECS dans la dernière heure.",
        "todo": "Plusieurs relances en une heure sont normales pendant que l'on puise de l'eau chaude (douches, bain). Si cela arrive sans grande consommation, demandez à votre installateur de vérifier l'hystérésis de réchauffage du ballon et le mode ECS.",
    },
    "high_cycle_rate": {
        "title": "Très nombreux démarrages cette heure",
        "what": "{cph} démarrages dans la dernière heure, bien au-dessus de votre objectif de {target_cph}.",
        "what_plain": "Très nombreux démarrages dans la dernière heure.",
        "todo": "Bien plus de démarrages que votre limite coûtent du rendement et usent le compresseur. Vérifiez que robinets de radiateurs et boucles de plancher sont ouverts et qu'aucun thermostat ou automatisation ne met la pompe à chaleur en marche et à l'arrêt ; si cela continue, demandez à votre installateur.",
    },
    "cop_vs_datasheet_low": {
        "title": "COP inférieur à la fiche technique",
        "what": "Le COP s'écarte de {pct_diff} % de la valeur de la fiche ({cop_expected}) par ce temps.",
        "what_plain": "Le COP est inférieur à la valeur de la fiche par ce temps.",
        "todo": "Souvent un effet de mesure : à faible besoin de chaleur, l'écart de température est faible, et votre compteur peut inclure le circulateur et l'électronique. S'il reste bas aussi par temps plus froid, demandez à votre installateur de contrôler l'unité.",
    },
    "db_retention_warning": {
        "title": "Nettoyage de la base inactif",
        "what": "{stale_alerts} anciennes alertes et {stale_cycles} anciens cycles n'ont pas été supprimés.",
        "what_plain": "D'anciennes alertes et d'anciens cycles n'ont pas été supprimés.",
        "todo": "Le nettoyage de nuit (03:00) n'a pas tourné. Vérifiez que le nettoyage est activé dans les options de l'intégration et redémarrez Home Assistant ; si cela revient, cherchez les erreurs de Daikin Cycle ML dans le journal.",
    },
    "kmeans_retrain_stale": {
        "title": "Apprentissage en pause",
        "what": "L'apprentissage hebdomadaire de vos cycles n'a pas abouti depuis {hours_since_ok} h.",
        "what_plain": "L'apprentissage hebdomadaire de vos cycles n'a pas abouti.",
        "todo": "Aucune action requise si votre pompe à chaleur a eu peu de cycles récemment. Sinon, redémarrez Home Assistant.",
    },
    "energy_daily_anomaly": {
        "title": "Consommation élevée aujourd'hui",
        "what": "La consommation du jour ({today_el_kwh} kWh) dépasse largement votre journée habituelle ({baseline_el_mean} kWh).",
        "what_plain": "La consommation du jour dépasse largement votre journée habituelle.",
        "todo": "Souvent une journée froide, une température intérieure plus élevée, plus d'ECS ou l'appoint électrique. Si rien de cela ne s'applique, regardez les graphiques du jour.",
    },
}

# Titles of the two messages built outside build_rich_alert
# (status_report.build_cop_low_message / build_stooklijn_message).
OTHER_TITLES = {"cop_low": "COP du jour bas", "stooklijn_advies": "Conseil de loi d'eau"}

KMEANS_REASONS = {
    "too_few": "Pas encore assez de cycles pour apprendre. Aucune action requise : l'apprentissage reprend seul.",
    "fetch_failed": "La base de données n'a pas pu être lue. Redémarrez Home Assistant ; si cela revient, consultez le journal.",
    "kmeans_failed": "L'étape d'apprentissage a échoué. Merci de le signaler sur GitHub (Daikin Cycle ML issues).",
    "no_db": "La base de données de l'intégration n'est pas chargée. Redémarrez Home Assistant.",
    None: "L'apprentissage hebdomadaire n'a pas tourné. Redémarrez Home Assistant.",
}
