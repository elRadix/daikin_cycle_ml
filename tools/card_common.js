/* DCM-COMMON-BEGIN (#427) shared by every Daikin Cycle ML card: language, theme, header.
   Do not edit in a card: edit tools/card_common.js and run tools/sync_card_common.py */
var DCM = (function () {
  var V = (typeof variables !== 'undefined' && variables) ? variables : {};
  var H = (typeof hass !== 'undefined' && hass) ? hass : {};
  var S = (typeof states !== 'undefined' && states) ? states : {};
  var find = function (tk, sfx) {
    var ids = Object.keys(S), i, j, k, E = H.entities || {};
    for (i = 0; i < ids.length; i++) {
      if (ids[i].indexOf('sensor.') !== 0) continue;
      for (j = 0; j < sfx.length; j++) { if (ids[i].slice(-sfx[j].length - 1) === '_' + sfx[j]) return ids[i]; }
    }
    for (k in E) { if (E[k] && E[k].platform === 'daikin_cycle_ml' && E[k].translation_key === tk && S[k]) return k; }
    return null;
  };
  var A = function (id) { return (id && S[id] && S[id].attributes) ? S[id].attributes : {}; };
  var csA = A(find('cycle_state', ['cycle_state', 'cyclus_status', 'etat_du_cycle']));
  var spA = A(find('hp_specs', ['hp_specs', 'wp_specs', 'caracteristiques_de_la_pac']));
  /* language: lang_override, then the HA language, then the integration language, then English */
  var LS = ['en', 'nl', 'fr'];
  var ov = String(V.lang_override || '').toLowerCase();
  var ha = String(H.language || '').toLowerCase().slice(0, 2);
  var cl = String(csA.configured_language || '').toLowerCase();
  var lang = LS.indexOf(ov) >= 0 ? ov : (LS.indexOf(ha) >= 0 ? ha : (LS.indexOf(cl) >= 0 ? cl : 'en'));
  /* theme: auto follows the HA dark mode; light / dark force it */
  var th = String(V.theme_override || 'auto').toLowerCase();
  var dark = th === 'dark' ? true : (th === 'light' ? false : !!(H.themes && H.themes.darkMode));
  var P = dark
    ? { bg: '#1B1F24', bg2: '#232A33', bg3: '#1E3448', hd1: '#1E3448', hd2: '#15283A', text: '#E6F0FA', text2: '#90CAF9',
        muted: '#B0BEC5', border: 'rgba(79,195,247,0.35)', accent: '#4FC3F7', good: '#66BB6A', warn: '#FFA726', bad: '#EF5350' }
    : { bg: '#FFFFFF', bg2: '#F5FAFD', bg3: '#E3F2FD', hd1: '#E3F2FD', hd2: '#BBDEFB', text: '#0D47A1', text2: '#1565C0',
        muted: '#546E7A', border: 'rgba(0,151,224,0.25)', accent: '#0097E0', good: '#2E7D32', warn: '#E65100', bad: '#C62828' };
  /* light colours of the cards -> dark mode (light backgrounds dark, dark text light) */
  var MAP = {
    '#FFFFFF': P.bg, '#F5FAFD': P.bg2, '#F5FAFE': P.bg2, '#E6F4FB': P.bg2, '#E8F2FB': P.bg2, '#EAF2F8': P.bg2,
    '#E3F2FD': P.bg3, '#D6ECF7': P.bg3, '#DCEBFA': P.bg3, '#BBDEFB': '#1F4A6B', '#D6EAF8': P.bg3, '#E1F5FE': P.bg3, '#AED6F1': '#1F4A6B',
    '#FFF3E0': '#3A2A12', '#FFF8EC': '#3A2A12', '#FDEAD0': '#3A2A12', '#FFEBEE': '#3A1D1D', '#FDECEA': '#3A1D1D', '#FBD0C8': '#3A1D1D',
    '#E8F5E9': '#1C3324', '#EAFAF1': '#1C3324', '#D5F5E3': '#1C3324', '#F3E5F5': '#2E2236',
    '#0D47A1': P.text, '#003366': P.text, '#001B3D': P.text, '#003A70': P.text, '#00539F': '#BBDEFB', '#005A9C': '#BBDEFB',
    '#1565C0': P.text2, '#1976D2': '#64B5F6', '#546E7A': P.muted, '#5D6D7E': P.muted, '#7F8C8D': '#9EADB5', '#95A5A6': '#9EADB5',
    '#37474F': '#CFD8DC', '#444444': '#CFD8DC', '#000000': '#ECEFF1', '#94A3B8': '#78909C', '#6A1B9A': '#CE93D8',
    '#2E7D32': '#4CAF50', '#1E8449': '#81C784', '#C62828': '#E53935', '#E65100': '#FB8C00', '#7D4F00': '#FFCC80',
    '#8B1A1A': '#EF9A9A', '#7A0008': '#EF9A9A'
  };
  var paint = function (html) {
    if (!dark || typeof html !== 'string') return html;
    return html
      .replace(/(background(?:-color)?\s*:\s*)(#fff\b|white\b)/gi, '$1' + P.bg)
      .replace(/(<(?:rect|circle|ellipse|path)\b[^>]*?\sfill=")(white|#fff|#ffffff)(")/gi, '$1' + P.bg2 + '$3')
      .replace(/rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*([0-9.]+)\s*\)/g, function (m, a) { return 'rgba(255,255,255,' + Math.min(0.08, parseFloat(a) * 0.1).toFixed(3) + ')'; })
      .replace(/#[0-9a-fA-F]{6}\b/g, function (m) { return MAP[m.toUpperCase()] || m; });
  };
  var T3 = function (o) { return (o && typeof o === 'object') ? (o[lang] || o.en || '') : String(o || ''); };
  var model = spA.model ? String(spA.model).toUpperCase() : '';
  var meta = [spA.family, spA.kw ? spA.kw + ' kW' : '', spA.refrigerant].filter(function (x) { return x && String(x) !== 'None'; }).join(' · ');
  /* one header for every card: icon, title + model, subtitle + family / kW / refrigerant */
  var header = function (icon, title, sub) {
    return '<div class="dcm-header" style="display:flex;align-items:center;gap:12px;width:100%;box-sizing:border-box;padding:14px 16px;'
      + 'border-radius:14px 14px 0 0;background:linear-gradient(135deg,' + P.hd1 + ' 0%,' + P.hd2 + ' 100%);border-bottom:3px solid ' + P.accent + ';text-align:left;">'
      + '<div style="background:' + P.accent + ';width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;'
      + 'font-size:20px;line-height:1;flex-shrink:0;box-shadow:0 4px 10px rgba(0,151,224,0.3);">' + icon + '</div>'
      + '<div style="min-width:0;flex:1;">'
      + '<div style="font-size:1.05em;font-weight:900;color:' + P.text + ';text-transform:uppercase;letter-spacing:0.8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
      + T3(title) + (model ? ' · ' + model : '') + '</div>'
      + '<div style="font-size:0.82em;font-weight:800;color:' + P.text2 + ';white-space:normal;">' + T3(sub) + (meta ? ' · ' + meta : '') + '</div>'
      + '</div></div>';
  };
  return { lang: lang, dark: dark, P: P, paint: paint, header: header, T3: T3, V: V, model: model,
           showHelp: V.show_help !== false && V.show_hints !== false };
})();
/* DCM-COMMON-END */
