| scenario | condition | study done | correct answer | tool calls | checker errors | JSON retries | invented numbers (first reply) | still flagged | time s |
|---|---|---|---|---|---|---|---|---|---|
| field_project | before | yes | yes | 9 | 0 | 0 | 0 | - | 77 |
| field_project | after | yes | yes | 7 | 0 | 0 | 0 | 0 | 75 |
| gaslift_nodal | before | yes | yes | 10 | 0 | 0 | 0 | - | 120 |
| gaslift_nodal | after | yes | yes | 10 | 0 | 0 | 0 | 0 | 112 |
| gaslift_allocation | before | yes | yes | 7 | 0 | 0 | 1 | - | 107 |
| gaslift_allocation | after | yes | yes | 7 | 0 | 0 | 0 | 0 | 106 |
| uncertainty | before | yes | yes | 8 | 0 | 0 | 0 | - | 71 |
| uncertainty | after | yes | yes | 6 | 0 | 0 | 0 | 0 | 63 |
| debottleneck | before | yes | yes | 9 | 0 | 0 | 0 | - | 86 |
| debottleneck | after | yes | yes | 7 | 0 | 0 | 0 | 0 | 84 |
| pipeline_sizing | before | yes | yes | 33 | 11 | 0 | 3 | - | 130 |
| pipeline_sizing | after | yes | yes | 6 | 0 | 0 | 3 | 0 | 55 |
| choke_sizing (held out) | before | yes | yes | 10 | 2 | 0 | 0 | - | 74 |
| choke_sizing (held out) | after | NO | NO | 70 | 28 | 0 | 0 | 0 | 149 |
| water_rise (held out) | before | yes | yes | 7 | 0 | 0 | 0 | - | 70 |
| water_rise (held out) | after | NO | NO | 56 | 28 | 0 | 0 | 0 | 99 |

**before**: studies done 8/8, correct answers 8/8, invented numbers in replies 4, checker errors 13, time 12 min
**after**: model server dropped during ['choke_sizing', 'water_rise'] (counted as failures)
**after**: studies done 6/8, correct answers 6/8, invented numbers in replies 3 (left after rewrite: 0), checker errors 56, time 12 min

- before / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- before / gaslift_nodal: best lift rate 0.08 mmsm3/d (expected about 0.1)
- before / gaslift_allocation: best split {'W1': 0.05, 'W2': 0.1} (expected W1 0.05, W2 0.1)
- before / uncertainty: ranking ['BO.WaterCut', 'W1:W1_Comp.ReservoirPressure', 'W1:W1_Comp.LiquidPI'] (expected water cut first)
- before / debottleneck: 203 mm @12 bara: 34.27 %, 152 mm @8 bara: 2.07 % (expected 203 mm better)
- before / pipeline_sizing: smallest diameter with inlet <= 90 bara: 254.0 (expected 254)
- before / choke_sizing: most oil at 32.0 mm (expected the largest choke, 32 mm)
- before / water_rise: least oil at water cut 50.0 %, wells not flowing at [70.0] % (expected the least at 70)
- after / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- after / gaslift_nodal: best lift rate 0.08 mmsm3/d (expected about 0.1)
- after / gaslift_allocation: best split {'W1': 0.05, 'W2': 0.1} (expected W1 0.05, W2 0.1)
- after / uncertainty: ranking ['BO.WaterCut', 'W1:W1_Comp.ReservoirPressure', 'W1:W1_Comp.LiquidPI'] (expected water cut first)
- after / debottleneck: 203 mm @12 bara: 34.27 %, 152 mm @8 bara: 2.07 % (expected 203 mm better)
- after / pipeline_sizing: smallest diameter with inlet <= 90 bara: 254.0 (expected 254)
- after / choke_sizing: no choke-size sweep
- after / water_rise: no water-cut sweep
