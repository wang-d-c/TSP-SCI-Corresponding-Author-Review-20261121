# Supplementary Methods and Statistical Checks

## S1 Recorded environment and build

**Table S1. Historical evidence for the 600-run environment.**

| Item | Recorded value |
| --- | --- |
| Host CPU | Intel Core Ultra 9 275HX, 24 cores and 24 logical processors. Same-host inventory dated 16 November 2026. |
| Physical RAM | 48 GiB installed in the host inventory. All 596 valid run receipts report 50,870,607,872 bytes (47.377 GiB) visible to Windows. |
| Operating system | Native Windows 11, build 10.0.26300, from the 20 November build receipt. |
| C compiler and target | w64devkit GCC 16.2.0, x86_64-w64-mingw32. |
| Main build flags | Common solver: `-O3 -std=gnu99 -fcommon -DTWO_LEVEL_TREE -march=native -ffp-contract=off`, forced Windows platform header, link `-lm`. The external bridge added `-ffunction-sections` and `-fdata-sections` to its two newly compiled units and linked with `-Wl,--gc-sections -lm`. |
| Logical affinity | Serial solver Job on logical CPU 0 (mask 1). Monitor on logical CPU 1. |
| Power and CPU state | All 596 valid admission receipts record AC power. Continuous supply status, active power plan, performance mode, and effective frequency during runs were not recorded. |

The same-host inventory also records the two installed modules (16 + 32 GiB). The compiler target appears in the 20 November compiler log. The original build has 175 baseline translation units. The relink receipt confirms the same flags for the replacements Ascent, AddTourCandidates and FindTour. The bridge receipt identifies its two newly compiled units as Distance.c and gpx_euc2d_io.c, alongside reused author objects. The 596 valid terminal receipts provide the run-time RAM, AC and affinity record. CPU affinity establishes logical placement. The records do not establish core type or exclusive access. The earlier hardware inventory is not evidence of the power plan or frequency during the formal run.

## S2 Common configuration and charged time

The three current arms and all parent runs share the frozen LKH 3.0.14-derived Windows build. C_ref starts without a supplied tour. The continuation arms install the selected initial tour on the first full TSP trial. Initial-tour edge insertion uses the registered normal setting. The main paper uses C, M and K as abbreviated labels.

**Table S2. Common solver configuration.**

| Component | Registered setting |
| --- | --- |
| Distance model | TSPLIB EUC_2D, SCALE 1, PRECISION 100 |
| Candidate construction | POPMUSIC, maximum candidates 5, neighbors 5, sample size 10, solutions 25, trials 1, initial-tour construction off |
| Search configuration | Subgradient off, MOVE_TYPE 5, SUBSEQUENT_MOVE_TYPE 5, BACKTRACKING off, PATCHING_A 1, PATCHING_C 0, GAIN_CRITERION on |
| Limits | RUNS 1, MAX_TRIALS 100000, STOP_AT_OPTIMUM off, POPULATION_SIZE 0, TRACE_LEVEL 1 |
| Recombinations | Conditional internal GPX2 in the common solver. The K arm adds three external bridge invocations before continuation |
| Parent and arm clocks (s) | Request, stop proof, certification, cleanup at 17/18/19/20 for parents and 85/86/88/90 for each arm |
| Placement and protection | Native Windows, serial solver CPU0, independent monitor CPU1. Commit cap 4 GiB per process. Physical memory gates at 12 GiB for admission and 8 GiB during execution |

In the frozen author archive, LKHmain.c selects MergeWithTourGPX2 according to RECOMBINATION. RUNS = 1 precludes the Run > 1 branch, and POPULATION_SIZE = 0 precludes the MaxPopulationSize > 1 branch. The linked FindTour_ablation.c still permits trial-level merge attempts after the Lin–Kernighan step while both inner time bounds permit. The best-tour case requires FirstNode->BestSuc and a non-makespan setting. The ordinal-tour case requires Dimension = DimensionSaved, Cost ≥ OrdinalTourCost, BetterCost > OrdinalTourCost and a non-makespan setting. MergeWithTourGPX2 returns early if NewDimension = 0. A merge call therefore need not reach the internal gpx routine. Trace level 1 does not provide an invocation census. K’s P1/P2, P1/P3 and P2/P3 bridge processes and their verified child tours have individual records.

The 200 recorded pools share identical paid fees between M and K. Parent tour byte identities were checked for all 600 parent files. Continuation parameter files are identical within the 199 groups with a file for each arm. The M arm in the remaining group was blocked during admission and had no continuation parameter file. It retained the fee and pool identity in its result envelope.

**Table S3. Observed timing quantities.**

| Observed event or interval | Sample | Mean seconds | Range in seconds |
| --- | ---: | ---: | ---: |
| Full sealed pool fee paid by each arm | 200 pools | 51.394 | 51.160 to 51.487 |
| Three launches to observed Job-empty intervals, summed within K | 200 K arms | 0.131 | 0.094 to 0.191 |
| Three external calls' Job CPU time, summed within K | 200 K arms | 0.040 | 0 to 0.094 |
| Last external child verified, on the charged clock | 200 K arms | 53.042 | 52.751 to 53.241 |
| K minus M continuation launch on each arm's charged clock | 198 valid M/K pairs | 0.262 | 0.155 to 0.406 |

The field selection_s is retained in the frozen export. The portable numeric ledger names its exact value last_external_gpx_verified_charged_s. It is the last recorded child verification time from the arm’s charged origin. The elapsed process interval includes launch, operating-system and observation costs. The time between continuation launches includes all measured preparation differences. None of these fields alone identifies the effect of recombination time on the final tour.

The source and timing audit, pool and fee records, and individual timing events are linked from the accompanying [methods note](方法与计时核查.md).

## S3 Descriptive statistical checks

The same 196 complete C/M/K groups support the following common-coverage check across all 20 maps. The four incomplete groups remain represented in the delivery ledger. The main statistical analysis continues to use the eligible pairs for each contrast.

**Table S4. Common-coverage sensitivity among 196 complete triplets.**

| Comparison | Shorter / tied / longer | Map-equal ppm | 95% map-bootstrap interval, ppm |
| --- | --- | ---: | --- |
| K/M | 97 / 26 / 73 | −9.74 | [−43.44, +15.62] |
| K/C | 105 / 6 / 85 | +121.01 | [+61.04, +192.49] |
| M/C | 104 / 3 / 89 | +130.74 | [+56.35, +218.19] |

The K/M leave-one-map range is −14.02 to +3.34 ppm. The mean becomes positive only in the check omitting C10k.0. C10k.0 contributes −263.07 ppm across nine eligible pairs and includes the most negative pair (seed 981, −2223.46 ppm). The registered result retains that instance and all its eligible pairs. The complete-group and leave-one-map results are sensitivity checks.

![Figure S1. Empirical cumulative distributions of valid same-map same-seed pair effects. These distributions weight seed pairs equally, while the main statistical estimate weights maps equally.](../03_数据与复算/复算产物/pair_ecdf.png){width=95%}

The standalone [current statistical annotations](../03_数据与复算/statistical_notes_EN.md) give the original inference family and links to machine-readable results. The separate Historical Appendix includes Tables H1–H9 and Figures H1–H3. The current paper's Table 3 and Figure 2 show the strata and map-level effects.

The registered K/M primary analysis is kept distinct from the four-comparison secondary Holm family. K/EAX and M/EAX were not estimated in the original main batch. They keep p = 1 only internally for the originally specified calibration of K/C and M/C. An independently timed EAX supplement has its own accounting, tests, exclusions and missingness. Its outcomes cannot be retroactively pooled into the previous Holm calculation.

## S4 Original dispatch and cost audit

## Execution order and environmental evidence

An independent replay of the original assignment with seed 20261120 reproduced all 800 frozen slot labels and all 600 executed C/M/K slots. Each map received five K-first and five M-first assignments. Two monitor exclusions left 99 valid K/M pairs per order. The K-first exclusion was C10k.0/2301, and the M-first exclusion was ei8246/981. Across the five controller epochs the total dispatch counts were 9, 33, 264, 19 and 275. All 596 valid root processes reported the expected parent PID for their epoch. No valid K/M pair crossed an epoch. C ran before the K/M block in 50 of 99 K-first pairs and 53 of 99 M-first pairs. The previously dispatched formal method was C in 72 and 74 cases, respectively. This predecessor is a scheduling observation. Pool construction and workloads outside the experiment can intervene. The median within-epoch delay between the first method completing and the next method entering was 0.0912 s and 0.0935 s, respectively. This interval uses a monotonic clock. It is distinct from the difference of 0.262 s between continuation launches on the arms' respective charged clocks.

Available memory, system commit, paging, AC admission, affinities and Job CPU time were logged. Continuous temperature and frequency, power limit transitions and total completed trials were not logged. The supplementary order comparisons therefore describe schedule sensitivity without attributing it to a physical mechanism. The full order sample remains in the primary K/M analysis. The disk-full ledger adjudication for slot 12 has no original terminal timestamp, which remains blank.

## Identical starts and verified results

Independent SHA256 computations on 34 input tour files confirmed 17 byte-identical M/K starts. The 34 native first-trial witness tours were also independently parsed, normalized under rotation and reversal, and matched to their respective input cycles. Equal route length alone could not verify either claim. Across the 17 pairs, the engine, pool, seed and continuation parameter file matched within each pair. Fifteen pairs tied. On xvb13584, pool seed 1861, M and K ended at 37103 and 37104 with continuation seed 4861. With pool seed 2521, they ended at 37121 and 37122 with continuation seed 5521. The K continuation launch was 0.26784 s and 0.24316 s later on its charged clock, respectively. One pair was M-first, the other K-first. Each run met the predeclared stop-proof and delivery deadlines using the expected budget-stop exit status. These observations do not isolate the effect of launch delay or identify a search mechanism.

## Measured costs and a future sensitivity protocol

The disjoint time segments sum to the reported final charge for all 596 valid arms. On the 198 matched M/K pairs, each method was charged the same mean parent-pool cost of 51.39493 s. K's three external bridge stages averaged 0.13091 s from launch to observed Job-zero and 0.08034 s from Job-zero to child verification. Other pre-launch work averaged 1.40854 s for M and 1.45971 s for K. The observed continuation intervals from launch to Job-zero averaged 32.21928 s for M and 31.95685 s for K. Candidate validation after native cleanup to scored delivery averaged 0.03961 s and 0.03926 s. Mean final charges were 85.23390 s and 85.23196 s. These intervals include the operations observed between each pair of timestamps. Monitor and Job CPU time overlap the wall-clock intervals, so they were not added again. The original 17 s limit was a stop-request setting per parent. The three requests account for a nominal 51 s, while the measured pool consumes about 57.1% of the 90 s ceiling.

A future budget study could use 12 fixed maps, three per stratum, and six prespecified seeds per map. Each configuration would assign equal numbers of K-first and M-first runs per map. A 30/90/300 s total-budget comparison could provision parent request settings of 5/17/56 s per parent, subject to a separately logged feasibility check for the 30 s budget. A 90 s allocation comparison could instead vary the parent request setting from three 17 s slots to three 10 s slots while preserving the same total cap. Each arm would pay its full pool cost, and K would additionally pay for recombination. Failures and tail observations would remain visible. The current experiment tested only the original 90 s allocation. The proposed sensitivity study has not been started.

**Table S5. Observed charges by phase, seconds (198 valid paired groups).**

| Phase | M | K |
| --- | ---: | ---: |
| Common pool | 51.39493 | 51.39493 |
| Other preparation before launch | 1.40854 | 1.45971 |
| External GPX2 launch to Job-zero | — | 0.13091 |
| Job-zero to child verification | — | 0.08034 |
| Continuation launch to observed Job-zero | 32.21928 | 31.95685 |
| Job-zero to native cleanup | 0.00329 | 0.00369 |
| Native cleanup to scored delivery | 0.03961 | 0.03926 |
| Delivery to charged completion | 0.16825 | 0.16628 |
| Total charge | 85.23390 | 85.23196 |

The disjoint ledger records the same wall time segments before the rounding used here. Job CPU time and monitor times overlap those intervals.

**Table S6. Largest negative K/M effects, ppm (exploratory).**

| Map/seed | Valid within map | Start | M / K own-start continuation | Final | Contribution to original primary mean |
| --- | ---: | ---: | ---: | ---: | ---: |
| C10k.0/981 | 9 | 81.06 | 2797.31/499.06 | -2223.46 | -12.35 |
| genC15k.seed100004/2521 | 10 | 43.13 | 1831.92/163.20 | -1628.59 | -8.14 |
| genC15k.seed100004/1861 | 10 | 39.71 | 2600.45/1380.20 | -1183.66 | -5.92 |

The registered all-pair map-equal estimate is -9.97555 ppm. The post hoc exclusion of absolute effects at or above 1,000 ppm gives +18.73239 ppm. This exclusion is solely a sensitivity check. The three effects and all other valid pairs remain in the primary estimate.

The exploratory map sign-flip enumerated all 1,048,576 combinations, included ties at the observed magnitude using a 10⁻⁹ ppm sum tolerance and had no zero map differences. The conditional within-map label check used 100,000 draws and a plus-one numerator and denominator. Map bootstrap intervals, within-order strata, order-standardized estimates, common-triplet results and tail/leave-one-map checks are descriptive or sensitivity analyses, without multiplicity-adjusted post hoc inference.
