"""TEST-ONLY stand-in for sixgill.definitions. Constants are plain strings, as in the real toolkit."""
ALL = "__ALL__"
class _NS:
    def __getattr__(self, n): return n
class Units: METRIC = "METRIC"; FIELD = "FIELD"; SI = "SI"
class ModelComponents:
    WELL="Well"; TUBING="Tubing"; COMPLETION="Completion"; FLOWLINE="Flowline"; SINK="Sink"; BLACKOILFLUID="BlackOilFluid"
    SOURCE="Source"; JUNCTION="Junction"; CHOKE="Choke"; CASING="Casing"
class _Params:
    def __getattr__(self, g):
        return type("G", (), {"__getattr__": lambda s, n: {"WATERCUT":"WaterCut","GOR":"GOR","RESERVOIRPRESSURE":"ReservoirPressure",
            "PRESSURE":"Pressure","INNERDIAMETER":"InnerDiameter","HORIZONTALDISTANCE":"HorizontalDistance","LIQUIDPI":"LiquidPI",
            "TEMPERATURE":"Temperature","BEANSIZE":"BeanSize","ASSOCIATEDBLACKOILFLUID":"AssociatedBlackOilFluid",
            "RESERVOIRTEMPERATURE":"ReservoirTemperature","CONSTANTC":"ConstantC","SLOPEN":"SlopeN"}.get(n, n)})()
Parameters = _Params(); Constants = _Params()
class SystemVariables:  # values as recorded from PIPESIM 2023.1
    PRESSURE="Pressure"; VOLUME_FLOWRATE_LIQUID_STOCKTANK="VolumeFlowrateLiquidStockTank"
    VOLUME_FLOWRATE_OIL_STOCKTANK="VolumeFlowrateOilStockTank"; VOLUME_FLOWRATE_GAS_STOCKTANK="VolumeFlowrateGasStockTank"
class ProfileVariables:
    TOTAL_DISTANCE="TotalDistance"; PRESSURE="Pressure"; TEMPERATURE="Temperature"
