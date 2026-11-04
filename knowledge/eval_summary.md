| scenario | condition | study done | correct answer | tool calls | checker errors | JSON retries | invented numbers (first reply) | still flagged | time s |
|---|---|---|---|---|---|---|---|---|---|
| field_project | before | yes | yes | 14 | 1 | 0 | 0 | - | 102 |
| field_project | after | yes | yes | 7 | 0 | 0 | 1 | 0 | 96 |
| gaslift_nodal | before | yes | NO | 10 | 0 | 0 | 4 | - | 146 |
| gaslift_nodal | after | yes | NO | 10 | 0 | 0 | 0 | 0 | 115 |
| gaslift_allocation | before | yes | yes | 7 | 0 | 0 | 0 | - | 124 |
| gaslift_allocation | after | yes | yes | 7 | 0 | 0 | 0 | 0 | 111 |
| uncertainty | before | yes | yes | 9 | 0 | 0 | 0 | - | 119 |
| uncertainty | after | yes | yes | 7 | 0 | 0 | 0 | 0 | 113 |
| debottleneck | before | yes | yes | 9 | 0 | 0 | 0 | - | 90 |
| debottleneck | after | yes | yes | 7 | 0 | 0 | 0 | 0 | 113 |
| pipeline_sizing | before | yes | yes | 35 | 14 | 0 | 1 | - | 131 |
| pipeline_sizing | after | yes | yes | 8 | 0 | 0 | 0 | 0 | 90 |
| choke_sizing (held out) | before | yes | yes | 12 | 2 | 0 | 0 | - | 171 |
| choke_sizing (held out) | after | yes | yes | 10 | 2 | 0 | 2 | 0 | 89 |
| water_rise (held out) | before | yes | NO | 7 | 0 | 0 | 0 | - | 72 |
| water_rise (held out) | after | yes | NO | 7 | 0 | 0 | 0 | 0 | 74 |

**before**: studies done 8/8, correct answers 6/8, invented numbers in replies 5, checker errors 17, time 15 min
**after**: studies done 8/8, correct answers 6/8, invented numbers in replies 3 (left after rewrite: 0), checker errors 2, time 13 min

- before / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- before / gaslift_nodal: best lift rate 0.08 mmsm3/d (expected 0.1)
- before / gaslift_allocation: best split {'W1': 0.05, 'W2': 0.1} (expected W1 0.05, W2 0.1)
- before / uncertainty: ranking ['BO.WaterCut', 'W1:W1_Comp.ReservoirPressure', 'W1:W1_Comp.LiquidPI'] (expected water cut first)
- before / debottleneck: 203 mm @12 bara: 34.27 %, 152 mm @8 bara: 2.07 % (expected 203 mm better)
- before / pipeline_sizing: smallest diameter with inlet <= 90 bara: 254.0 (expected 254)
- before / choke_sizing: most oil at 32.0 mm (expected the largest choke, 32 mm)
- before / water_rise: least oil at water cut 50.0 % (expected 70)
- after / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- after / gaslift_nodal: best lift rate 0.08 mmsm3/d (expected 0.1)
- after / gaslift_allocation: best split {'W1': 0.05, 'W2': 0.1} (expected W1 0.05, W2 0.1)
- after / uncertainty: ranking ['OilA.WaterCut', 'W1:W1_Comp.ReservoirPressure', 'W1:W1_Comp.LiquidPI'] (expected water cut first)
- after / debottleneck: 203 mm @12 bara: 34.27 %, 152 mm @8 bara: 2.07 % (expected 203 mm better)
- after / pipeline_sizing: smallest diameter with inlet <= 90 bara: 254.0 (expected 254)
- after / choke_sizing: most oil at 32.0 mm (expected the largest choke, 32 mm)
- after / water_rise: least oil at water cut 50.0 % (expected 70)
