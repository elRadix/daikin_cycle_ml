"""#201: clearable optional sensor fields."""
from custom_components.daikin_cycle_ml.config_flow import DaikinCycleMLOptionsFlow as OF
class _E:
    def __init__(s,o): s.options=o
class _F(OF):
    def __init__(s,e): s._e=e
    @property
    def config_entry(s): return s._e
    def async_create_entry(s,data): return ("c",data)
def _r(o,u): return _F(_E(o))._save(u)[1]
def test_clear_all():
    o=_r({"power_sensor_entity":"s.a","cop_sensor_entity":"s.b","indoor_temp_sensor":"s.c"},{"sensors":{}})
    assert o["power_sensor_entity"] is None
    assert o["cop_sensor_entity"] is None
    assert o["indoor_temp_sensor"] is None
def test_set_works():
    assert _r({"power_sensor_entity":"s.old"},{"sensors":{"power_sensor_entity":"s.new"}})["power_sensor_entity"]=="s.new"
def test_preserved():
    o=_r({"power_sensor_entity":"s.a","compressor_rps_threshold":2.5},{"sensors":{}})
    assert o["power_sensor_entity"] is None and o["compressor_rps_threshold"]==2.5
def test_empty_no_crash():
    assert _r({},{"sensors":{}})["power_sensor_entity"] is None
def test_unrelated_kept():
    assert _r({"notify_service":"notify.x"},{"sensors":{}})["notify_service"]=="notify.x"
