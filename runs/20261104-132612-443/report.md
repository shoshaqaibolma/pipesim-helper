STUDY PLAN: Split 0.15 mmsm3/d of lift gas between W1 and W2 for maximum oil
Units: METRIC
1. Build this network as a new PIPESIM model:
   PROJECT: Gas lift allocation test (METRIC)
     fluid     BO: type=black_oil, api=30, gor=80, water_cut=40, gas_sg=0.7
     well      W1: fluid=BO, reservoir_pressure=220, reservoir_temperature=90, depth=2500, tubing_id=76, ipr={'model': 'pi', 'liquid_pi': 8}, gas_lift={'depth': 2200, 'rate': 0.05}
     well      W2: fluid=BO, reservoir_pressure=200, reservoir_temperature=90, depth=2400, tubing_id=76, ipr={'model': 'pi', 'liquid_pi': 12}, gas_lift={'depth': 2100, 'rate': 0.05}
     sink      SEP: pressure=15
     flowline  FL-W1: from=W1, to=J1, length=1000, id=100, elevation_change=0
     flowline  FL-W2: from=W2, to=J1, length=1000, id=100, elevation_change=0
     flowline  Trunk: from=J1, to=SEP, length=4000, id=152, elevation_change=0
     junction  J1: 
2. Analysis: optimize (try every combination of 1-3 variables (e.g. each well's gas lift rate) and pick the one that maximizes the main result (total oil by default); optional max_total limits the sum of the variables (e.g. the lift gas available))
     GasLiftInjection:W1:W1_GL.GasRate: [0, 0.05, 0.1, 0.15]
     GasLiftInjection:W2:W2_GL.GasRate: [0, 0.05, 0.1, 0.15]
     maximize: total oil rate (or the main oil rate); only combinations whose sum <= 0.15
3. Results recorded: liquid, oil and gas rate at each sink; liquid rate and pressure at each well and source
4. Total simulation runs: 11. Outputs: CSV, charts, report.md in runs/<timestamp>/

## Results

| case | W1:W1_GL.GasRate | W2:W2_GL.GasRate | SEP liquid rate [sm3/d] | SEP oil rate [sm3/d] | SEP gas rate [mmsm3/d] | W1 liquid rate [sm3/d] | W1 pressure [bara] | W2 liquid rate [sm3/d] | W2 pressure [bara] | _status | SEP oil rate change vs base [%] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base | 0.05 | 0.05 | 1256 | 753.5 | 0.1603 | 597.5 | 37.75 | 657.7 | 38.47 | Completed | 0 |
| W1:W1_GL.GasRate=0, W2:W2_GL.GasRate=0 | 0 | 0 | 696.7 | 418 | 0.03344 | 333.5 | 20.2 | 363.2 | 20.67 | Completed | -44.53 |
| W1:W1_GL.GasRate=0, W2:W2_GL.GasRate=0.05 | 0 | 0.05 | 741.1 | 444.6 | 0.08551 |  |  | 741.9 | 31.81 | Completed | -40.99 |
| W1:W1_GL.GasRate=0, W2:W2_GL.GasRate=0.1 | 0 | 0.1 | 775.2 | 465.1 | 0.1371 |  |  | 776.3 | 38.75 | Completed | -38.27 |
| W1:W1_GL.GasRate=0, W2:W2_GL.GasRate=0.15 | 0 | 0.15 | 765.9 | 459.5 | 0.1867 |  |  | 766.3 | 44.01 | Completed | -39.02 |
| W1:W1_GL.GasRate=0.05, W2:W2_GL.GasRate=0 | 0.05 | 0 | 668.2 | 400.9 | 0.08202 | 668.9 | 30.07 |  |  | Completed | -46.8 |
| W1:W1_GL.GasRate=0.05, W2:W2_GL.GasRate=0.05 | 0.05 | 0.05 | 1256 | 753.5 | 0.1603 | 597.5 | 37.75 | 657.7 | 38.47 | Completed | 0 |
| W1:W1_GL.GasRate=0.05, W2:W2_GL.GasRate=0.1 | 0.05 | 0.1 | 1279 | 767.2 | 0.2115 | 571.6 | 40.57 | 705.7 | 45.36 | Completed | 1.81 |
| W1:W1_GL.GasRate=0.1, W2:W2_GL.GasRate=0 | 0.1 | 0 | 696.2 | 417.7 | 0.1334 | 696 | 36.62 |  |  | Completed | -44.57 |
| W1:W1_GL.GasRate=0.1, W2:W2_GL.GasRate=0.05 | 0.1 | 0.05 | 1268 | 760.9 | 0.2108 | 640.6 | 43.84 | 628.3 | 40.85 | Completed | 0.97 |
| W1:W1_GL.GasRate=0.15, W2:W2_GL.GasRate=0 | 0.15 | 0 | 687.8 | 412.7 | 0.1828 | 688.5 | 41.71 |  |  | Completed | -45.24 |
