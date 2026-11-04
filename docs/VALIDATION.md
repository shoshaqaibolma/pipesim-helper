# Validation on PIPESIM 2023.1 (user's install)

All numbers below come from runs on the real PIPESIM 2023.1 engine (`runner/` logs, `knowledge/compare.json`).

## 1. Models built from a description vs the official training case studies
Method (`tools/rebuild_compare.py`): open the original case study (temp copy) and run it; convert its data into the
assistant's project description; build that project and run it under the same conditions; compare. Then copy the
detailed inputs the description does not carry (pipe roughness, wall thickness, full black-oil settings) and compare
again, to separate *simplification error* from *builder error*.

| Case study | Quantity | From description | + detailed inputs |
|---|---|---|---|
| TF_M2A water pipeline (P/T profile) | pressure loss | -7.0 % | **-3.4 %** |
| | liquid rate | +0.3 % | +0.3 % |
| TF_M2B gas pipeline (P/T profile) | outlet pressure | -0.05 % | **-0.04 %** |
| | gas rate (calculated) | +4.8 % | **-1.6 %** |
| TF_M2C multiphase pipeline (P/T profile) | pressure loss | -6.9 % | **-1.4 %** |
| | outlet liquid / gas rate | +1.8 % / -8.8 % | **+0.2 % / -1.9 %** |
| TF_M3A oil well (nodal analysis, 20 bara outlet) | liquid rate | +27 % | +27 % (fluid, trajectory, geothermal, well settings copied: no change) |

Findings:
- **Hydraulics of pipelines agree within about 2-4 %** once the detailed inputs are copied, and within 5-9 % from
  a short description. The builder itself (topology, boundary conditions, fluids) reproduces the case studies.
- **Temperatures do not match** (originals: -0.5 to -5.6 degC at the outlet; rebuilt: about 16 degC). The case
  studies model heat loss to a cold environment through heat-transfer settings that the description does not carry.
- **The training well is 27 % off** and none of the copied inputs closes the gap. The likely cause is the vertical
  multiphase flow correlation, which the PIPESIM Python Toolkit 2023.1 does not expose (FlowCorrelation only has
  OverrideGlobal/SwapAngle), so a new model uses PIPESIM's default. Not yet confirmed.

## 2. Engineering scenarios through the local LLM (Qwen 3.5 9B, plain-language requests)
| Scenario | Result |
|---|---|
| 2-well field, separator 10 -> 30 bara | built, 12 cases; oil 1259 -> 1011 sm3/d |
| Gas-lifted well: nodal analysis + gas lift sweep | 1224 sm3/d at Pwf 116.3 bara; optimum 0.10 mmsm3/d (751.6 sm3/d oil) |
| Gas lift allocation, 0.15 mmsm3/d between 2 wells | W1 0.05 / W2 0.10 -> 767.2 sm3/d (+1.8 %); non-flowing wells reported |
| Uncertainty ranking (tornado) | water cut 265.8 sm3/d swing > reservoir pressure 193.3 > PI 189.5 |
| Debottlenecking, 3 wells | 203 mm trunkline +34.3 % oil; separator 12 -> 8 bara only +2.1 % |
| 25 km gas export line sizing | 203 mm needs 126 bara (> 90); **254 mm** works (87.1 bara) |

Known limits of the 9B local model: in larger layouts it tends to invent junctions or zero-length links and needs
several correction rounds (the checker catches every case); its free-text conclusions can contain an invented
number, so the report and the precomputed summary are the reference.
