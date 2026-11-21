"""Alert texts, English (#463). Same keys and placeholders as _nl / _fr."""
from __future__ import annotations

LEVELS = {
    "info": "No action needed",
    "watch": "Keep an eye on it",
    "act": "Action needed",
}

WORDS = {"see": "See:", "or": " · or ", "test": "TEST"}

CARDS = {"eff": "Efficiency card", "daily": "Daily summary card"}
TABS = {
    "eff": {"live": "Live", "today": "Today", "eff": "Efficiency", "curve": "Curve", "advice": "Advice"},
    "daily": {"today": "Today", "overview": "Overview", "quality": "Quality", "cycles": "Cycles",
              "duration": "Duration", "events": "Events"},
}
GRAPHS = {
    "water": "Water temperatures", "compressor": "Compressor", "hydraulics": "Flow and ΔT",
    "comfort": "Comfort", "strip": "Backup heater and defrost", "balance": "Heat balance",
}

ALERTS = {
    "pendulum_hourly": {
        "title": "Many starts this hour",
        "what": "{cph} compressor starts in the last hour (your limit: {target_cph}).",
        "what_plain": "Many compressor starts in the last hour.",
        "todo": "In mild weather the heat pump's lowest output can be more than the house needs, so some on/off running is normal, also after hot water or a defrost. If it goes on, make sure all radiator valves and floor circuits are open; if the rooms are warmer than needed, lower the leaving-water offset of the weather-dependent curve by 1–2 °C on the Daikin controller or Onecta app.",
    },
    "pendulum_daily": {
        "title": "Many runs today",
        "what": "{cycles_today} runs today (your limit: {target_cpd}).",
        "what_plain": "Many runs today.",
        "todo": "Long, steady runs are the most efficient. If this happens every day, open all radiator valves and floor circuits; if the rooms are warmer than needed, lower the leaving-water offset of the weather-dependent curve by 1–2 °C, otherwise ask your installer.",
    },
    "short_run": {
        "title": "Short run",
        "what": "The compressor ran {duration_min} min, shorter than {threshold_min} min.",
        "what_plain": "The compressor stopped after a short run.",
        "todo": "A short run after hot water, around a defrost or in mild weather is normal. Only if they keep coming, follow the advice of the 'Repeated short runs' alert.",
    },
    "short_cycling_pattern": {
        "title": "Repeated short runs",
        "what": "{min_cycles} or more short runs within {window_min} min.",
        "what_plain": "Several short runs in a short time.",
        "todo": "This is short cycling: it costs efficiency and wears the compressor. Open all radiator valves and floor circuits and, if the rooms are warmer than needed, lower the leaving-water offset of the weather-dependent curve by 1–2 °C; if it goes on for days, ask your installer.",
    },
    "short_off": {
        "title": "Short pause between runs",
        "what": "The compressor started again after {off_min} min (less than {threshold_min} min).",
        "what_plain": "The compressor started again after a short pause.",
        "todo": "The heat pump protects its compressor with its own minimum pause, so this is often a switch between heating and hot water or a defrost. Only if it happens often together with short runs, look at the compressor graph.",
    },
    "ml_anomaly": {
        "title": "Unusual behaviour",
        "what": "This run behaved differently from what your heat pump usually does at {outdoor} °C outdoor.",
        "what_plain": "This run behaved differently from what your heat pump usually does in this weather.",
        "todo": "Often explained by a changed setting, hot water, a defrost or a sudden change in the weather. If it repeats for several days without such a reason, look at the graphs or ask your installer.",
    },
    "setpoint_osc": {
        "title": "Water target keeps changing",
        "what": "The leaving-water target changed {osc_count} times in {window_min} min.",
        "what_plain": "The leaving-water target changes often.",
        "todo": "Usually harmless: the weather-dependent curve moves the target by a degree when the outdoor temperature hovers around a step, or the controller adjusts it from the room temperature. If an app or Home Assistant automation changes the target or offset, let it change less often.",
    },
    "cop_degradation": {
        "title": "COP lower than last week",
        "what": "COP changed {week_pct} % compared with last week at the same outdoor temperature.",
        "what_plain": "COP is lower than last week at the same outdoor temperature.",
        "todo": "Keep the outdoor unit free of leaves and snow (never scrape ice off the fins: the unit defrosts itself) and check that the curve or room temperature was not raised. If the drop lasts two weeks or ice stays on the unit, ask your installer.",
    },
    "defrost_excessive": {
        "title": "Many defrosts",
        "what": "{count_7d} defrosts in the last 7 days; up to {threshold} are normal for this weather and {run_h_7d} h of running.",
        "what_plain": "More defrosts than normal for the weather in the last 7 days.",
        "todo": "Frequent defrosts are normal in humid weather between about −5 and +7 °C, but not at 10 °C or warmer. Keep snow and leaves away from the unit, make sure meltwater can drain away and the cold air does not blow back into the unit (never scrape ice off). If ice stays on the unit or this keeps coming, ask your installer.",
    },
    "buh_excessive": {
        "title": "Backup heater used often",
        "what": "The backup heater was on during {buh_count_7d} runs in the last 7 days, for a large share of the running time.",
        "what_plain": "The backup heater was on for a large share of the running time in the last 7 days.",
        "todo": "Normal on very cold days, for the weekly tank disinfection and with powerful hot water; otherwise it costs electricity, because the heat pump makes several kWh of heat from 1 kWh. Check the Daikin controller or Onecta app for an error or emergency mode; if there is none and it goes on, ask your installer to check the backup heater settings.",
    },
    "source_stale": {
        "title": "No data from ESPAltherma",
        "what": "No update for {age_s} s. Cycles, COP and alerts are paused.",
        "what_plain": "ESPAltherma stopped sending data. Cycles, COP and alerts are paused.",
        "todo": "The heat pump keeps heating normally; only the monitoring is paused, and a short restart of the ESP usually clears by itself. If it lasts, check that the ESPAltherma device has power and Wi-Fi, and that its MQTT or ESPHome connection in Home Assistant works.",
    },
    "cop_physically_impossible": {
        "title": "Impossible COP value",
        "what": "{count} COP value(s) above what physics allows were ignored today.",
        "what_plain": "COP values above what physics allows were ignored today.",
        "todo": "Usually a power meter that reads too low (only the indoor unit measured, a missing phase, kW read as W) or a wrong flow value. Check the power meter in the integration options (Device); a single value at a start or stop can be ignored.",
    },
    "missing_attributes": {
        "title": "Values missing from ESPAltherma",
        "what": "{missing_count} value(s) are not sent: {missing_list}.",
        "what_plain": "Some values are not sent by ESPAltherma.",
        "todo": "Detection keeps working where it can. To get every feature, enable these values in your ESPAltherma definition and flash it again.",
    },
    "dhw_pendulum": {
        "title": "Hot water reheats often",
        "what": "{dhw_cph} hot-water reheats in the last hour (limit {target_cph}).",
        "what_plain": "Many hot-water reheats in the last hour.",
        "todo": "Several reheats in an hour are normal while hot water is being used (showers, a bath). If it happens without much hot-water use, ask your installer to check the tank reheat hysteresis and the hot-water mode.",
    },
    "high_cycle_rate": {
        "title": "Very many starts this hour",
        "what": "{cph} starts in the last hour, well above your target of {target_cph}.",
        "what_plain": "Very many starts in the last hour.",
        "todo": "Far more starts than your limit cost efficiency and wear the compressor. Check that radiator valves and floor circuits are open and that no thermostat or automation switches the heat pump on and off; if it goes on, ask your installer.",
    },
    "cop_vs_datasheet_low": {
        "title": "COP below datasheet",
        "what": "COP differs {pct_diff} % from the datasheet value ({cop_expected}) for this weather.",
        "what_plain": "COP is below the datasheet value for this weather.",
        "todo": "Often a measurement effect: at low heat demand the temperature difference is small, and your meter may include the circulation pump and control board. If it also stays low on colder days, ask your installer to check the unit.",
    },
    "db_retention_warning": {
        "title": "Database cleanup not running",
        "what": "{stale_alerts} old alerts and {stale_cycles} old cycles were not removed.",
        "what_plain": "Old alerts and cycles were not removed.",
        "todo": "The nightly cleanup (03:00) did not run. Check that cleanup is switched on in the integration options and restart Home Assistant; if it comes back, check the log for Daikin Cycle ML errors.",
    },
    "kmeans_retrain_stale": {
        "title": "Learning paused",
        "what": "The weekly learning of your run patterns has not finished for {hours_since_ok} h.",
        "what_plain": "The weekly learning of your run patterns has not finished.",
        "todo": "No action needed if your heat pump had few runs lately. Otherwise restart Home Assistant.",
    },
    "energy_daily_anomaly": {
        "title": "High electricity use today",
        "what": "Today's electricity use ({today_el_kwh} kWh) is far above your usual day ({baseline_el_mean} kWh).",
        "what_plain": "Today's electricity use is far above your usual day.",
        "todo": "Often a cold day, a higher room temperature setting, extra hot water or the backup heater. If none of these applies, look at today's graphs.",
    },
}

# Titles of the two messages built outside build_rich_alert
# (status_report.build_cop_low_message / build_stooklijn_message).
OTHER_TITLES = {"cop_low": "Low day COP", "stooklijn_advies": "Heating curve advice"}

KMEANS_REASONS = {
    "too_few": "Not enough runs yet to learn from. No action needed: learning resumes by itself.",
    "fetch_failed": "The database could not be read. Restart Home Assistant; if it comes back, check the log.",
    "kmeans_failed": "The learning step failed. Please report it on GitHub (Daikin Cycle ML issues).",
    "no_db": "The integration's database is not loaded. Restart Home Assistant.",
    None: "The weekly learning did not run. Restart Home Assistant.",
}
