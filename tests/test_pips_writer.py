"""pips_writer on a synthetic .pips with the real schema (jobs 28-29); the builder skips it for non-PIPESIM files."""
import os, sqlite3, sys, tempfile, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "fake_sixgill"), os.path.dirname(HERE)]
import pips_writer, pips_reader, netbuilder
from test_netbuilder import FIELD   # noqa: E402

tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "built.pips")
db = path + ".db"
con = sqlite3.connect(db)
con.executescript("""
create table AV_BlackOilFluid (Id int, Name text, ThermalData_Id int);
create table AV_BlackOilThermalData (Id int, EnthalpyCalcMethod text, OilHeatCapacity real, GasHeatCapacity real,
  WaterHeatCapacity real, OilConductivity real, GasConductivity real, WaterConductivity real, LatentHeatOfVaporization real);
create table AV_PipeBase (Id int, Name text, HeatTransfer_Id int);
create table AV_PipeHeatTransfer (Id int, UTypeAir text, UCoeffUserAir real, UTypeWater text, UCoeffUserWater real,
  IsUCalculated int, PipeConductivity real);
create table AV_Flowline (Id int, Name text, AmbientFluidType text);
insert into AV_BlackOilFluid values (1, 'BO', 10);
insert into AV_BlackOilThermalData values (10, 'Method2009', null, null, null, null, null, null, null);
insert into AV_PipeBase values (2, 'FL', 20);
insert into AV_PipeHeatTransfer values (20, 'Insulated', 11.36, 'Insulated', 11.36, 1, 45.0);
insert into AV_Flowline values (2, 'FL', 'Air');
""")
con.commit(); con.close()
with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("Info", "header")
    z.write(db, "Model")
os.remove(db)

rep = pips_writer.apply(path, fluids=["BO", "Missing"], pipes={"FL": {"u_value": 0.0}})
assert rep["fluids"] == ["BO"] and "Missing" in rep["skipped"][0] and "FL: U = 0.0" in rep["pipes"][0], rep
assert zipfile.ZipFile(path).namelist() == ["Info", "Model"]
r = pips_reader.read_pips(path, component="BO")["component"]
td = next(v for k, v in r.items() if k.startswith("AV_BlackOilFluid"))["linked"]["ThermalData_Id -> AV_BlackOilThermalData"]
assert td["WaterHeatCapacity"]["value"] == 4186.8 and "EnthalpyCalcMethod" not in td, td
use = pips_reader.read_pips(path, component="FL")["heat_transfer_in_use"]
assert use["u_value_set_as"] == "UserSupplied" and use["u_value"]["value"] == 0.0, use
print("writer: standard thermal data + user U-value written into the file's database, reader sees them")

# the builder: fake models are not PIPESIM zip files, so the thermal step is skipped and the model stays usable
m, report = netbuilder.build(dict(FIELD, flowlines=[dict(f, u_value=2.0) for f in FIELD["flowlines"]]),
                             os.path.join(tmp, "f.pips"))
assert report["thermal"] is None and m.comps["Flowline"]
m.close()
print("builder: thermal step only for real PIPESIM files; u_value accepted in the project")
