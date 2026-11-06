"""The .pips reader on a synthetic file with the real schema seen in jobs 28-29 (no PIPESIM needed)."""
import json, os, sqlite3, sys, tempfile, types, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
if "openai" not in sys.modules:
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=lambda **k: None)
import pips_reader, agent


def make_pips(path):
    db = path + ".db"
    con = sqlite3.connect(db)
    con.executescript("""
    create table AV_PipeBase (Id int, Name text, HeatTransfer_Id int, ThermalConductivity real, Version text);
    create table AV_PipeHeatTransfer (Id int, Version text, PipeConductivity real, UCoeffUserAir real,
                                      UTypeAir text, IsUCalculated int, Survey_Id int);
    create table AV_Flowline (Id int, Name text, AmbientAirTemperature real, MeasuredDistance real);
    create table AV_BlackOilFluid (Id int, Name text, ThermalData_Id int, GOR real);
    create table AV_BlackOilThermalData (Id int, WaterHeatCapacity real, OilHeatCapacity real, GasConductivity real);
    create table AV_ThermalData (Id int, Decoy real);
    insert into AV_PipeBase values (5, 'FL', 7, 48.0075, '1');
    insert into AV_PipeHeatTransfer values (7, '1', 60.549998, 0.0, 'UserSupplied', 0, null);
    insert into AV_Flowline values (5, 'FL', 288.7055556, 6103.6);
    insert into AV_BlackOilFluid values (9, 'Multiphase', 11, 100.0);
    insert into AV_BlackOilThermalData values (11, 4186.8, 1884.06, 0.0346);
    insert into AV_ThermalData values (11, -1);
    """)
    con.commit(); con.close()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Info", "header")
        z.write(db, "Model")
    os.remove(db)


tmp = tempfile.mkdtemp()
pips = os.path.join(tmp, "TF_test.pips")
make_pips(pips)
before = open(pips, "rb").read()

# a component with everything it points to (heat-transfer row, thermal data row); temperatures in degC
r = pips_reader.read_pips(pips, component="FL")
comp = r["component"]
base = next(v for k, v in comp.items() if k.startswith("AV_PipeBase"))
ht = base["linked"]["HeatTransfer_Id -> AV_PipeHeatTransfer"]
assert ht["UTypeAir"] == "UserSupplied" and ht["UCoeffUserAir"]["value"] == 0.0, ht
assert ht["PipeConductivity"] == {"value": 60.549998, "unit": "SI (as stored)"}
fl = next(v for k, v in comp.items() if k.startswith("AV_Flowline"))
assert fl["values"]["AmbientAirTemperature"]["unit"] == "degC" and abs(fl["values"]["AmbientAirTemperature"]["value"] - 15.5556) < 1e-3
fluid = pips_reader.read_pips(pips, component="Multiphase")["component"]
td = next(v for k, v in fluid.items() if k.startswith("AV_BlackOilFluid"))["linked"]
assert "ThermalData_Id -> AV_BlackOilThermalData" in td, td           # not the decoy AV_ThermalData
assert td["ThermalData_Id -> AV_BlackOilThermalData"]["WaterHeatCapacity"]["value"] == 4186.8
print("reader: component + linked rows (heat transfer, fluid thermal data); K -> degC")

# everyday words find the right columns, and the owner of a linked row is named
hits = pips_reader.read_pips(pips, keyword="u value")["matches"]
assert any(h["table"] == "AV_PipeHeatTransfer" and h["component"] == "FL" and "UCoeffUserAir" in h["values"]
           for h in hits), hits
hits = pips_reader.read_pips(pips, keyword="heat capacity")["matches"]
assert any(h["values"].get("WaterHeatCapacity", {}).get("value") == 4186.8 for h in hits), hits
assert pips_reader.read_pips(pips, keyword="nothing_like_this")["matches"] == []
assert open(pips, "rb").read() == before                                # never modified
print("reader: 'u value' / 'heat capacity' map to the stored columns; file untouched")

# learned unit conversions are applied when available
pips_reader._load_units = lambda: {"MeasuredDistance": {"scale": 1.0, "offset": 0.0, "unit": "m"}}
fl = next(v for k, v in pips_reader.read_pips(pips, component="FL")["component"].items() if k.startswith("AV_Flowline"))
assert fl["values"]["MeasuredDistance"] == {"value": 6103.6, "unit": "m"}
print("reader: verified units from knowledge/pips_units.json are used")

# the agent tool
assert "read_pips" in agent.FUNCS and any(t["function"]["name"] == "read_pips" for t in agent.TOOLS)
assert "read_pips" in agent.SYSTEM
out = agent.FUNCS["read_pips"](path=pips, component="", keyword="conductivity")
assert any("PipeConductivity" in h["values"] for h in out["matches"])
print("agent: read_pips tool registered and described in the instructions")
print("ALL PIPS READER TESTS PASSED")
