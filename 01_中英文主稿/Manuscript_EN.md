# Additional GPX2 Recombination Under a Fixed Time Budget

Authors and affiliations [to be confirmed]

## Abstract

We tested whether three additional pairwise generalized partition crossover (GPX2) operations shorten the final tour under a fixed total budget in the symmetric Euclidean traveling salesperson problem. The reference arm C searched directly from coordinates using a common LKH-derived configuration. M continued from the shortest of three parent tours. K selected the shortest eligible tour from the same parents and three external GPX2 outputs before continuation. M and K each paid the full cost of their shared parent pool. K also paid for its additional recombination and validation. The primary batch used 20 maps, ten seeds per map and a 90 s budget. All 600 runs reached a terminal state, and 596 delivered independently verified tours. Against M, K was shorter in 97 of 198 valid pairs, tied in 28 and longer in 73. The map-equal mean reduction was −9.98 ppm (95% map bootstrap interval [−43.47, +15.36], two-sided p = 0.648). Against C, K and M had mean reductions of +117.59 and +130.64 ppm (Holm-adjusted p = 0.000252 and 0.001682). Earlier V22 and R4 results are reported separately. The primary comparison leaves the mean benefit of the extra recombination uncertain under the tested conditions.

**Keywords:** traveling salesperson problem, Lin–Kernighan–Helsgaun, partition crossover, fixed-budget evaluation, paired experiments

## 1. Introduction

When a heuristic must deliver a complete tour by a fixed deadline, time devoted to creating and combining initial tours is time not available for later search. The Lin–Kernighan–Helsgaun (LKH) heuristic [1] and generalized partition crossover (GPX2) [2,3] are established approaches. They can be composed in many ways, but an improvement of the intermediate tour does not itself establish an improvement of the final delivered tour. GPX2 already supports recombination among LKH results, and earlier studies have considered both crossover inside LKH and feedback of improved solutions to search [2,3,4].

We compare three project-defined configurations rather than propose a new crossover. C starts independently from the instance, M selects the shortest of three parent tours and continues search, and K performs three additional pairwise GPX2 operations on that same pool before continuation. Necessary generation, selection, recombination, verification and delivery are charged to the appropriate method. We ask whether the additional three-pair preparation improves final tour quality relative to M under the same total budget. The current secondary comparisons concern C. Historical baselines and start-to-finish observations are reported separately.

This study contributes a same-parent comparison in which both M and K are charged for producing their shared parents, alongside separate reporting of route quality and delivery. It measures the net effect of K’s three additional recombinations and describes when a shorter selected starting tour did not retain its advantage at the deadline. V22, R4 and the conditional old-pool diagnostic provide separate historical context. These observations apply to the recorded configurations and do not by themselves identify the cause of a reversal.

## 2. Related work

Helsgaun’s LKH implements the Lin–Kernighan heuristic [1]. LKH-2 extended k-opt submoves [5], and the LKH-3 report describes the later solver lineage [6]. Tinós, Helsgaun, and Whitley [2, Sections 4–5] compared GPX2 and IPT inside multi-trial LKH at preset trial and run counts and reported that better offspring did not necessarily improve the surrounding iterated local search. GPX2 has also been studied across separate runs [3], and Hains et al. [4] studied crossover on clustered TSP instances. Our paired contrast quantifies the net effect of three extra GPX2 calls on final delivered tours. Both methods use the same three-parent pool and pay its full cost under the same total wall-clock budget.

POPMUSIC has been used to construct LKH candidate edges using tour information [7]. Friedrich et al. [8] and Weise et al. [9] study fixed-budget bet-and-run strategies, including allocation of decision time and prediction; choosing among short initial searches is therefore not a new general strategy. Zhang and Looks [10] use backbone information from tours to guide LK search and perturbation. Our M is a concrete comparison configuration, not an invented bet-and-run framework. Recent candidate-list and partition-crossover studies [11,12] further limit any general novelty claim. McMenemy et al. [13] already compared LKH variants and EAX across a large set of structurally varied instances and investigated instance characteristics; their setting and budgets differ from ours. The present study differs operationally by recording the exact shared parent pool, charging its cost to both arms, and testing the *net* effect of three additional external GPX2 calls on delivered tours. Different implementations, benchmarks and deadlines prevent direct numerical comparisons with the cited studies.

## 3. Problem and comparison methods

For coordinates \(p_i=(x_i,y_i)\), the edge cost is \(d(i,j)=\lfloor\sqrt{(x_i-x_j)^2+(y_i-y_j)^2}+0.5\rfloor\) under the TSPLIB EUC_2D convention [14]. A feasible solution visits each city exactly once and returns to the starting city. The tour length is the sum of all cycle edges. Independent checks verify coverage and EUC_2D length.

All three arms use the same frozen, modified LKH 3.0.14-derived Windows executable. The common configuration uses POPMUSIC candidate construction, at most five candidates per node, no subgradient ascent, MOVE_TYPE = 5, SUBSEQUENT_MOVE_TYPE = 5, MAX_TRIALS = 100000, RUNS = 1, POPULATION_SIZE = 0, SCALE = 1 and PRECISION = 100. C_ref is the configured reference used in this study. The historical P5 builds and the historical author-LKH baselines have separate version records.

- **C_ref (C)** searches directly from the coordinates with the nominal group seed \(s\) and no supplied initial tour.
- **M_new (M)** selects the shortest of three verified parent tours, then continues through a fresh invocation of the common solver with seed \(s+3000\) and the selected INITIAL_TOUR_FILE.
- **K_new (K)** uses the same three physical parent tours and performs three external GPX2 calls on P1/P2, P1/P3 and P2/P3. It verifies the children and selects the shortest eligible tour from the parents and children before the same configured continuation with seed \(s+3000\). Ties retain the first eligible candidate, with parents ordered before children.

Parents use seeds \(s\), \(s+1000\) and \(s+2000\). The shared pool is generated once per map–seed group. M and K each pay the full measured generation, certification and sealing cost of that pool. K also pays for its three external programs, candidate preparation, validation and selection. The same total budget allows different amounts of continuation time. The first actual working tour of each continuation is checked against the selected input.

RECOMBINATION = GPX2 selects a merge function in the common binary. RUNS = 1 and POPULATION_SIZE = 0 rule out the between-run and population branches. The linked trial routine can still attempt internal merges after a Lin–Kernighan improvement step if its elapsed-time and tour-state conditions permit. Trace level 1 does not enumerate those attempts. This conditional internal behavior is shared by C, parent generation and continuation. K's three pre-continuation bridge calls are explicit external operations. The supplementary methods give the source conditions and the parameter table.

## 4. Experimental design and validity

### 4.1 Primary 600-slot batch

The current batch used 20 prespecified maps spanning engineering VLSI, clustered, uniform and geographic strata, with five maps per stratum. Each map used the same ten registered seeds. The main table has 200 slots per C, M and K, with M and K adjacent and each running first in five groups per map. The inputs and map-source manifest were frozen before dispatch. A native Windows host executed the solvers serially on CPU0, with independent resource monitoring on CPU1. The per-process commit limit was 4 GiB. The minimum required available physical memory was 12 GiB at admission and 8 GiB during execution. The operating-system stop and monitor evidence was retained. Affinity specifies placement. Table 1 reports the recorded host and toolchain. Supplementary Table S1 identifies the evidence for each setting.

**Table 1. Recorded environment for the primary 600-run experiment.**

| Item | Recorded value |
| --- | --- |
| Host CPU | Intel Core Ultra 9 275HX, 24 cores and 24 logical processors. Same-host inventory dated 16 November 2026. |
| Physical RAM | 48 GiB installed in the host inventory. All 596 valid run receipts report 50,870,607,872 bytes (47.377 GiB) visible to Windows. |
| Operating system | Native Windows 11, build 10.0.26300, from the 20 November build receipt. |
| C compiler and target | w64devkit GCC 16.2.0, x86_64-w64-mingw32. |
| Main build flags | Common solver: `-O3 -std=gnu99 -fcommon -DTWO_LEVEL_TREE -march=native -ffp-contract=off`, forced Windows platform header, link `-lm`. The external bridge added `-ffunction-sections` and `-fdata-sections` to its two newly compiled units and linked with `-Wl,--gc-sections -lm`. |
| Logical affinity | Serial solver Job on logical CPU 0 (mask 1). Monitor on logical CPU 1. |
| Power and CPU state | All 596 valid admission receipts record AC power. Continuous supply status, active power plan, performance mode, and effective frequency during runs were not recorded. |

Each arm has a 90 s total charged window. The stop request is scheduled at 85 s. Required evidence of search termination is due strictly before 86 s, certification strictly before 88 s and cleanup strictly before 90 s. For each physical parent, the corresponding times are 17, 18, 19 and 20 s. Input handling, candidate construction, search, applicable common-pool and branch work, verification, delivery and cleanup are charged. Admission waiting is outside any dispatched method's charged clock. The independent terminal-route replay is post-experiment verification. It cannot create a scored candidate retrospectively.

The export now labels the historical field selection_s as last_external_gpx_verified_charged_s. It records a charged-clock observation at the last external child's independent verification, with the common-prefix offset included. It cannot be interpreted as a pure GPX2 or selection duration. Recorded release, certification, search-stop proof and cleanup fields are different time observations. The records do not establish when individual candidates were first found internally.

The registered EAX arm (200 slots) and separate mechanism protocol (800 slots) were deferred at admission. The analysis below covers the three admitted arms.

### 4.2 Historical batches

V22 used native Windows on the CPU2 server, 20 maps and five seeds per map, with 300 valid C/M/K outcomes. R4 used native Windows on a local laptop, 12 maps and three seeds per map. Its five core methods delivered 164 valid tours in 180 slots. Its six 10,000-city generated maps contain uniform, clustered and mixed structures. The six 1,500–2,000-city research maps came from the University of Stirling collection [13]. M ran before K in R4. The recorded time fields and two previously exposed groups are handled under its own protocol. V22, R4 and the current study differ in inputs and frozen configurations and retain separate effect estimates.

### 4.3 Statistical analysis

For left arm X and reference Y with two valid tours at the same map and seed, the length reduction is \(10^6[L(Y)-L(X)]/L(Y)\) ppm. Positive values favor X. We average paired seed effects inside each map and give each map with usable pairs equal weight. Delivery and invalid attempts are counted separately. The K/M estimate uses every eligible K/M pair regardless of C's outcome.

For the primary 600-slot study, we retain the registered K/M two-sided map sign-flip test and the 95% percentile interval from 100,000 map-level bootstrap resamples (seed 20261120). The test assumes independently exchangeable effect signs under the null. The intervals describe sensitivity to which of the fixed maps are resampled. The four registered secondary comparisons are K/C, M/C, K/EAX and M/EAX. The two unobserved comparisons retain p = 1 placeholders solely for Holm adjustment. Four-stratum summaries, leave-one-map checks and the common set of 196 complete C/M/K groups are descriptive sensitivity analyses. The historical R4 five-comparison family and its 20,000 resamples are kept separate.

## 5. Results

### 5.1 Primary C/M/K batch

All 600 scheduled C/M/K runs reached terminal status. C, M and K delivered 198, 199 and 199 valid tours respectively. All 596 were independently verified. One C run was interrupted by lack of disk space. Two runs were interrupted by the original runtime paging guard (one K and one C), and one M run was rejected by the original pre-start memory check before native search. The valid K from that M run's shared-pool group remains in the ledger and contributes wherever a legitimate comparison exists. There were no normal budget non-deliveries.

**Table 2. Primary-batch route quality among eligible matched-seed pairs.** All comparisons cover 20 maps. The interval is a percentile map bootstrap. Holm adjustment applies to the registered secondary family.

| Comparison | Pairs | Shorter / tied / longer | Mean ppm | 95% interval, ppm | Reported p |
| --- | ---: | --- | ---: | --- | ---: |
| K/M | 198 | 97 / 28 / 73 | −9.98 | [−43.47, +15.36] | 0.648 |
| K/C | 197 | 105 / 6 / 86 | +117.59 | [+59.78, +186.98] | 0.000252 |
| M/C | 197 | 105 / 3 / 89 | +130.64 | [+56.19, +218.04] | 0.001682 |

![Figure 1. Map-equal reductions and 95% percentile map bootstrap intervals for the three current comparisons. Positive ppm favors the left arm. The whiskers are marginal intervals. The secondary p-values in Table 2 use the original four-comparison Holm family.](../03_数据与复算/复算产物/overall_effects_95ci.png){width=94%}

The K/M map median was +5.76 ppm. Twelve map means were positive and eight were negative. C10k.0 had the most negative map mean (−263.07 ppm across nine eligible pairs). The leave-one-map K/M mean ranged from −14.02 to +3.34 ppm. The primary estimate retains all 20 maps. Supplementary Table S4 gives the stratum means. The five equally weighted maps per stratum gave K/M descriptive means of −20.47 ppm for VLSI, −40.30 for clustered, +5.98 for uniform and +14.88 for geographic maps. These contrasts describe the selected panels. They do not identify effects of map structure independently of other characteristics. Supplementary Table S5 shows all three comparisons on the 196 groups in which C, M and K each delivered, with the original comparison-specific samples kept for the registered tests.

The paid common prefix averaged 51.394 s across 200 pools. Among the 198 jointly valid M/K pairs, M and K launched their continuation solver at mean charged times of 52.803 and 53.066 s respectively. The paired launch difference of 0.262 s includes preparation, checks and system overhead. Across 200 K arms, the three external process intervals from launch to observed Job-empty state summed to 0.131 s on average per arm. These intervals include process overhead and end when exit is observed. They cannot explain the quality differences on their own.

### 5.2 Historical V22

V22 produced 300 valid C/M/K results with no recorded formal failures or retries. K/C was shorter/tied/longer in 36/38/26 of the 100 seed groups and had a map-equal mean reduction of 34.76 ppm; K/M was 44/41/15 with 29.30 ppm; M/C was 27/37/36 with 5.46 ppm. The earlier V23 audit used 20,000 map-level bootstrap resamples stratified by map family and reported 95% intervals of [12.52 ppm, 58.31 ppm] and [16.49 ppm, 41.84 ppm] for K/C and K/M, respectively. In 64 groups K's recombination start was strictly shorter than the best parent; final K/M outcomes in those groups were 44 shorter, five tied and 15 longer. These are CPU2 results under that batch's protocol, not observations that can be paired or pooled with local R4.

### 5.3 Historical R4 C/M/K

All C, M and K slots yielded valid routes on 12 maps and three seeds. Historical Table H1 reports the map-weighted results. K was shorter more often than it was longer relative to M, but the longer outcomes had a larger average magnitude. The K/M interval crosses zero and the observed data do not demonstrate equivalence.

**Historical Table H1. R4 complete paired route comparisons.**

| Comparison | Valid pairs / maps | Shorter / tied / longer | Map-equal mean (ppm) | Exploratory 95% interval (ppm) |
| --- | --- | --- | --- | --- |
| K/M | 36 / 12 | 9 / 21 / 6 | −4.05 | [−22.41, 10.96] |
| K/C | 36 / 12 | 13 / 16 / 7 | 33.27 | [7.45, 64.61] |
| M/C | 36 / 12 | 11 / 17 / 8 | 37.32 | [−0.18, 84.60] |

Historical Appendix Table H9 reports the four estimable registered tests and the incomplete EAX contrast. The estimable comparisons have six or seven nonzero maps, giving minimum two-sided sign-flip p-values of 0.03125 or 0.015625. Both exceed the first Holm cutoff of 0.01. The observed tie structure therefore prevented family-wise rejection at 0.05. M/C is calculated directly from its own pairs.

K/M has two positive, six zero and four negative means under the registered seed-relative metric. Its median map effect is zero. The largest individual improvement was 82.49 ppm and the largest regression was 285.75 ppm (139 length units on R10000-01/541). Leaving one map out yields means from −8.87 ppm to 3.37 ppm. The registered exposure sensitivity remains slightly negative. Both methods attained the published optimum in all 18 pairs on six 1,500–2,000-city instances [15]. On six 10,000-city maps, K/M was 9 shorter, 3 tied and 6 longer with mean reduction −8.10 ppm. This exploratory contrast confounds size with origin and structure. On C10000-02 the three absolute K/M differences sum to zero, but seed-specific denominators give the registered map mean a tiny negative sign. The supplementary sensitivity first computes each method’s mean within each map.

Historical Appendix Figure H1 shows the K/M map reductions. Exact ties are marked separately, and the dashed line is the equal-map mean.

Historical Appendix Table H2 reports the complete R4 map values. Tables H5 and H6 in the same appendix document the R4 settings and selected version hashes. Table H8 lists attainment of published reference lengths.

### 5.4 Historical R4 external baselines and delivery

**Historical Table H3. R4 terminal status.**

| Method | Valid | Budget non-delivery | Resource-monitor interruption |
|---|---:|---:|---:|
| C | 36 | 0 | 0 |
| M | 36 | 0 | 0 |
| K | 36 | 0 | 0 |
| Author LKH-GPX2 | 29 | 7 | 0 |
| Author LKH-POP | 27 | 8 | 1 |

All 180 R4 slots for these five methods reached a terminal state, with 164 valid routes. Both author-LKH configurations delivered in zero of six runs on the two 10,000-city clustered maps. The twelve logs report completed ascent and 72.97–74.58 CPU s of preprocessing. These CPU times describe the burden of initial work. They do not locate the wall-clock cutoffs. This comparison uses the registered ALPHA/subgradient configurations and provides no controlled comparison with an author LKH POPMUSIC/no-subgradient configuration.

**Historical Table H4. R4 comparisons with valid deliveries.** The two K-versus-author-LKH contrasts belong to the five registered R4 tests. The other four rows are descriptive.

| Comparison | Role | Valid pairs / maps | Shorter / tied / longer | Map-equal mean (ppm) | Exploratory 95% interval (ppm) |
| --- | --- | --- | --- | --- | --- |
| K/LKH-GPX2 | Registered | 29 / 10 | 17 / 10 / 2 | 242.25 | [65.63, 516.40] |
| K/LKH-POP | Registered | 27 / 10 | 13 / 14 / 0 | 316.30 | [76.88, 639.88] |
| M/LKH-GPX2 | Descriptive | 29 / 10 | 17 / 10 / 2 | 247.80 | [64.60, 538.95] |
| M/LKH-POP | Descriptive | 27 / 10 | 13 / 14 / 0 | 312.13 | [75.81, 632.85] |
| C/LKH-GPX2 | Descriptive | 29 / 10 | 16 / 8 / 5 | 204.21 | [42.25, 450.16] |
| C/LKH-POP | Descriptive | 27 / 10 | 13 / 12 / 2 | 259.30 | [68.96, 509.60] |

The first two rows were among the five registered R4 contrasts. The four descriptive rows use the same valid-pair rule. Historical Appendix Table H9 gives the registered p-values.

The original R4 EAX arm used an adapted implementation of edge-assembly crossover [16]. It delivered 18 of 19 attempts on six large maps, with 17 slots deferred. Among the available pairs, M/EAX, C/EAX and K/EAX were shorter, tied or longer in 18/0/0, 16/0/2 and 17/0/1 cases. The separately versioned EAX supplement delivered 18, failed on one and left 17 unstarted. These partial records describe availability and observed valid pairs.

### 5.5 Historical starting tours and continuation

M and K parent hashes match in all 36 R4 groups. In 16 groups the selected starting cycles are identical up to rotation and reversal, and their final lengths tie. In the remaining 20 groups K starts shorter; it finishes shorter in 9, tied in 5 and longer in 6. On four of the small-map runs, K started at the published optimum while M reached it during continuation. Of the 16 strictly better K starts on the 10,000-city maps, 9 led to shorter endpoints, 1 to a tie and 6 to longer endpoints. No matched external optimum was established for these six large maps. Thus a shorter start did not guarantee the shorter final tour in these observed configurations. The per-group start and final differences are shown in Historical Appendix Figure H2; their association is descriptive and does not isolate a causal mechanism. It is not possible from this observation alone to attribute the six reversals uniquely to extra recombination time, route structure, initialization state, randomness or other search dynamics. Historical Appendix Figure H3 shows the distribution of all 36 endpoint seed pairs within maps.

The three external GPX2 calls took 0.33 s on average. Available continuation allowances averaged 31.15 s for M and 30.88 s for K. On the larger maps the paired allowance difference (M minus K) ranged from −0.288 to +0.450 s. The allowance is computed after charged branch preparation. A longer measured M startup explains the most negative difference (Historical Appendix Table H7).

A separate 30-second diagnostic used 12 already-exposed development pools from six maps and three continuation seeds per pool (72 valid tasks). Start A was the shortest parent and start B was the tour selected by the historical K procedure. B finished shorter/tied/longer in 12/20/4 of 36 pairs. The 18 same-cycle pairs tied. Among the 18 pairs starting from different cycles, B started shorter and finished shorter/tied/longer in 12/2/4. A ran before B and the already-generated pools were supplied without charge. These repeat seeds characterize sensitivity in the development pools. R4 used different pools and one continuation seed per pool.

## 6. Discussion

The same-parent comparison asks what the three additional external GPX2 calls return on the full charged clock. K shortened more paired tours than it lengthened in the current batch. The larger negative effects on a few maps brought the equal-map mean below zero. Its interval spans gains and losses. The primary evidence does not establish a stable incremental advantage. Equivalence was not tested against a prespecified margin. Both M and K shortened tours on average relative to the configured C reference in the valid paired sample under the registered Holm analysis. The direct K/M contrast governs any comparison between the two shared-pool arms.

V22 had a positive K/M estimate, while R4 and the current batch had slightly negative estimates. The data sets, software and execution sequences differ. The comparison across batches cannot isolate the influence of any one factor. The recorded R4 changes between the selected starting tour and the final tour illustrate the behavior described by earlier GPX2 studies. They provide separate descriptive evidence. In the current batch, the paid common prefix and the recorded phase timestamps are directly observable. Their association with tour quality cannot isolate preparation expense, ranking, initial route structure and subsequent search dynamics.

## 7. Limitations and future work

The current estimates describe 20 fixed maps, one total budget and the tested common LKH configuration. The map-level test relies on its sign-exchangeability assumption and does not turn the fixed panel into a random sample of all Euclidean TSP instances. Incomplete pairs remain missing in the conditional quality analysis. The common-coverage check uses the same 196 groups for three contrasts and is descriptive. The audit covers the test settings, tour feasibility and the software versions used. Global optimality and the number of in-process GPX2 calls remain outside the recorded evidence.

The current experiment contains no timed EAX comparison. R4 offers separate comparisons with two author LKH configurations and incomplete EAX observations. The large-map EAX engineering candidate lacked complete evidence of stopping before the deadline. It contributes no score. The current design evaluates the overall effect of the branch policy. Matching continuation windows and logging detailed internal search trajectories would answer a different mechanism question.

## 8. Conclusion

Under the current 90 s conditions, the extra external GPX2 stage produced no clear average tour-quality advantage over continuation from the shortest parent. M and K had shorter average tours than the configured C reference on their valid paired samples. Earlier V22 and R4 outcomes remain separate. Reporting map-level effects, charged preparation, delivery and invalid attempts makes the observed trade-off visible.

## Reproducibility and declarations

The author-review artifact contains the current numeric ledger, input and version manifests, a separately runnable CSV statistics and plotting workflow, and route-hash and length verification material. Existing tours can be checked against the exact coordinate bytes and authorized city-order files. The author-access appendix identifies the public sources, the items requiring authorized transfer, and the materials needed for a timed native Windows rerun. Access and redistribution are subject to the recorded terms. The release link for the previously analyzed batches is the [historical review repository](https://github.com/wang-d-c/TSP-SCI-Reproducibility-And-Evidence-20261118). Those public numerical records and historical route checks pertain to V22 and R4.

Authors, affiliations, corresponding author contact, final approval, funding and competing interests are to be confirmed by the authors before submission.

## AI assistance

ChatGPT and Codex assisted research design, code development, analysis and manuscript preparation. The authors will confirm the scope, placement and wording of the disclosure against the selected journal policy before submission and will take responsibility for the submitted text and evidence.

## References

1. Helsgaun, K. (2000). An effective implementation of the Lin–Kernighan traveling salesman heuristic. *European Journal of Operational Research*, 126(1), 106–130. https://doi.org/10.1016/S0377-2217(99)00284-2
2. Tinós, R., Helsgaun, K., & Whitley, D. (2018). Efficient recombination in the Lin–Kernighan–Helsgaun traveling salesman heuristic. *Parallel Problem Solving from Nature*, LNCS 11101, 95–107. https://doi.org/10.1007/978-3-319-99253-2_8
3. Tinós, R., Whitley, D., & Ochoa, G. (2020; online 2019). A new generalized partition crossover for the traveling salesman problem: Tunneling between local optima. *Evolutionary Computation*, 28(2), 255–288. https://doi.org/10.1162/evco_a_00254
4. Hains, D., Whitley, D., & Howe, A. (2012). Improving Lin–Kernighan–Helsgaun with crossover on clustered instances of the TSP. *PPSN XII*, 388–397. https://doi.org/10.1007/978-3-642-32964-7_39
5. Helsgaun, K. (2009). General k-opt submoves for the Lin–Kernighan TSP heuristic. *Mathematical Programming Computation*, 1, 119–163. https://doi.org/10.1007/s12532-009-0004-6
6. Helsgaun, K. (2017). An extension of the Lin–Kernighan–Helsgaun TSP solver for constrained traveling salesman and vehicle routing problems. Technical report, Roskilde University. https://forskning.ruc.dk/da/publications/an-extension-of-the-lin-kernighan-helsgaun-tsp-solver-for-constra/
7. Taillard, É. D., & Helsgaun, K. (2019). POPMUSIC for the travelling salesman problem. *European Journal of Operational Research*, 272(2), 420–429. https://doi.org/10.1016/j.ejor.2018.06.039
8. Friedrich, T., Kötzing, T., & Wagner, M. (2017). A generic bet-and-run strategy for speeding up stochastic local search. *AAAI Conference on Artificial Intelligence*, 31, 801–807. https://doi.org/10.1609/aaai.v31i1.10645
9. Weise, T., Wu, Z., & Wagner, M. (2019). An improved generic bet-and-run strategy with performance prediction for stochastic local search. *AAAI Conference on Artificial Intelligence*, 33, 2395–2402. https://doi.org/10.1609/aaai.v33i01.33012395
10. Zhang, W., & Looks, M. (2005). A novel local search algorithm for the traveling salesman problem that exploits backbones. *IJCAI*, 343–349. https://ijcai.org/proceedings/2005/182
11. Heins, J., Schäpermeier, L., Kerschke, P., & Whitley, D. (2024). Dancing to the state of the art? How candidate lists influence LKH for solving the traveling salesperson problem. *PPSN XVIII*, LNCS 15148, 100–115. https://doi.org/10.1007/978-3-031-70055-2_7
12. de Carvalho, O. Q., & Whitley, D. (2025). Dramatically faster partition crossover for the traveling salesman problem. *GECCO ’25*, 818–826. https://doi.org/10.1145/3712256.3726465
13. McMenemy, P., Veerapen, N., Adair, J., & Ochoa, G. (2019). Rigorous performance analysis of state-of-the-art TSP heuristic solvers. *EvoCOP*, LNCS 11452, 99–114. https://doi.org/10.1007/978-3-030-16711-0_7. Associated dataset record: https://datastorre.stir.ac.uk/handle/11667/127 (CC BY 4.0 for the 14 included instance files).
14. Reinelt, G. (1991). TSPLIB—A traveling salesman problem library. *ORSA Journal on Computing*, 3(4), 376–384. https://doi.org/10.1287/ijoc.3.4.376
15. Kerschke, P., Kotthoff, L., Bossek, J., Hoos, H. H., & Trautmann, H. (2018). Leveraging TSP solver complementarity through machine learning. *Evolutionary Computation*, 26(4), 597–620. https://doi.org/10.1162/evco_a_00215
16. Nagata, Y., & Kobayashi, S. (2013). A powerful genetic algorithm using edge assembly crossover for the traveling salesman problem. *INFORMS Journal on Computing*, 25(2), 346–363. https://doi.org/10.1287/ijoc.1120.0506
