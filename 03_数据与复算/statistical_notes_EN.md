# Statistical supplement for the 600-run experiment

The 600 registered core slots include 596 valid completions and four invalid deliveries. C, M and K delivered 198, 199 and 199 valid tours out of 200 attempts each. The invalid deliveries consist of two paging-protection stops during execution, one pre-launch physical-memory threshold failure and one disk-full interruption. The experiment recorded no ordinary budget non-deliveries. The quality estimand is conditional on valid delivery by both arms. Delivery frequencies are reported separately.

For each eligible map and seed, the reduction is one million times the difference between the reference and trial lengths divided by the reference length. Positive values favor the trial arm. We average over eligible seeds within each map, then give the map means equal weight. The preregistered K/M test is a two-sided exact map-level sign-flip test with independent map-wise sign symmetry under the null. Percentile intervals use 100,000 resamples of maps with seed 20261120. The interval describes uncertainty across the study maps under this resampling model. The secondary Holm family includes K/C, M/C, K/EAX and M/EAX. The two deferred EAX comparisons contribute p=1 adjustment placeholders and provide no empirical estimate.

| Comparison | Valid pairs | Shorter / tied / longer | Map-equal mean ppm | 95% map-bootstrap interval ppm | p |
|---|---:|---:|---:|---:|---:|
| K/M | 198 | 97 / 28 / 73 | −9.98 | [−43.47, +15.36] | 0.647730 |
| K/C | 197 | 105 / 6 / 86 | +117.59 | [+59.78, +186.98] | 0.000252 (Holm) |
| M/C | 197 | 105 / 3 / 89 | +130.64 | [+56.19, +218.04] | 0.001682 (Holm) |

Each contrast uses all 20 study maps. The K/M point estimate is negative despite more seed-level wins than losses. C10k.0 has a mean of −263.07 ppm and the most negative seed pair of −2223.46 ppm. The all-map primary analysis retains those observations. The K/M leave-one-map range is −14.02 to +3.34 ppm. The point estimate becomes positive only when C10k.0 is omitted.

## Descriptive checks

| Source group | Maps | K/M ppm | K/C ppm | M/C ppm |
|---|---:|---:|---:|---:|
| VLSI engineering | 5 | −20.47 | +125.80 | +146.27 |
| DIMACS clustered | 5 | −40.30 | +294.94 | +348.27 |
| DIMACS uniform | 5 | +5.98 | +1.77 | −4.21 |
| Waterloo geographic | 5 | +14.88 | +47.83 | +32.21 |

These four source groups are descriptive. No interaction test was added. A shared-subset sensitivity analysis retained the same 196 valid C/M/K triplets for every contrast on all 20 maps. The K/M mean was −9.74 ppm with a 95% map-bootstrap interval from −43.44 to +15.62. The K/C and M/C means were +121.01 and +130.74 ppm. This sensitivity excludes four groups with an invalid delivery and reproduces the practical interpretation of the main analysis. It remains conditional on delivery. The K/M evidence does not establish equivalence. [Complete-triplet estimates](复算产物/complete_triplet_summary.csv) · [Four exclusions](复算产物/excluded_triplets.csv) · [Leave-one-map estimates](复算产物/leave_one_map.csv)

## Figure captions

**Overall effects.** Symbols mark map-equal route-length reductions in ppm. The circle is the preregistered K/M comparison. Squares are the two secondary comparisons. Lines show separate 95% map-bootstrap intervals, and the vertical dashed line marks zero. The contrasts use 198, 197 and 197 valid pairs, respectively. [Overall effects](复算产物/overall_effects_95ci.pdf)

**Map-level effects.** Each point averages the eligible seed-level comparisons within one map. Maps are ordered by source group, and all panels share the ppm scale. Positive values favor the first arm. [Map effects](复算产物/map_effects.pdf)

**Seed-pair distributions.** The empirical cumulative distributions show one observation per valid map and seed for each comparison. Their horizontal scale retains the observed tails. The empirical distributions weight seed pairs equally. The main effect averages the seed pairs within each map before applying equal weights to the maps. [Pair distributions](复算产物/pair_ecdf.pdf)
