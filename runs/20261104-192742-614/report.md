STUDY PLAN: Analyze how field oil rate changes with separator pressure
Units: METRIC
1. Build this network as a new PIPESIM model:
   PROJECT: Field A (METRIC)
     fluid      BO: black oil, 35 API, GOR 100 sm3/sm3, water cut 20 %, gas SG 0.7
     well       W1: reservoir 250 bara / 90 degC, depth 2500 m, tubing 76 mm, PI 10 sm3/d/bar, fluid BO
     well       W2: reservoir 230 bara / 90 degC, depth 2400 m, tubing 76 mm, PI 15 sm3/d/bar, fluid BO
     junction   J1: 
     flowline   FL-W1: W1 -> J1, 1500 m, ID 100 mm, elevation +0 m
     flowline   FL-W2: W2 -> J1, 900 m, ID 100 mm, elevation +0 m
     flowline   Trunk: J1 -> SEP, 5000 m, ID 152 mm, elevation +10 m
     sink       SEP: 15 bara
2. Analysis: sweep (vary ONE variable over a range, everything else at base)
     Sink:SEP.Pressure: [10, 15, 20, 25, 30]
3. Results recorded: liquid, oil and gas rate at each sink; liquid rate and pressure at each well and source
4. Total simulation runs: 6. Outputs: CSV, charts, report.md in runs/<timestamp>/

## Results

| case | SEP.Pressure | SEP liquid rate [sm3/d] | SEP oil rate [sm3/d] | SEP gas rate [mmsm3/d] | W1 liquid rate [sm3/d] | W1 pressure [bara] | W2 liquid rate [sm3/d] | W2 pressure [bara] | _status | SEP oil rate change vs base [%] |
|---|---|---|---|---|---|---|---|---|---|---|
| base | 15 | 1521 | 1217 | 0.1217 | 677.3 | 39.44 | 844 | 38.87 | Completed | 0 |
| SEP.Pressure=10 | 10 | 1574 | 1259 | 0.1259 | 699.4 | 38.51 | 874.7 | 37.94 | Completed | 3.47 |
| SEP.Pressure=15 | 15 | 1521 | 1217 | 0.1217 | 677.3 | 39.44 | 844 | 38.87 | Completed | 0 |
| SEP.Pressure=20 | 20 | 1453 | 1162 | 0.1162 | 648.5 | 40.64 | 804 | 40.08 | Completed | -4.52 |
| SEP.Pressure=25 | 25 | 1367 | 1093 | 0.1093 | 612.9 | 42.15 | 753.8 | 41.6 | Completed | -10.16 |
| SEP.Pressure=30 | 30 | 1264 | 1011 | 0.1011 | 570.7 | 43.97 | 693.4 | 43.4 | Completed | -16.9 |

![](sweep_liquid_rate.png)

![](sweep_oil_rate.png)

![](sweep_gas_rate.png)

![](sweep_pressure.png)
