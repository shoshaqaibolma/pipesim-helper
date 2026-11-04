| scenario | condition | study done | correct answer | tool calls | checker errors | JSON retries | invented numbers (first reply) | still flagged | time s |
|---|---|---|---|---|---|---|---|---|---|
| field_project | before | yes | yes | 9 | 0 | 0 | 0 | - | 81 |
| field_project | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 76 |
| field_project | structured | NO | NO | 72 | 32 | 0 | 0 | 0 | 176 |
| gaslift_nodal | before | yes | yes | 10 | 0 | 0 | 0 | - | 111 |
| gaslift_nodal | knowledge | yes | yes | 10 | 0 | 0 | 0 | 0 | 111 |
| gaslift_nodal | structured | NO | NO | 100 | 40 | 0 | 0 | 0 | 141 |
| gaslift_allocation | before | yes | yes | 7 | 0 | 0 | 0 | - | 108 |
| gaslift_allocation | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 106 |
| gaslift_allocation | structured | NO | NO | 66 | 8 | 0 | 0 | 0 | 156 |
| uncertainty | before | yes | yes | 8 | 0 | 0 | 0 | - | 71 |
| uncertainty | knowledge | yes | yes | 6 | 0 | 0 | 0 | 0 | 63 |
| uncertainty | structured | NO | NO | 26 | 12 | 0 | 0 | 0 | 71 |
| debottleneck | before | yes | yes | 9 | 0 | 0 | 0 | - | 87 |
| debottleneck | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 88 |
| debottleneck | structured | NO | NO | 66 | 8 | 0 | 0 | 0 | 155 |
| pipeline_sizing | before | yes | yes | 33 | 11 | 0 | 0 | - | 137 |
| pipeline_sizing | knowledge | yes | yes | 6 | 0 | 0 | 2 | 0 | 53 |
| pipeline_sizing | structured | NO | NO | 48 | 10 | 0 | 0 | 0 | 137 |
| choke_sizing (held out) | before | yes | yes | 10 | 2 | 0 | 0 | - | 72 |
| choke_sizing (held out) | knowledge | NO | NO | 28 | 12 | 0 | 8 | 4 | 95 |
| choke_sizing (held out) | structured | NO | NO | 48 | 6 | 0 | 0 | 0 | 155 |
| water_rise (held out) | before | yes | yes | 7 | 0 | 0 | 0 | - | 72 |
| water_rise (held out) | knowledge | yes | yes | 7 | 0 | 0 | 0 | 0 | 70 |
| water_rise (held out) | structured | NO | NO | 60 | 10 | 0 | 0 | 0 | 167 |

**before**: studies done 8/8, correct answers 8/8, invented numbers in replies 0, checker errors 13, time 12 min
**knowledge**: studies done 7/8, correct answers 7/8, invented numbers in replies 10 (left after rewrite: 4), checker errors 12, time 11 min
**structured**: model server dropped during ['field_project', 'gaslift_nodal', 'gaslift_allocation', 'debottleneck', 'water_rise'] (counted as failures)
**structured**: studies done 0/8, correct answers 0/8, invented numbers in replies 0 (left after rewrite: 0), checker errors 126, time 19 min

- before / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- before / gaslift_nodal: best lift rate 0.1 mmsm3/d (expected about 0.1)
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
- knowledge / choke_sizing: no choke-size sweep
- knowledge / water_rise: least oil at water cut 50.0 %, wells not flowing at [70.0] % (expected the least at 70)
- structured / field_project: no separator-pressure sweep
- structured / gaslift_nodal: nodal run: False, gas lift sweep: False
- structured / gaslift_allocation: no optimize run
- structured / uncertainty: no tornado run
- structured / debottleneck: no grid run
- structured / pipeline_sizing: no diameter sweep
- structured / choke_sizing: no choke-size sweep
- structured / water_rise: no water-cut sweep
