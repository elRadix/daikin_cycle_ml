"""Build translations/fr.json from en.json (azsono03 fork).

Every string present in en.json gets a French value; the structure is
copied from en.json so any key added upstream stays visible (falls back
to the English text and is listed on stdout so it can be translated).
"""
import copy
import json
import sys

base = sys.argv[1] if len(sys.argv) > 1 else "custom_components/daikin_cycle_ml"
en = json.load(open(f"{base}/translations/en.json", encoding="utf-8"))
fr = copy.deepcopy(en)

T = {}  # path tuple -> french


def put(path, value):
    T[tuple(path.split("/"))] = value


def block(prefix, mapping):
    for k, v in mapping.items():
        put(f"{prefix}/{k}", v)


# ------------------------------------------------------------------ config
C = "config/step"
block(f"{C}/model_custom", {
    "title": "Correspondance personnalisée des valeurs",
    "description": "Correspondance JSON facultative entre les clés standard et les noms de vos valeurs. Donnez un objet JSON (exemple dans le README). Laisser vide pour les valeurs par défaut.",
    "data/custom_attribute_map": "Correspondance des valeurs (JSON)",
    "data_description/custom_attribute_map": "Objet JSON qui associe les clés standard aux noms de vos valeurs. Le format exact est dans la documentation.",
})
block(f"{C}/model_custom_info", {
    "title": "Pompe à chaleur personnalisée",
    "description": "Votre pompe à chaleur ne fait pas partie des modèles Daikin intégrés.\n\nUn modèle personnalisé reprend les réglages du **Profil de base** (valeurs sûres). Vous pourrez ajuster les seuils de détection, les limites de confort et l'analyse du COP plus tard dans les options de l'intégration.\n\nLa page suivante fait correspondre les noms de valeurs ESPAltherma aux clés de l'intégration.",
    "data/custom_datasheet_json": "Caractéristiques de la PAC (JSON, facultatif)",
    "data_description/custom_datasheet_json": "Caractéristiques facultatives de votre PAC. Laisser vide pour le Profil de base.\n\n**Champs obligatoires :** `family` (texte), `kw` (nombre), `lwt_min` (nombre), `lwt_max` (nombre), `nom_cop` (nombre).\n\n**Champs facultatifs :** `bivalent` (booléen), `buh_kw` (nombre), `refrigerant` (R32 / R290 / R410A), `min_modulation_kw` (nombre), `max_flow_lmin` (nombre), `noise_db` (nombre).\n\n**Points de COP facultatifs :** liste d'objets avec les clés `label`, `t_out`, `t_lwc`, `cop`.\n\n**Exemple minimal :**\n\n    {spec_example_min}\n\n**Exemple avec points de COP :**\n\n    {spec_example_full}",
})
block(f"{C}/attributes", {
    "title": "Vérification des valeurs",
    "description": "Valeurs principales trouvées sur la source : **{present} / {total}**.\n\n**Présentes :**\n{present_list}\n\n**Manquantes :**\n{missing_list}\n\n{hybrid_hint}",
})
block(f"{C}/cycle", {
    "title": "Détection des cycles",
    "description": "Seuils qui décident quand le compresseur est compté en marche.\n\n- **Seuil de vitesse compresseur** (3 par défaut) : en marche quand la vitesse (tr/s) ≥ ce seuil. Augmenter pour ignorer les pointes brèves.\n- **Capteur de puissance** (facultatif) : utilisé en secours quand la vitesse n'est pas disponible.\n- **Seuil de puissance de secours** (200 W par défaut) : plus bas = plus sensible.",
    "data/compressor_rps_threshold": "Seuil de vitesse compresseur (tr/s)",
    "data/power_sensor_entity": "Capteur de puissance (secours, facultatif)",
    "data/fallback_power_threshold_w": "Seuil de puissance de secours",
    "data/indoor_temp_sensor": "Capteur de température intérieure",
    "data_description/compressor_rps_threshold": "Compresseur en marche quand la vitesse ≥ cette valeur. 3 par défaut. Augmenter pour ignorer les pointes brèves.",
    "data_description/power_sensor_entity": "Facultatif. Utilisé en secours quand la vitesse est absente ou nulle. Laisser vide pour désactiver.",
    "data_description/fallback_power_threshold_w": "Seuil de puissance (W) du capteur de secours. 200 par défaut. Plus bas = plus sensible.",
    "data_description/indoor_temp_sensor": "Capteur facultatif de température intérieure (utilisé par l'apprentissage et les garde-fous de confort).",
})
block(f"{C}/pendulum", {
    "title": "Seuils de cycles courts",
    "data/short_run_threshold_min": "Seuil de marche courte",
    "data/short_off_threshold_min": "Seuil d'arrêt court",
    "data/pendulum_cycles_per_day": "Cycles par jour avant alerte",
    "data/dhw_pendulum_cycles_per_hour": "Cycles d'eau chaude par heure",
    "description": "En dessous de ces valeurs, un cycle est compté comme « court ». Plus bas = plus strict, plus d'alertes.\n\n- **Marche courte** (20 min par défaut) : cycles plus courts signalés.\n- **Arrêt court** (5 min par défaut) : arrêts plus courts signalés.\n- **Cycles par jour** (35-40 par défaut) : nombre quotidien qui déclenche une alerte.\n- **Cycles d'eau chaude par heure** (3 par défaut) : alerte propre à l'eau chaude.",
    "data_description/short_run_threshold_min": "Les cycles plus courts sont des « marches courtes ». 20 min par défaut. Plus bas = plus strict.",
    "data_description/short_off_threshold_min": "Les arrêts plus courts sont des « arrêts courts ». 5 min par défaut. Plus bas = plus strict.",
    "data_description/pendulum_cycles_per_day": "Nombre de cycles par jour qui déclenche une alerte. 35-40 par défaut. Plus bas = plus d'alertes.",
    "data_description/dhw_pendulum_cycles_per_hour": "Cycles d'eau chaude par heure qui déclenchent une alerte. 3 par défaut.",
})
block(f"{C}/quality", {
    "title": "Seuils de qualité",
    "data/good_run_threshold_min": "Durée de bon cycle",
    "data/good_dt_threshold_k": "Écart départ/retour minimal",
    "data/good_off_threshold_min": "Durée d'arrêt minimale",
    "data/target_cycles_per_day": "Objectif de cycles par jour",
    "description": "Seuils utilisés pour noter un cycle de 0 à 100. Atteindre un seuil évite une pénalité.\n\n- **Bon cycle** (45 min par défaut) : durée ≥ ce seuil = note maximale. En dessous : −30 points.\n- **Écart départ/retour** (5,0 K par défaut) : écart minimal pour la note maximale. En dessous : −20 points.\n- **Arrêt minimal** (20 min par défaut) : arrêt minimal pour la note maximale. En dessous : −20 points.\n- **Objectif de cycles/jour** (8 par défaut) : utilisé dans les conseils.",
    "data_description/good_run_threshold_min": "Une durée égale ou supérieure donne la note maximale. 45 min par défaut. En dessous = −30 points.",
    "data_description/good_dt_threshold_k": "Écart départ/retour minimal (K) pour la note maximale. 5,0 K par défaut. En dessous = −20 points.",
    "data_description/good_off_threshold_min": "Arrêt minimal pour la note maximale. 20 min par défaut. En dessous = −20 points.",
    "data_description/target_cycles_per_day": "Objectif de cycles par jour pour un fonctionnement efficace. 8 par défaut. Utilisé dans les conseils.",
})
block(f"{C}/notifications", {
    "title": "Notifications",
    "data/persistent_enabled": "Notifications persistantes",
    "data/status_update_enabled": "Bilans périodiques",
    "data/status_update_interval_hours": "Intervalle des bilans (heures)",
    "data/notify_emoji_enabled": "Émojis dans les notifications",
    "data/notify_service": "Destinataire des notifications",
    "data/quiet_hours_enabled": "Heures calmes",
    "data/quiet_hours_start": "Début des heures calmes",
    "data/quiet_hours_end": "Fin des heures calmes",
    "description": "Comment et quand les alertes sont envoyées.\n\n- **Notifications persistantes** : alertes dans la barre latérale.\n- **Destinataire** (facultatif) : par ex. `notify.mobile_app_telephone`.\n- **Heures calmes** : pas d'alerte non critique pendant cette plage (22:00–07:00 par défaut).",
    "data_description/persistent_enabled": "Afficher les alertes en notifications persistantes dans la barre latérale.",
    "data_description/notify_service": "Choisir une entité de notification (recommandé) ou un ancien service notify. Laisser vide pour ne rien envoyer sur le téléphone.",
    "data_description/quiet_hours_enabled": "Pas d'alerte non critique pendant les heures calmes.",
    "data_description/quiet_hours_start": "Début des heures calmes, HH:MM (24 h). 22:00 par défaut.",
    "data_description/quiet_hours_end": "Fin des heures calmes, HH:MM (24 h). 07:00 par défaut.",
    "data_description/status_update_enabled": "Envoyer régulièrement un bilan sur plusieurs lignes.",
    "data_description/status_update_interval_hours": "Heures entre deux bilans (1-168).",
    "data_description/notify_emoji_enabled": "Commencer les notifications par un émoji d'état ou de gravité.",
})
block(f"{C}/finalize", {
    "title": "Confirmation",
    "description": "Modèle : {model}. Source : {source}. Valider pour créer l'intégration.",
})
block(f"{C}/reconfigure", {
    "title": "Reconfigurer Daikin Cycle ML",
    "description": "Choisir l'étendue des changements.\n\n- **Rapide** : source et modèle seulement.\n- **Assistant complet** : tous les réglages, avec les valeurs actuelles préremplies.",
    "menu_options/reconfigure_basic": "Source et modèle seulement (rapide)",
    "menu_options/reconfigure_full": "Assistant complet (tous les réglages)",
})
block(f"{C}/reconfigure_basic", {
    "title": "Source et modèle",
    "description": "Changer la source ou le modèle de PAC. Les autres réglages ne bougent pas.",
    "data/source_sensor": "Capteur source",
    "data/model": "Modèle de PAC",
    "data_description/source_sensor": "Capteur ESPAltherma qui fournit les valeurs de la PAC. Habituellement : sensor.althermasensors.",
    "data_description/model": "Votre modèle Daikin, qui fixe les seuils par défaut. Choisir « Personnalisé » pour fournir vos propres caractéristiques.",
})
block(f"{C}/reconfigure_full", {
    "title": "Assistant complet",
    "description": "Relancer tout l'assistant. Les valeurs actuelles sont préremplies.",
})
block(f"{C}/map_attributes", {
    "title": "Correspondance des valeurs obligatoires",
    "description": "Associer chaque valeur standard au nom correspondant sur votre capteur. Laisser vide si le nom standard existe déjà.\n\nLe capteur fournit **{available_count}** valeurs.\n\nExemples de noms disponibles :\n{available_list}\n\nNon trouvées : {bad_list}",
})
for k in en["config"]["step"]["map_attributes"]["data_description"]:
    if k.startswith(("Boiler", "Hybrid")):
        put(f"{C}/map_attributes/data_description/{k}",
            f"Nom de la valeur « {k} » sur le capteur (hybride seulement — laisser vide si absente).")
    else:
        put(f"{C}/map_attributes/data_description/{k}",
            f"Nom sur votre capteur de la valeur standard « {k} ». Laisser vide si le nom standard existe déjà.")
block(f"{C}/diagnose", {
    "title": "Diagnostic de l'import automatique",
    "description": "Rapport de détection automatique des valeurs.\n\n**Correspondances :**\n{report_lines}\n\n**Avertissements :**\n{warnings}\n\n**Valeurs standard manquantes :** {missing_count}\n\nVérifier avant de continuer. Les valeurs non trouvées pourront être associées à la main à l'étape suivante.",
})
block(f"{C}/attribute_mapping", {
    "title": "Correspondance des valeurs",
    "description": "Votre ESPAltherma peut utiliser des noms différents des clés de l'intégration. Choisir comment les associer.\n\n**JSON** : coller un objet JSON qui associe les clés standard à vos noms ESPAltherma. Pour utilisateurs avancés.\n\n**Manuel** : un champ par valeur. Plus simple si vous préférez un formulaire.",
    "data/mapping_mode": "Mode de correspondance",
    "data_description/mapping_mode": "JSON pour les utilisateurs avancés (un seul objet), Manuel pour un formulaire valeur par valeur.",
})
block(f"{C}/attribute_mapping_advanced", {
    "title": "Correspondance avancée",
    "description": "Coller un objet JSON qui associe les clés standard à vos noms ESPAltherma. Laisser vide pour les valeurs du profil.",
    "data/custom_attribute_map": "Correspondance des valeurs (JSON)",
    "data_description/custom_attribute_map": "Objet JSON qui associe les clés standard aux noms de vos valeurs. Le format exact est dans la documentation.",
})
block(f"{C}/model", {
    "title": "Configuration de Daikin Cycle ML",
    "description": "Choisir le capteur source ESPAltherma, le modèle de PAC et la façon d'associer les valeurs.\n\n- **Capteur source** : doit fournir les 12 valeurs ESPAltherma obligatoires (mode « une seule entité »). En mode entités séparées, choisir n'importe quelle entité `espaltherma_*`.\n- **Modèle** : fixe les seuils par défaut.\n- **Mode de correspondance** : Automatique utilise les noms standard, Manuel permet de les associer vous-même.",
    "data/source_sensor": "Capteur source",
    "data/model": "Modèle de PAC",
    "data/attribute_mode": "Mode de correspondance",
    "data_description/source_sensor": "Capteur ESPAltherma qui fournit les 12 valeurs obligatoires. Habituellement : sensor.althermasensors.",
    "data_description/model": "Votre modèle Daikin, qui fixe les seuils par défaut. Choisir « Personnalisé » pour fournir vos propres caractéristiques.",
    "data_description/attribute_mode": "Automatique utilise les noms standard d'ESPAltherma. Manuel permet d'associer chaque valeur au nom de votre capteur.",
})
block(f"{C}/user", {
    "title": "Daikin Cycle ML — famille de modèle",
    "description": "Choisir la famille de votre Daikin Altherma : c'est le début de la référence du groupe extérieur (ex. ERGA, EPRA, EKHBRD). Le modèle exact se choisit à l'écran suivant.\n\n- **Profil de base** : réglages sûrs quand le modèle exact est inconnu.\n- **Personnalisé** : vous fournissez vos propres caractéristiques.\n\n**Détecté :** entité unique = {mono_found}, entités ESPAltherma v2 = {v2_count}.\n**Type de source conseillé :** `{suggestion}`.",
    "data/family": "Famille de modèle",
    "data/source_type": "Type de source ESPAltherma",
    "data_description/family": "Début de la référence du groupe extérieur. Exemple : ERGA, EPRA, EKHBRD.",
    "data_description/source_type": "Façon dont ESPAltherma envoie ses données. « Entité unique » pour le capteur classique, « Entités séparées » pour ESPAltherma v2 (une entité par valeur). « Auto » détecte au démarrage.",
})
block(f"{C}/individual_prefix", {
    "title": "Préfixe des entités ESPAltherma v2",
    "description": "Préfixe d'entity_id sous lequel ESPAltherma v2 publie ses capteurs. Par défaut : `sensor.espaltherma_`.",
    "data/individual_prefix": "Préfixe des entités",
    "data_description/individual_prefix": "Préfixe avec le domaine, par ex. `sensor.espaltherma_`.",
})
block(f"{C}/individual_review", {
    "title": "Vérification des valeurs ESPAltherma v2",
    "description": "**{matched}/{total}** valeurs obligatoires trouvées. Entités découvertes : {discovered}.{missing_block}{collision_block}\n\nContinuer pour choisir le modèle Daikin. La correspondance reste modifiable dans les options.",
})
block("config/error", {
    "entity_not_found": "Capteur introuvable",
    "missing_attributes": "Il manque au capteur une ou plusieurs valeurs ESPAltherma obligatoires. La liste est dans la description ; vous pouvez aussi passer en correspondance manuelle.",
    "invalid_json": "JSON invalide",
    "attribute_not_found": "Un ou plusieurs noms associés n'existent pas sur le capteur source.",
    "required_attrs_unmapped": "Une ou plusieurs valeurs obligatoires n'ont ni correspondance ni nom standard sur le capteur.",
    "source_offline": "Le capteur ESPAltherma est indisponible. Attendre 30 à 60 s qu'il revienne puis réessayer.",
    "source_empty": "Le capteur ESPAltherma n'a pas encore de données. Attendre la prochaine mise à jour puis réessayer.",
})
block("config/abort", {
    "already_configured": "Déjà configuré",
    "reconfigure_successful": "Reconfiguration réussie",
    "reconfigure_hybrid_change": "Reconfiguration réussie. Le modèle est passé entre hybride (EVLQ) et non hybride : l'historique des cycles est conservé tel quel, les nouveaux cycles utiliseront la nouvelle détection chaudière.",
})

# ----------------------------------------------------------------- options
O = "options/step"
block(f"{O}/init", {
    "title": "Options de Daikin Cycle ML",
    "description": "Choisir la partie à modifier.",
    "menu_options/device": "Appareil",
    "menu_options/pendulum": "Cycles courts",
    "menu_options/quality_ml": "Qualité et apprentissage",
    "menu_options/notifications": "Notifications",
    "menu_options/advanced": "Avancé",
    "menu_options/cop_calc": "Calcul du COP",
    "menu_options/test_notification": "Envoyer une notification de test",
    "menu_options/test_all_notifications": "Envoyer TOUTES les notifications de test",
    "menu_option_descriptions/device": "Capteurs, seuils de détection et confort",
    "menu_option_descriptions/pendulum": "Cycles courts et consigne instable",
    "menu_option_descriptions/quality_ml": "Seuils de notation de la qualité",
    "menu_option_descriptions/notifications": "Destinataire, heures calmes, groupes d'alertes, langue",
    "menu_option_descriptions/advanced": "Conservation, bilan quotidien, compactage",
    "menu_option_descriptions/cop_calc": "Alimentation et puissance de l'appoint pour le COP",
    "menu_option_descriptions/test_notification": "Envoyer un exemple d'alerte au destinataire",
    "menu_option_descriptions/test_all_notifications": "Un clic — envoie un exemple de chaque alerte (sans filtres)",
})
block(f"{O}/device", {
    "title": "Appareil",
    "description": "Capteurs et seuils de détection.\n\nCapteur source : {source_sensor}\nModèle : {model}\n\nPour changer la source ou le modèle, utiliser Reconfigurer.",
    "sections/sensors/name": "Capteurs",
    "sections/sensors/data/power_sensor_entity": "Capteur de puissance (secours)",
    "sections/sensors/data/cop_sensor_entity": "Capteur de COP",
    "sections/sensors/data/indoor_temp_sensor": "Capteur de température intérieure",
    "sections/sensors/data_description/power_sensor_entity": "Facultatif. Utilisé en secours quand la vitesse du compresseur est absente.",
    "sections/sensors/data_description/cop_sensor_entity": "Capteur de COP global, par ex. sensor.altherma_global_cop. Utilisé pour les échantillons de COP.",
    "sections/sensors/data_description/indoor_temp_sensor": "Facultatif. Utilisé par l'apprentissage et les garde-fous de confort.",
    "sections/detection/name": "Détection",
    "sections/detection/data/compressor_rps_threshold": "Seuil de vitesse compresseur (tr/s)",
    "sections/detection/data/fallback_power_threshold_w": "Seuil de puissance de secours",
    "sections/detection/data_description/compressor_rps_threshold": "Compresseur en marche quand la vitesse ≥ cette valeur. 3 par défaut.",
    "sections/detection/data_description/fallback_power_threshold_w": "Seuil de puissance (W) du capteur de secours. 200 par défaut.",
    "sections/comfort/name": "Confort",
    "sections/comfort/data/comfort_min_c": "Température intérieure minimale (°C)",
    "sections/comfort/data/comfort_max_c": "Température intérieure maximale (°C)",
    "sections/comfort/data_description/comfort_min_c": "Aucune baisse du départ d'eau ne sera conseillée en dessous de cette température intérieure. 20 °C par défaut.",
    "sections/comfort/data_description/comfort_max_c": "Aucune hausse du départ d'eau ne sera conseillée au-dessus de cette température intérieure. 24 °C par défaut.",
})
block(f"{O}/pendulum", {
    "title": "Cycles courts",
    "description": "Ce qui compte comme un mauvais cycle.",
    "sections/run_off/name": "Seuils de marche et d'arrêt",
    "sections/run_off/data/short_run_threshold_min": "Seuil de marche courte",
    "sections/run_off/data/short_off_threshold_min": "Seuil d'arrêt court",
    "sections/run_off/data_description/short_run_threshold_min": "Les cycles plus courts sont signalés. 20 min par défaut.",
    "sections/run_off/data_description/short_off_threshold_min": "Les arrêts plus courts sont signalés. 5 min par défaut.",
    "sections/pendulum/name": "Détection des cycles trop fréquents",
    "sections/pendulum/data/pendulum_cycles_per_hour": "Cycles par heure",
    "sections/pendulum/data/pendulum_cycles_per_day": "Cycles par jour",
    "sections/pendulum/data/dhw_pendulum_cycles_per_hour": "Cycles d'eau chaude par heure",
    "sections/pendulum/data_description/pendulum_cycles_per_hour": "Nombre de cycles par heure qui déclenche une alerte. 4 par défaut.",
    "sections/pendulum/data_description/pendulum_cycles_per_day": "Nombre de cycles par jour qui déclenche une alerte. 40 par défaut.",
    "sections/pendulum/data_description/dhw_pendulum_cycles_per_hour": "Cycles d'eau chaude par heure qui déclenchent une alerte. 3 par défaut.",
    "sections/setpoint/name": "Consigne instable",
    "sections/setpoint/data/setpoint_oscillation_threshold": "Nombre de changements avant alerte",
    "sections/setpoint/data/setpoint_osc_window_min": "Fenêtre d'observation (min)",
    "sections/setpoint/data/setpoint_osc_min_delta": "Changement minimal de consigne (°C)",
    "sections/setpoint/data_description/setpoint_oscillation_threshold": "Nombre de changements de consigne de départ dans la fenêtre avant une alerte. 6 par défaut — ignore les réglages normaux, prévient en cas de vraie instabilité.",
    "sections/setpoint/data_description/setpoint_osc_window_min": "Fenêtre glissante en minutes. 30 par défaut.",
    "sections/setpoint/data_description/setpoint_osc_min_delta": "Changement minimal (°C) pour compter un changement de consigne. 0,5 par défaut.",
})
block(f"{O}/quality_ml", {
    "title": "Qualité et apprentissage",
    "description": "Note de qualité des cycles (0-100).",
    "sections/quality/name": "Note de qualité",
    "sections/quality/data/good_run_threshold_min": "Durée de bon cycle",
    "sections/quality/data/good_dt_threshold_k": "Écart départ/retour minimal",
    "sections/quality/data/good_off_threshold_min": "Durée d'arrêt minimale",
    "sections/quality/data/target_cycles_per_day": "Objectif de cycles par jour",
    "sections/quality/data_description/good_run_threshold_min": "Une durée égale ou supérieure donne la note maximale. 45 min par défaut.",
    "sections/quality/data_description/good_dt_threshold_k": "Écart minimal (K) pour la note maximale. 5,0 K par défaut.",
    "sections/quality/data_description/good_off_threshold_min": "Arrêt minimal pour la note maximale. 20 min par défaut.",
    "sections/quality/data_description/target_cycles_per_day": "Objectif utilisé dans les conseils. 8 par défaut.",
    "sections/adaptive/name": "Apprentissage adaptatif",
    "sections/adaptive/data/adaptive_thresholds_enabled": "Seuils adaptatifs",
    "sections/adaptive/data/adaptive_min_samples": "Nombre minimal de cycles",
    "sections/adaptive/data_description/adaptive_thresholds_enabled": "Ajuster automatiquement les seuils d'après les cycles observés.",
    "sections/adaptive/data_description/adaptive_min_samples": "Cycles nécessaires avant l'ajustement automatique. 20 par défaut.",
})
block(f"{O}/notifications", {
    "title": "Notifications",
    "description": "Comment et quand les alertes sont envoyées. Choisir une partie.",
    "menu_options/notifications_delivery": "Envoi",
    "menu_options/notifications_quiet_hours": "Heures calmes et bilans",
    "menu_options/notifications_content": "Contenu et langue",
    "menu_options/notifications_test_menu": "Notifications de test",
    "menu_options/notifications_enabled": "Activation alerte par alerte",
    "menu_option_descriptions/notifications_delivery": "Notifications persistantes, destinataire, émojis, conseils",
    "menu_option_descriptions/notifications_quiet_hours": "Heures calmes, anti-répétition, bilans périodiques",
    "menu_option_descriptions/notifications_content": "Langue et groupes d'alertes",
    "menu_option_descriptions/notifications_test_menu": "Envoyer un ou tous les exemples d'alerte",
    "menu_option_descriptions/notifications_enabled": "Activer ou couper chaque alerte",
})
block(f"{O}/advanced", {
    "title": "Avancé",
    "description": "Conservation et entretien de la base de données.",
    "sections/retention/name": "Conservation",
    "sections/retention/data/retention_enabled": "Entretien activé",
    "sections/retention/data/cycle_retention_days": "Conservation des cycles (jours)",
    "sections/retention/data/alert_retention_days": "Conservation des alertes (jours)",
    "sections/retention/data/vacuum_enabled": "Compacter après la purge",
    "sections/retention/data/daily_summary_live_enabled": "Bilan quotidien en direct",
    "sections/retention/data_description/retention_enabled": "Lancer l'entretien chaque jour à 3 h.",
    "sections/retention/data_description/cycle_retention_days": "Les cycles plus anciens sont résumés puis supprimés. 90 par défaut.",
    "sections/retention/data_description/alert_retention_days": "Les alertes plus anciennes sont supprimées. 30 par défaut.",
    "sections/retention/data_description/vacuum_enabled": "Compacter la base SQLite (VACUUM) après la purge pour libérer de la place.",
    "sections/retention/data_description/daily_summary_live_enabled": "Mettre à jour le bilan quotidien à la fin de chaque cycle. La reprise et l'entretien tournent toujours.",
    "sections/season/name": "Saison",
    "sections/season/data/season_start_month": "Mois de début de saison",
    "sections/season/data_description/season_start_month": "Premier mois de la saison de chauffe (1-12), pour le rendement saisonnier (SPF). 10 par défaut.",
})
block(f"{O}/test_notification", {
    "title": "Notification de test",
    "description": "Envoyer **un exemple d'alerte** au destinataire configuré.\n\n• **Type d'alerte** — l'alerte à simuler (ou *Toutes les alertes*)\n• **Forcer l'envoi** — ignorer les groupes d'alertes, les heures calmes et l'anti-répétition pour ce test seulement\n\nUtilise les options actuelles (destinataire et notifications persistantes) sans les modifier.",
    "data/alert_kind": "Type d'alerte",
    "data/ignore_group_filters": "Forcer l'envoi (sans filtres)",
    "data_description/alert_kind": "Type d'alerte à envoyer en test. « Toutes les alertes » les envoie toutes d'un coup.",
    "data_description/ignore_group_filters": "Normalement une alerte n'est pas envoyée si son groupe est coupé, pendant les heures calmes ou dans la fenêtre anti-répétition. Cocher pour l'envoyer quand même.",
})
block(f"{O}/test_notification_result", {
    "title": "Résultat du test",
    "description": "Type : **{kind}**\n\nRésultat : **{status}**\n\nAperçu :\n```\n{preview}\n```\n\nValider pour revenir au menu des options.",
})
block(f"{O}/test_all_notifications", {
    "title": "Envoyer toutes les notifications de test",
    "description": "Envoie **un exemple de chaque type d'alerte** au destinataire configuré, sans filtres (groupes, heures calmes, anti-répétition).\n\nValider pour envoyer.",
})
block(f"{O}/test_all_notifications_result", {
    "title": "Résultat de l'envoi groupé",
    "description": "Résultat : **{status}**\n\nAlertes envoyées : **{count}**\n\nAperçu :\n```\n{preview}\n```\n\nValider pour revenir au menu.",
})
block(f"{O}/notifications_delivery", {
    "title": "Envoi",
    "description": "Comment les alertes vous parviennent.",
    "data/persistent_enabled": "Notifications persistantes",
    "data/notify_service": "Destinataire des notifications",
    "data/notify_emoji_enabled": "Émojis dans les notifications",
    "data/action_advice_enabled": "Ajouter des conseils",
    "data_description/persistent_enabled": "Afficher les alertes en notifications persistantes dans la barre latérale.",
    "data_description/notify_service": "Entité de notification ou ancien service. Vide = rien sur le téléphone.",
    "data_description/notify_emoji_enabled": "Commencer les messages par un émoji pour les repérer vite.",
    "data_description/action_advice_enabled": "Ajouter un conseil d'action dans les messages d'alerte.",
})
block(f"{O}/notifications_quiet_hours", {
    "title": "Heures calmes et bilans",
    "description": "Couper les alertes non critiques et programmer des bilans réguliers.",
    "data/quiet_hours_enabled": "Heures calmes",
    "data/quiet_hours_start": "Début des heures calmes",
    "data/quiet_hours_end": "Fin des heures calmes",
    "data/alert_aggregation_minutes": "Anti-répétition (minutes)",
    "data/status_update_enabled": "Bilans périodiques",
    "data/status_update_interval_hours": "Intervalle des bilans (heures)",
    "data_description/quiet_hours_enabled": "Pas d'alerte non critique pendant les heures calmes.",
    "data_description/quiet_hours_start": "Début des heures calmes, HH:MM (24 h). 22:00 par défaut.",
    "data_description/quiet_hours_end": "Fin des heures calmes, HH:MM (24 h). 07:00 par défaut.",
    "data_description/alert_aggregation_minutes": "Ne pas répéter une même alerte dans cette fenêtre. 30 par défaut.",
    "data_description/status_update_enabled": "Envoyer régulièrement un bilan de l'activité des cycles.",
    "data_description/status_update_interval_hours": "Fréquence du bilan (1-168 heures).",
})
block(f"{O}/notifications_content", {
    "title": "Contenu et langue des alertes",
    "description": "Langue et activation par groupe d'alertes.",
    "data/notification_language": "Langue des notifications",
    "data/alert_group_pendulum": "Alerte : cycles trop fréquents",
    "data/alert_group_short_cycle": "Alerte : cycles courts",
    "data/alert_group_ml": "Alerte : anomalie d'apprentissage",
    "data/alert_group_setpoint": "Alerte : consigne instable",
    "data/alert_group_cop_stooklijn": "Alerte : COP / loi d'eau",
    "data/alert_group_component_health": "Alerte : état des composants",
    "data/alert_group_data_quality": "Alerte : qualité des données",
    "data_description/notification_language": "Langue des messages d'alerte et des libellés (cartes du tableau de bord comprises). Anglais par défaut.",
    "data_description/alert_group_pendulum": "Alertes de cycles trop fréquents (heure / jour).",
    "data_description/alert_group_short_cycle": "Alertes de marche courte et d'arrêt court.",
    "data_description/alert_group_ml": "Alertes d'anomalie détectée par l'apprentissage.",
    "data_description/alert_group_setpoint": "Alertes de consigne de départ instable.",
    "data_description/alert_group_cop_stooklijn": "Alertes de COP du jour et conseils de loi d'eau.",
    "data_description/alert_group_component_health": "Alertes de dégivrage et d'appoint électrique.",
    "data_description/alert_group_data_quality": "Alertes de source muette et de valeurs manquantes.",
})
dedup_names = {
    "pendulum_hourly": "cycles trop fréquents (heure)",
    "pendulum_daily": "cycles trop fréquents (jour)",
    "short_run": "marche courte",
    "short_off": "arrêt court",
    "ml_anomaly": "anomalie d'apprentissage",
    "setpoint_osc": "consigne instable",
    "cop_low": "COP du jour bas",
    "stooklijn_advies": "conseil de loi d'eau",
    "cop_degradation": "baisse du COP",
    "defrost_excessive": "dégivrages excessifs",
    "buh_excessive": "appoint électrique",
    "source_stale": "source muette",
    "missing_attributes": "valeurs manquantes",
    "dhw_pendulum": "cycles d'eau chaude",
    "high_cycle_rate": "fréquence de cycles élevée",
    "cop_vs_datasheet_low": "COP sous la fiche technique",
    "db_retention_warning": "base non purgée",
    "kmeans_retrain_stale": "apprentissage en retard",
    "energy_daily_anomaly": "consommation anormale",
    "short_cycling_pattern": "série de cycles courts",
    "cop_physically_impossible": "COP impossible",
}
put(f"{O}/notifications_dedup/title", "Anti-répétition par alerte")
put(f"{O}/notifications_dedup/description", "Nombre minimal de minutes entre deux alertes du même type.")
for k, v in en["options"]["step"]["notifications_dedup"]["data"].items():
    key = k[len("alert_agg_"):-len("_min")]
    put(f"{O}/notifications_dedup/data/{k}", f"Fenêtre : {dedup_names.get(key, key)}")
for k, v in en["options"]["step"]["notifications_dedup"]["data_description"].items():
    fv = (v.replace("Default", "Par défaut :").replace("days", "jours").replace("min.", "min")
          if v.startswith("Default") else "Fenêtre anti-répétition de cette alerte.")
    put(f"{O}/notifications_dedup/data_description/{k}", fv)
block(f"{O}/notifications_test_menu", {
    "title": "Notifications de test",
    "description": "Envoyer un exemple d'alerte au destinataire.",
    "menu_options/test_notification": "Envoyer une alerte de test",
    "menu_options/test_all_notifications": "Envoyer toutes les alertes d'un coup",
    "menu_option_descriptions/test_notification": "Choisir un type d'alerte et envoyer un exemple",
    "menu_option_descriptions/test_all_notifications": "Un clic envoie un exemple de chaque alerte",
})
put(f"{O}/notifications_enabled/title", "Activation alerte par alerte")
put(f"{O}/notifications_enabled/description", "Activer ou couper chaque alerte. Les alertes activées restent soumises aux groupes et aux heures calmes.")
en_desc = {
    "cop_degradation": "Se déclenche quand le COP baisse de plus de 15 % d'une semaine sur l'autre.",
    "defrost_excessive": "Se déclenche quand le nombre de dégivrages sur 7 jours dépasse le seuil.",
    "buh_excessive": "Se déclenche quand la part de cycles avec appoint sur 7 jours dépasse le seuil.",
    "source_stale": "Se déclenche quand la source ne se met plus à jour (critique).",
    "missing_attributes": "Se déclenche quand des valeurs obligatoires manquent.",
    "dhw_pendulum": "Se déclenche quand les cycles d'eau chaude par heure atteignent l'objectif.",
    "high_cycle_rate": "Se déclenche quand la fréquence dépasse 1,5 × l'objectif horaire.",
    "cop_vs_datasheet_low": "Se déclenche quand le COP est plus de 10 % sous la fiche technique.",
    "db_retention_warning": "Prévenir quand la base de données n'est plus purgée.",
    "kmeans_retrain_stale": "Prévenir quand l'apprentissage hebdomadaire est en retard.",
    "energy_daily_anomaly": "Prévenir quand la consommation du jour est anormale.",
}
for k in en["options"]["step"]["notifications_enabled"]["data"]:
    key = k[len("alert_enabled_"):]
    put(f"{O}/notifications_enabled/data/{k}", f"Alerte « {dedup_names.get(key, key)} »")
    put(f"{O}/notifications_enabled/data_description/{k}", en_desc.get(key, ""))
block(f"{O}/cop_calc", {
    "title": "Calcul du COP",
    "description": "Alimentation et puissance de l'appoint pour l'estimation de la consommation électrique.",
    "sections/electrical/name": "Consommation électrique",
    "sections/electrical/data/supply_phases": "Alimentation",
    "sections/electrical/data/buh_step1_kw": "Appoint étage 1 (kW)",
    "sections/electrical/data/buh_step2_kw": "Appoint étage 2 (kW)",
    "sections/electrical/data_description/supply_phases": "Alimentation de la PAC : 1 = monophasé, 3 = triphasé. 1 par défaut.",
    "sections/electrical/data_description/buh_step1_kw": "Puissance de l'étage 1 de l'appoint. 3 kW par défaut (standard Daikin).",
    "sections/electrical/data_description/buh_step2_kw": "Puissance de l'étage 2 de l'appoint. 3 kW par défaut (certains modèles : 6 kW).",
})
block(f"{O}/quality", {
    "data/buh_penalty_legionella_waived": "Pas de pénalité d'appoint pendant l'anti-légionelle",
    "data_description/buh_penalty_legionella_waived": "Quand le ballon atteint 60 °C ou plus, l'appoint est nécessaire pour finir la désinfection. Décocher pour garder la pénalité de −10 même dans ce cas.",
})

# ------------------------------------------------------------------ entity
S = "entity/sensor"
ents = {
    "thermal_power_live": "Puissance thermique instantanée",
    "cycle_state": "État du cycle",
    "current_cycle": "Cycle en cours",
    "last_cycle": "Dernier cycle",
    "cycles_today": "Cycles aujourd'hui",
    "quality_today": "Qualité du jour",
    "source_health": "Fraîcheur de la source",
    "learned_thresholds": "Seuils appris",
    "cop_today": "COP chauffage du jour",
    "heating_curve_advice": "Conseil de loi d'eau",
    "cop_curve_recent": "Courbe de COP récente",
    "cop_mean_day": "COP moyen du jour",
    "cop_mean_week": "COP moyen de la semaine",
    "cop_mean_month": "COP moyen du mois",
    "cop_heating_day": "COP chauffage (jour)",
    "cop_heating_week": "COP chauffage (semaine)",
    "cop_heating_month": "COP chauffage (mois)",
    "cop_dhw_day": "COP eau chaude (jour)",
    "cop_dhw_week": "COP eau chaude (semaine)",
    "cop_dhw_month": "COP eau chaude (mois)",
    "cop_cooling_day": "COP rafraîchissement (jour)",
    "cop_cooling_week": "COP rafraîchissement (semaine)",
    "cop_cooling_month": "COP rafraîchissement (mois)",
    "cop_combined_today": "COP global du jour",
    "spf_season": "Rendement saisonnier (SPF) saison",
    "spf_ytd": "Rendement saisonnier (SPF) depuis janvier",
    "scop_running_365d": "SCOP glissant 365 j",
    "hp_specs": "Caractéristiques de la PAC",
    "cop_normalized_a7w35": "COP ramené à A7/W35",
    "cop_vs_datasheet_pct": "COP par rapport à la fiche (%)",
    "cop_degradation_status": "Baisse du COP",
    "cop_degradation_week_pct": "Baisse du COP sur la semaine (%)",
    "cop_trend_30d": "Tendance du COP 30 j",
    "runtime_compressor_today": "Marche compresseur aujourd'hui",
    "runtime_buh_today": "Marche appoint aujourd'hui",
    "compressor_starts_today": "Démarrages compresseur aujourd'hui",
    "defrost_count_today": "Dégivrages aujourd'hui",
    "defrost_duration_today": "Durée de dégivrage aujourd'hui",
    "duty_cycle_today": "Taux de marche aujourd'hui",
    "electrical_energy_heating_today": "Électricité chauffage aujourd'hui",
    "electrical_energy_dhw_today": "Électricité eau chaude aujourd'hui",
    "electrical_energy_cooling_today": "Électricité rafraîchissement aujourd'hui",
    "electrical_energy_total_today": "Électricité totale aujourd'hui",
    "thermal_energy_heating_today": "Chaleur produite aujourd'hui",
    "thermal_energy_cooling_today": "Froid produit aujourd'hui",
    "daily_summary_recent": "Résumé des derniers jours",
    "electrical_power_estimated": "Puissance électrique estimée",
    "hybrid_mode": "Mode hybride",
    "boiler_efficiency_cop": "Rendement chaudière (COP)",
    "boiler_contribution_today_pct": "Part de la chaudière aujourd'hui (%)",
    "alerts_today": "Alertes aujourd'hui",
}
for k, v in ents.items():
    put(f"{S}/{k}/name", v)
block(f"{S}/cop_degradation_status/state", {
    "none": "Normal", "info": "Information", "warning": "Avertissement", "critical": "Critique",
})
B = "entity/binary_sensor"
bents = {
    "compressor_running": "Compresseur en marche",
    "pendulum_hourly": "Cycles trop fréquents (heure)",
    "pendulum_daily": "Cycles trop fréquents (jour)",
    "short_run": "Marche courte",
    "short_off": "Arrêt court",
    "defrost_active": "Dégivrage en cours",
    "buh_active": "Appoint en marche",
    "dhw_active": "Eau chaude en cours",
    "heating_active": "Chauffage en cours",
    "cooling_active": "Rafraîchissement en cours",
    "source_stale": "Source muette",
    "missing_attrs": "Valeurs manquantes",
    "setpoint_oscillating": "Consigne instable",
    "dhw_pendulum": "Cycles d'eau chaude trop fréquents",
    "high_cycle_rate": "Fréquence de cycles élevée",
    "boiler_operation_demand": "Demande chaudière",
    "boiler_dhw_demand": "Demande chaudière eau chaude",
    "short_cycling_pattern": "Série de cycles courts",
    "cop_physically_impossible": "COP physiquement impossible",
}
for k, v in bents.items():
    put(f"{B}/{k}/name", v)

# ------------------------------------------------------------------ issues
block("issues", {
    "source_stale/title": "ESPAltherma ne répond plus",
    "source_stale/description": "La source ESPAltherma n'envoie plus de données récentes. Vérifier le module ESP et sa connexion Wi-Fi.",
    "missing_attrs/title": "Valeurs obligatoires manquantes",
    "missing_attrs/description": "Il manque {count} valeur(s) obligatoire(s) à la source. Vérifier qu'ESPAltherma publie tous les champs.",
    "db_corrupt/title": "Échec du contrôle de la base de données",
    "db_corrupt/description": "La base des cycles a échoué au contrôle d'intégrité. Les données peuvent être incohérentes. Exporter les cycles et relancer l'entretien.",
    "notify_failed/title": "Envoi des notifications en échec",
    "notify_failed/description": "{count} échecs d'affilée vers {target}. Vérifier la configuration du service de notification.",
    "migration_failed/title": "Échec de migration des données d'apprentissage",
    "migration_failed/description": "Erreur de migration : {error}. L'historique d'apprentissage peut être incompatible avec le modèle actuel.",
    "datasheet_import_invalid/title": "Échec de l'import de fiche technique",
    "datasheet_import_invalid/description": "{count} erreur(s) de validation. Première : {first}",
    "datasheet_schema_unknown/title": "Version de fiche technique non prise en charge",
    "datasheet_schema_unknown/description": "Le contenu a la version {found} ; seule la version {supported} est prise en charge.",
    "datasheet_load_failed/title": "Fiches techniques personnelles illisibles",
    "datasheet_load_failed/description": "Impossible de lire les fiches techniques personnelles : {reason}",
    "legacy_db_multi_entry/title": "Ancienne base attribuée à une seule intégration",
    "legacy_db_multi_entry/description": "L'ancienne base Daikin Cycle ML (avant la v1.10.0) contient des données de plusieurs intégrations. Elle a été attribuée à {assigned_title} (la plus ancienne). Fichier d'origine conservé : {legacy_path}. Intégrations présentes : {n_entries}. Si ce choix est faux, utiliser l'action daikin_cycle_ml.assign_legacy_db. Pour archiver (repartir de zéro) : daikin_cycle_ml.archive_legacy_db. Pour exporter en CSV : daikin_cycle_ml.export_legacy_db.",
    "espaltherma_v2_missing_attrs/title": "Capteurs ESPAltherma v2 manquants",
    "espaltherma_v2_missing_attrs/description": "{count} capteur(s) obligatoire(s) ne sont pas publiés par ESPAltherma v2 : {labels}. Les activer dans l'interface web d'ESPAltherma v2 (Settings → Definitions), puis redémarrer ESPAltherma.",
})

# ---------------------------------------------------------------- services
entry_field = {"name": "Intégration", "description": "Identifiant de l'intégration (config entry)."}
svc = {
    "reset_counters": ("Remettre les compteurs à zéro", "Remet à zéro les compteurs du jour (tous ou une partie).",
                       {"counters": ("Compteurs", "Liste des compteurs (vide = tous).")}),
    "export_cycles": ("Exporter les cycles", "Exporte les cycles en JSON ou CSV.",
                      {"days": ("Jours", "Nombre de jours à remonter."), "format": ("Format", "Format de sortie.")}),
    "label_cycle": ("Étiqueter un cycle", "Ajoute votre étiquette à un cycle enregistré (apprentissage).",
                    {"cycle_id": ("N° de cycle", "Identifiant du cycle dans la base."), "label": ("Étiquette", "Texte de l'étiquette.")}),
    "recompute_baseline": ("Recalculer la référence", "Recalcule la référence d'apprentissage.",
                           {"days": ("Jours", "Fenêtre de référence en jours.")}),
    "run_maintenance": ("Lancer l'entretien", "Résume et supprime les anciens cycles et alertes, avec compactage facultatif.",
                        {"cycle_retention_days": ("Conservation des cycles (jours)", "Supprimer les cycles plus vieux que N jours."),
                         "alert_retention_days": ("Conservation des alertes (jours)", "Supprimer les alertes plus vieilles que N jours."),
                         "vacuum": ("Compacter", "Compacter la base SQLite (VACUUM) après la purge.")}),
    "export_cop_hourly": ("Exporter le COP par heure", "Exporte le COP agrégé par heure en JSON ou CSV.",
                          {"days": ("Jours", "Nombre de jours à remonter."),
                           "mode": ("Mode", "Filtre facultatif (heating, dhw, defrost, unknown)."),
                           "format": ("Format", "Format de sortie.")}),
    "send_test_notification": ("Envoyer une notification de test", "Envoie un message de test au destinataire configuré.",
                               {"message": ("Message", "Texte personnalisé facultatif."),
                                "target": ("Autre destinataire", "Remplace le destinataire configuré (facultatif)."),
                                "alert_kind": ("Type d'alerte", "Envoyer un type d'alerte précis en test. Omettre pour un simple message."),
                                "ignore_filters": ("Ignorer les filtres", "Ignorer heures calmes, anti-répétition et groupes.")}),
    "import_datasheet": ("Importer une fiche technique", "Importe ou remplace des caractéristiques Daikin fournies par vous.",
                         {"payload": ("Contenu", "Fiche technique (objet ou texte JSON)."),
                          "source_url": ("Lien de la source", "Référence facultative de la source.")}),
    "remove_user_datasheet": ("Supprimer une fiche personnelle", "Supprime une fiche technique personnelle pour un modèle.",
                              {"model_key": ("Clé du modèle", "Clé du modèle à retirer.")}),
    "recompute_kmeans": ("Relancer l'apprentissage", "Relance le regroupement (k-means) sur les N derniers jours et notifie le résultat.",
                         {"days": ("Jours", "Fenêtre d'apprentissage en jours.")}),
    "assign_legacy_db": ("Attribuer l'ancienne base", "Déplace la base SQLite d'une intégration vers une autre. Recharger les deux ensuite.",
                         {"entry_id": ("Intégration source", "Intégration dont la base doit être déplacée."),
                          "target_entry_id": ("Intégration cible", "Intégration qui doit recevoir la base. Échoue si elle en a déjà une.")}),
    "archive_legacy_db": ("Archiver la base", "Renomme la base actuelle en .legacy-[date] et repart de zéro au prochain rechargement.",
                          {"entry_id": ("Intégration", "Intégration dont la base doit être archivée.")}),
    "export_legacy_db": ("Exporter la base", "Exporte toutes les tables en CSV avec un manifest.json dans /config/daikin_cycle_ml_export_[entry_id]_[date]/.",
                         {"entry_id": ("Intégration", "Intégration dont la base doit être exportée.")}),
}
for s_key, (name, desc, fields) in svc.items():
    put(f"services/{s_key}/name", name)
    put(f"services/{s_key}/description", desc)
    for f_key in en["services"].get(s_key, {}).get("fields", {}):
        if f_key in fields:
            fn, fd = fields[f_key]
        elif f_key == "entry_id":
            fn, fd = entry_field["name"], entry_field["description"]
        else:
            continue
        put(f"services/{s_key}/fields/{f_key}/name", fn)
        put(f"services/{s_key}/fields/{f_key}/description", fd)
put("services/send_test_notification/fields/entry_id/description",
    "Identifiant de l'intégration. Facultatif s'il n'y a qu'une intégration Daikin.")

# ---------------------------------------------------------------- selector
block("selector/alert_kind/options", {
    "status_summary": "Bilan quotidien",
    "pendulum_hourly": "Cycles trop fréquents (heure)",
    "pendulum_daily": "Cycles trop fréquents (jour)",
    "short_run": "Marche courte",
    "short_off": "Arrêt court",
    "ml_anomaly": "Anomalie d'apprentissage",
    "setpoint_osc": "Consigne instable",
    "cop_low": "COP du jour bas",
    "stooklijn_advies": "Conseil de loi d'eau",
    "all_alerts": "Toutes les alertes (tout tester)",
    "short_cycling_pattern": "Série de cycles courts (fenêtre)",
})
block("selector/source_type/options", {
    "monolithic": "Entité unique (ESPAltherma v1, sensor.althermasensors)",
    "individual": "Entités séparées (ESPAltherma v2, sensor.espaltherma_*)",
    "auto": "Détection automatique (conseillé pour une nouvelle installation)",
})

# ------------------------------------------------------------------- apply
missing = []


def walk(node_en, node_fr, path):
    for k, v in node_en.items():
        p = path + (k,)
        if isinstance(v, dict):
            walk(v, node_fr[k], p)
        elif isinstance(v, str):
            if p in T:
                node_fr[k] = T.pop(p)
            elif k in node_en and path[-1:] == ("data",) and "map_attributes" in path:
                pass  # attribute names stay as-is (ESPAltherma labels)
            else:
                missing.append("/".join(p))


# keys containing "/" (ESPAltherma labels) cannot go through put()
_md = fr["config"]["step"]["map_attributes"]["data_description"]
for _k in ("I/U operation mode", "Flow sensor (l/min)"):
    _md[_k] = f"Nom sur votre capteur de la valeur standard « {_k} ». Laisser vide si le nom standard existe déjà."
    T.pop(tuple(f"config/step/map_attributes/data_description/{_k}".split("/")), None)

walk(en, fr, ())
missing = [m for m in missing if not m.startswith("config/step/map_attributes/data_description/")]
json.dump(fr, open(f"{base}/translations/fr.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
open(f"{base}/translations/fr.json", "a").write("\n")
print("untranslated (kept English):", missing)
print("unused french keys:", ["/".join(k) for k in T])
