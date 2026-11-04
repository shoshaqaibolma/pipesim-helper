| scenario | condition | study done | correct answer | tool calls | checker errors | JSON retries | invented numbers (first reply) | still flagged | time s |
|---|---|---|---|---|---|---|---|---|---|
| field_project | before | yes | yes | 9 | 0 | 0 | 0 | - | 90 |
| field_project | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 73 |
| gaslift_nodal | before | yes | yes | 10 | 0 | 0 | 0 | - | 115 |
| gaslift_nodal | knowledge | yes | yes | 10 | 0 | 0 | 0 | 0 | 109 |
| gaslift_allocation | before | yes | yes | 7 | 0 | 0 | 0 | - | 112 |
| gaslift_allocation | knowledge | yes | yes | 7 | 0 | 0 | 1 | 0 | 118 |
| uncertainty | before | yes | yes | 8 | 0 | 0 | 0 | - | 72 |
| uncertainty | knowledge | yes | yes | 6 | 0 | 0 | 0 | 0 | 64 |
| debottleneck | before | yes | yes | 9 | 0 | 0 | 0 | - | 88 |
| debottleneck | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 87 |
| pipeline_sizing | before | NO | NO | 64 | 22 | 0 | 0 | - | 98 |
| pipeline_sizing | knowledge | yes | yes | 6 | 0 | 0 | 4 | 0 | 58 |
| choke_sizing (held out) | before | yes | yes | 10 | 2 | 0 | 0 | - | 86 |
| choke_sizing (held out) | knowledge | NO | NO | 28 | 12 | 0 | 0 | 0 | 78 |
| water_rise (held out) | before | yes | yes | 7 | 0 | 0 | 0 | - | 71 |
| water_rise (held out) | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 68 |

**before**: model server dropped during ['pipeline_sizing'] (counted as failures)
**before**: studies done 7/8, correct answers 7/8, invented numbers in replies 0, checker errors 24, time 12 min
**knowledge**: studies done 7/8, correct answers 7/8, invented numbers in replies 5 (left after rewrite: 0), checker errors 12, time 10 min

- before / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- before / gaslift_nodal: best lift rate 0.1 mmsm3/d (expected about 0.1)
- before / gaslift_allocation: best split {'W1': 0.05, 'W2': 0.1} (expected W1 0.05, W2 0.1)
- before / uncertainty: ranking ['BO.WaterCut', 'W1:W1_Comp.ReservoirPressure', 'W1:W1_Comp.LiquidPI'] (expected water cut first)
- before / debottleneck: 203 mm @12 bara: 34.27 %, 152 mm @8 bara: 2.07 % (expected 203 mm better)
- before / pipeline_sizing: no diameter sweep
- before / choke_sizing: most oil at 32.0 mm (expected the largest choke, 32 mm)
- before / water_rise: least oil at water cut 50.0 %, wells not flowing at [70.0] % (expected the least at 70)
- knowledge / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- knowledge / gaslift_nodal: best lift rate 0.08 mmsm3/d (expected about 0.1)
- knowledge / gaslift_allocation: best split {'W1': 0.05, 'W2': 0.1} (expected W1 0.05, W2 0.1)
- knowledge / uncertainty: ranking ['BO.WaterCut', 'W1:W1_Comp.ReservoirPressure', 'W1:W1_Comp.LiquidPI'] (expected water cut first)
- knowledge / debottleneck: 203 mm @12 bara: 34.27 %, 152 mm @8 bara: 2.07 % (expected 203 mm better)
- knowledge / pipeline_sizing: smallest diameter with inlet <= 90 bara: 254.0 (expected 254)
- knowledge / choke_sizing: no choke-size sweep
- knowledge / water_rise: least oil at water cut 50.0 %, wells not flowing at [70.0] % (expected the least at 70)
