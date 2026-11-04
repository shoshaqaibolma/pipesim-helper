| scenario | condition | study done | correct answer | tool calls | checker errors | JSON retries | invented numbers (first reply) | still flagged | time s |
|---|---|---|---|---|---|---|---|---|---|
| field_project | before | yes | yes | 14 | 1 | 0 | 0 | - | 110 |
| field_project | after | NO | NO | 0 | 0 | 0 | 0 | 0 | 6 |
| gaslift_nodal | before | NO | NO | 6 | 0 | 0 | 0 | - | 67 |
| gaslift_nodal | after | NO | NO | 0 | 0 | 0 | 0 | 0 | 6 |
| gaslift_allocation | before | NO | NO | 0 | 0 | 0 | 0 | - | 14 |
| gaslift_allocation | after | NO | NO | 0 | 0 | 0 | 0 | 0 | 6 |
| uncertainty | before | NO | NO | 0 | 0 | 0 | 0 | - | 6 |
| uncertainty | after | NO | NO | 0 | 0 | 0 | 0 | 0 | 6 |
| debottleneck | before | NO | NO | 0 | 0 | 0 | 0 | - | 6 |
| debottleneck | after | NO | NO | 0 | 0 | 0 | 0 | 0 | 6 |
| pipeline_sizing | before | NO | NO | 0 | 0 | 0 | 0 | - | 6 |
| pipeline_sizing | after | NO | NO | 0 | 0 | 0 | 0 | 0 | 6 |
| choke_sizing (held out) | before | NO | NO | 0 | 0 | 0 | 0 | - | 6 |
| choke_sizing (held out) | after | NO | NO | 0 | 0 | 0 | 0 | 0 | 6 |
| water_rise (held out) | before | NO | NO | 0 | 0 | 0 | 0 | - | 6 |
| water_rise (held out) | after | NO | NO | 0 | 0 | 0 | 0 | 0 | 6 |

**before**: studies done 1/8, correct answers 1/8, invented numbers in replies 0, checker errors 1, time 3 min
**after**: studies done 0/8, correct answers 0/8, invented numbers in replies 0 (left after rewrite: 0), checker errors 0, time 0 min

- before / field_project: most oil at separator 10.0 bara (expected the lowest, 10)
- before / gaslift_nodal: nodal run: True, gas lift sweep: False
- before / gaslift_allocation: no optimize run
- before / uncertainty: no tornado run
- before / debottleneck: no grid run
- before / pipeline_sizing: no diameter sweep
- before / choke_sizing: no choke-size sweep
- before / water_rise: no water-cut sweep
- after / field_project: no separator-pressure sweep
- after / gaslift_nodal: nodal run: False, gas lift sweep: False
- after / gaslift_allocation: no optimize run
- after / uncertainty: no tornado run
- after / debottleneck: no grid run
- after / pipeline_sizing: no diameter sweep
- after / choke_sizing: no choke-size sweep
- after / water_rise: no water-cut sweep
