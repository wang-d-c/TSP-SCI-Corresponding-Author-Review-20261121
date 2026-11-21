"""Generate order intervals and tail weights from unrounded matched route data."""
from collections import defaultdict
from csv import DictReader, DictWriter
import json
from pathlib import Path
import random
from statistics import mean, median


ROOT=Path(__file__).resolve().parent/'results'


def rows(name):
    with (ROOT/name).open(encoding='utf-8',newline='') as f:
        return list(DictReader(f))


def quartile(sorted_vals, q):
    idx=q*(len(sorted_vals)-1)
    lo=int(idx)
    return sorted_vals[lo]+(idx-lo)*(sorted_vals[min(lo+1,len(sorted_vals)-1)]-sorted_vals[lo])


all_pairs=rows('start_end_pairs.csv')
assert len(all_pairs)==198
by_map=defaultdict(list)
for row in all_pairs:
    by_map[row['map']].append(row)
assert len(by_map)==20
order=rows('order_by_map.csv')
differences=[float(row['K_first_minus_M_first_ppm']) for row in order]
assert len(differences)==len(by_map)
rng=random.Random(2026112114)
bs=sorted(mean(rng.choices(differences,k=len(differences))) for _ in range(20000))
without={m:[float(t['final_advantage_ppm']) for t in group if abs(float(t['final_advantage_ppm'])) < 1000] for m,group in by_map.items()}
output={'endpoint_ppm_primary_all':mean(mean(float(t['final_advantage_ppm']) for t in group) for group in by_map.values()),
        'endpoint_ppm_post_hoc_abs_lt_1000':mean(mean(group) for group in without.values()),
        'order_gap_ppm':mean(differences), 'order_gap_median_ppm':median(differences),
        'order_gap_map_bootstrap_95_ppm':[quartile(bs,q) for q in (.025,.975)],
        'bootstrap_draws':20000, 'bootstrap_seed':2026112114,
        'balanced_order_KM_ppm':mean((float(row['K_first_ppm'])+float(row['M_first_ppm']))/2 for row in order)}
raw=rows('tail_pairs.csv')
tails=[]
for row in raw:
    n=len(by_map[row['map']])
    tails.append({'map':row['map'],'seed':row['seed'],'valid_pairs_in_map':n,
         'start_advantage_ppm':row['start_advantage_ppm'],'final_advantage_ppm':row['final_advantage_ppm'],
         'M_own_start_gain_ppm':row['M_own_start_gain_ppm'],'K_own_start_gain_ppm':row['K_own_start_gain_ppm'],
         'contribution_primary_map_equal_ppm':float(row['final_advantage_ppm'])/(n*len(by_map))})
assert len(tails)==3
with (ROOT/'negative_tail_contributions.csv').open('w',encoding='utf-8',newline='') as f:
    w=DictWriter(f,fieldnames=list(tails[0]));w.writeheader();w.writerows(tails)
output['tails']=tails
(ROOT/'supplement_details.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
