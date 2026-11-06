| scenario | condition | study done | correct answer | tool calls | checker errors | JSON retries | invented numbers (first reply) | still flagged | time s |
|---|---|---|---|---|---|---|---|---|---|
| field_project | before | yes | yes | 9 | 0 | 0 | 0 | - | 78 |
| field_project | knowledge | yes | yes | 9 | 0 | 0 | 0 | 0 | 114 |
| gaslift_nodal | before | yes | yes | 10 | 0 | 0 | 1 | - | 116 |
| gaslift_nodal | knowledge | yes | yes | 10 | 0 | 0 | 0 | 0 | 113 |
| gaslift_allocation | before | yes | yes | 7 | 0 | 0 | 1 | - | 109 |
| gaslift_allocation | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 106 |
| uncertainty | before | yes | yes | 8 | 0 | 0 | 0 | - | 72 |
| uncertainty | knowledge | yes | yes | 6 | 0 | 0 | 0 | 0 | 66 |
| debottleneck | before | yes | yes | 9 | 0 | 0 | 0 | - | 89 |
| debottleneck | knowledge | yes | yes | 9 | 0 | 0 | 1 | 0 | 100 |
| pipeline_sizing | before | yes | yes | 33 | 11 | 0 | 5 | - | 142 |
| pipeline_sizing | knowledge | yes | yes | 8 | 0 | 0 | 0 | 0 | 52 |
| choke_sizing | before | yes | yes | 10 | 2 | 0 | 0 | - | 75 |
| choke_sizing | knowledge | yes | yes | 6 | 0 | 0 | 0 | 0 | 62 |
| water_rise (held out) | before | yes | yes | 7 | 0 | 0 | 0 | - | 73 |
| water_rise (held out) | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 71 |

**before**: studies done 8/8, correct answers 8/8, invented numbers in replies 7, checker errors 13, time 12 min
**knowledge**: studies done 8/8, correct answers 8/8, invented numbers in replies 1 (left after rewrite: 0), checker errors 0, time 11 min

- before / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- before / gaslift_nodal: best lift rate 0.08 mmsm3/d (expected about 0.1)
- before / gaslift_allocation: best split {'W1': 0.05, 'W2': 0.1} (expected W1 0.05, W2 0.1)
- before / uncertainty: ranking ['BO.WaterCut', 'W1:W1_Comp.ReservoirPressure', 'W1:W1_Comp.LiquidPI'] (expected water cut first)
- before / debottleneck: 203 mm @12 bara: 34.27 %, 152 mm @8 bara: 2.07 % (expected 203 mm better)
- before / pipeline_sizing: smallest diameter with inlet <= 90 bara: 254.0 (expected 254)
- before / choke_sizing: most oil at 32.0 mm (expected the largest choke, 32 mm)
- before / water_rise: least oil at water cut 50.0 %, wells not flowing at [70.0] % (expected the least at 70)
- knowledge / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- knowledge / gaslift_nodal: best lift rate 0.08 mmsm3/d (expected about 0.1)
- knowledge / gaslift_allocation: best split {'W1': 0.05, 'W2': 0.1} (expected W1 0.05, W2 0.1)
- knowledge / uncertainty: ranking ['BO.WaterCut', 'W1:W1_Comp.ReservoirPressure', 'W1:W1_Comp.LiquidPI'] (expected water cut first)
- knowledge / debottleneck: 203 mm @12 bara: 34.27 %, 152 mm @8 bara: 2.07 % (expected 203 mm better)
- knowledge / pipeline_sizing: smallest diameter with inlet <= 90 bara: 254.0 (expected 254)
- knowledge / choke_sizing: most oil at 32.0 mm (expected the largest choke, 32 mm)
- knowledge / water_rise: least oil at water cut 50.0 %, wells not flowing at [70.0] % (expected the least at 70)
