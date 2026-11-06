# Reading values inside a PIPESIM .pips file

The PIPESIM Python Toolkit (2023.1) does not expose every setting of a model. Heat transfer (U-values, insulation
type, conductivities), fluid thermal data (heat capacities) and per-pipe flow correlations are among the hidden
ones. They are still in the `.pips` file, and the assistant can read them with the `read_pips` tool.

## What a .pips file is
- A **zip archive**. One entry, `Model`, is an **SQLite database**; the other entries are file metadata.
- Each object type has a table named `AV_<Type>`: `AV_Flowline`, `AV_Source`, `AV_BlackOilFluid`, `AV_PipeBase`,
  `AV_PipeHeatTransfer`, `AV_BlackOilThermalData`, `AV_FlowCorrelation`, `AV_SinglePhaseCorrelation`, ...
- Rows have an `Id`. A row points to a related row with a `<Something>_Id` column, for example
  `AV_PipeBase.HeatTransfer_Id -> AV_PipeHeatTransfer.Id` and
  `AV_BlackOilFluid.ThermalData_Id -> AV_BlackOilThermalData.Id`.
- Values are stored in **SI units**: temperatures in K, lengths in m, pressures in Pa, rates in m3/s, power in W,
  fractions 0-1. Verified in job 30 on 20 case studies: for 50 columns the stored value converts exactly to what the
  toolkit reports (e.g. Pressure x 1e-5 = bara, LiquidFlowRate x 86400 = sm3/d, BeanSize x 1000 = mm,
  temperatures - 273.15 = degC, WaterCut x 100 = %). `read_pips` applies these (`knowledge/pips_units.json`) and
  labels hidden SI columns by name (W/m/K, W/m2/K, J/kg/K, mm).
- A pipe has U-value settings for both surroundings (`UTypeAir`/`UCoeffUserAir` and `UTypeWater`/`UCoeffUserWater`);
  only the side matching the pipe's `AmbientFluidType` is used. `read_pips` reports that one as `heat_transfer_in_use`.

## The settings that matter most (found in the training case studies)

| Table | Column | Meaning | Example (TF_M2 pipelines) |
|---|---|---|---|
| AV_PipeHeatTransfer | UTypeAir | how the pipe's U-value is set (UserSupplied, Insulated, BareInAir, Coated) | UserSupplied |
| AV_PipeHeatTransfer | UCoeffUserAir | user U-value, W/m2/K | 0.0 |
| AV_PipeHeatTransfer | PipeConductivity | pipe wall conductivity, W/m/K | 60.55 |
| AV_PipeBase | ThermalConductivity, CementThermalConductivity | pipe / cement conductivity, W/m/K | 48.0 / 1.557 |
| AV_BlackOilThermalData | OilHeatCapacity, GasHeatCapacity, WaterHeatCapacity | J/kg/K | 1884.06 / 2302.74 / 4186.8 |
| AV_BlackOilThermalData | OilConductivity, GasConductivity, WaterConductivity | W/m/K | 0.1384 / 0.0346 / 0.6055 |
| AV_Flowline | AmbientAirTemperature | K (shown in degC) | 288.71 K = 15.56 degC |

A model built through the toolkit leaves the fluid thermal data empty and uses an "Insulated" pipe with a
calculated U-value. In job 29, writing the original's values for these two tables into a rebuilt model made it
match the case study exactly (gas pipeline 0.00 %, multiphase pipeline +0.01 %, outlet temperatures identical).

## Asking the assistant
- "What U-value and insulation does pipe FL use in C:\models\TF_M2B.pips?"
- "Which heat capacities does the fluid in C:\models\line.pips have?"
- "Show me everything stored for FL in C:\models\line.pips."

The tool works on a temporary copy and opens the database read-only; the model file is never changed.

## Reading it yourself (Python)
```python
import pips_reader
print(pips_reader.read_pips(r"C:\models\line.pips", component="FL"))          # one object + linked rows
print(pips_reader.read_pips(r"C:\models\line.pips", keyword="heat capacity"))  # search by word
```
Or from the command line: `python pips_reader.py "C:\models\line.pips" FL`.
