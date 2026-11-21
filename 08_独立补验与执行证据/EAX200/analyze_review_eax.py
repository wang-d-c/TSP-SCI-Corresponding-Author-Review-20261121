"""Re-audit all 200 finished R13 terminals and report only the new comparisons."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
from math import lcm
from pathlib import Path
import random
from statistics import mean, median

import run_review_eax as core
from review_eax_bindings import ensure, load, read, sha, write_new


CORE_600_SHA = 'f589f6382e02165ea575100b880b511b389a9691ce739feb638369d1d57bbbc7'
BOOTSTRAP_SEED = 20261120
BOOTSTRAP_REPEATS = 100_000
A02_POLICY = 'R13a02_kernel_action_audit'
A01_POLICY = 'R13a01_original_audit'


def comparison_summary(by_map):
    if not by_map:
        return {'maps': 0, 'mean_ppm': None, 'interval_95_ppm': None, 'two_sided_exact_signflip_p': None}
    exact_means = [mean(series) for _, series in sorted(by_map.items())]
    values = [float(value) for value in exact_means]
    denominator = lcm(*(value.denominator for value in exact_means))
    signed_terms = [value.numerator * (denominator // value.denominator) for value in exact_means]
    observed = abs(sum(signed_terms))
    signed_sum = -sum(signed_terms)
    extreme = int(abs(signed_sum) >= observed)
    previous_gray = 0
    for index in range(1, 1 << len(values)):
        gray = index ^ (index >> 1)
        changed = gray ^ previous_gray
        term = signed_terms[changed.bit_length() - 1]
        signed_sum += 2 * term if gray & changed else -2 * term
        extreme += abs(signed_sum) >= observed
        previous_gray = gray
    exact_p = extreme / (1 << len(values))
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    samples = sorted(sum(rng.choices(values, k=n)) / n for _ in range(BOOTSTRAP_REPEATS))
    endpoints = []
    for q in (0.025, 0.975):
        i = (len(samples) - 1) * q
        start = int(i)
        endpoints.append(samples[start] + (samples[start + 1] - samples[start]) * (i - start))
    return {'maps': n, 'mean_ppm': mean(values), 'interval_95_ppm': endpoints,
            'two_sided_exact_signflip_p': exact_p, 'short_tied_long': [
                sum(value > 0 for series in by_map.values() for value in series),
                sum(value == 0 for series in by_map.values() for value in series),
                sum(value < 0 for series in by_map.values() for value in series)],
            'n_valid_pairs': sum(len(series) for series in by_map.values())}


def write_csv(path, data):
    if not data:
        return
    with path.open('x', encoding='utf-8', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def analyze(saved_core, dest):
    ensure(sha(saved_core) == CORE_600_SHA, 'frozen portable 600-row core ledger differs')
    contract = read(core.CONTRACT)
    admitted = read(core.ADMISSION)
    ensure(admitted['admitted'] is True and admitted['runtime_contract_sha256'] == sha(core.CONTRACT),
           'supplemental phase lacks verified admission')
    planned = core.read_planned_rows()
    ensure(len(planned) == 200 and contract['planned_eax_rows'] == planned,
           'supplemental schedule differs from the 200 original EAX identities')
    terminal_list = []
    amendment_path = core.ROOT / 'r13_a02_continuation.json'
    amendment = read(amendment_path)
    expected_a01 = amendment['existing_79_result_hashes']
    ensure(amendment['policy'] == A02_POLICY and len(expected_a01) == 79 and
           amendment['original_runtime_contract_sha256'] == sha(core.CONTRACT) and
           amendment['original_actual_admission_sha256'] == sha(core.ADMISSION) and
           all(sha(Path(path)) == digest for path, digest in amendment['frozen_new_files'].items()),
           'continuation revision or immutable a01 boundary changed')
    first_failure = amendment['existing_failure']
    ensure(first_failure['label'] == 'e0316' and first_failure['retained_score'] is None,
           'the first failed slot is not frozen with its original null score')
    for row in planned:
        label = f"e{int(row['slot']):04d}"
        path = core.terminal_path('formal', label)
        ensure(path.is_file(), f'not completed: missing terminal for {label}')
        record = read(path)
        ensure(record['source_row'] == row and record['counts_as_formal'] is True and
               record['admission_sha256'] == sha(core.ADMISSION), f'{label}: wrong result identity')
        if label in expected_a01:
            ensure(sha(path) == expected_a01[label], f'{label}: earlier a01 formal result changed')
            policy = A01_POLICY
        else:
            ensure(record['terminal_status'] != 'valid' or record.get('postrun_audit_policy') == A02_POLICY,
                   f'{label}: a02 valid score has no bound decision version')
            policy = A02_POLICY
        if label == 'e0316':
            ensure(record['score'] is None and record['terminal_status'] == first_failure['retained_status'],
                   'first false rejection is permanently left as the original unscored outcome')
        terminal_list.append((label, row, path, record, policy))
    baseline = {(row['map'], row['seed'], row['method']): row for row in core.csv_rows(saved_core)}
    ensure(len(baseline) == 600, 'no duplicate core slot expected')
    exact = load('cmk_R13_post_run_independent', core.OLD_REVIEW / 'phase_b_numeric/euc2d_verify.py')
    checked_maps = {}
    outputs = []
    pairs = defaultdict(lambda: defaultdict(list))
    missing_pairs = defaultdict(Counter)
    strata = defaultdict(lambda: defaultdict(set))
    paired_rows = []
    for label, row, terminal_path, record, policy in terminal_list:
        run_path = Path(contract['run_root']) / 'formal' / label
        for name, digest in record['material_sha256'].items():
            ensure(sha(run_path / name) == digest, f'{label}: raw evidence digest changed')
        terminal_status = record['terminal_status']
        score = record['score']
        verified_route = False
        if terminal_status == 'valid':
            ensure(record['scope'] == 'formal' and record['complete_stop_proof'] and record['complete_candidate_ledger'],
                   'no score without complete accepted evidence')
            route_record = read(run_path / 'independent_validation.json')
            route = Path(route_record['route']).resolve(strict=True)
            ensure(route.is_relative_to(run_path.resolve()), 'route outside its own formal attempt')
            if row['map'] not in checked_maps:
                checked_maps[row['map']] = exact.read_problem(core.source_map(row, 'formal'))
            instance = checked_maps[row['map']]
            ensure(instance.digest == row['input_sha256'], 'original geometry changed after timed run')
            verified = exact.verify(instance, route, expected=int(score))
            ensure(verified['tour_sha256'] == record['route_sha256'], 'route identity differs on independent recount')
            verified_route = True
        else:
            ensure(score is None, 'environment or wrapper outcome must never score')
        wrapper_path = run_path / 'w' / 'result.json'
        wrapper = read(wrapper_path) if wrapper_path.is_file() else {}
        outer_path = run_path / 'result.json'
        outer = read(outer_path) if outer_path.is_file() else {}
        system = outer.get('system_validation') or {}
        children = wrapper.get('children', [])
        stop_record = wrapper.get('stop') or {}
        actual_kernel_calls = [(child.get('stop_proof') or {}).get('termination_call_s') for child in children]
        actual_kernel_calls = [value for value in actual_kernel_calls if isinstance(value, (int, float))]
        exit_observations = [child.get('cleanup_observed_s', child.get('exited_s')) for child in children]
        exit_observations = [value for value in exit_observations if isinstance(value, (int, float))]
        out = {'run_id': row['run_id'], 'map': row['map'], 'seed': row['pool_seed'], 'stratum': row['stratum'],
               'status': terminal_status, 'quality_if_valid': score, 'verified_independently': verified_route,
               'started_utc': record['started_utc'], 'terminal_utc': record['time_utc'],
               'published_candidates': record.get('published'), 'consumed_candidates': record.get('consumed'),
               'native_protocol': contract['version'],
               'postrun_audit_policy': policy,
               'stop_record_role': stop_record.get('action'), 'stop_record_s': stop_record.get('requested_s'),
               'stop_requested_s': stop_record.get('requested_s') if stop_record.get('action') == 'terminate_owned_job' else None,
               'actual_kernel_termination_call_s': max(actual_kernel_calls) if actual_kernel_calls else None,
               'stop_proven_s': record.get('last_native_stop_proof_s'),
               'last_wrapper_exit_observed_s': max(exit_observations) if exit_observations else None,
               'owner_cleanup_s': record.get('owned_cleanup_s'), 'committed_s': record.get('commit_s'),
               'wrapper_cpu_seconds_charged': wrapper.get('wrapper_cpu_seconds_charged'),
               'external_sampler_cpu_s': system.get('sampler_cpu_s'),
               'outer_controller_cpu_s': outer.get('controller_cpu_s'),
               'outer_controller_total_wall_s': outer.get('controller_total_wall_s'),
               'formal_terminal_sha256': sha(terminal_path), 'input_sha256': row['input_sha256'],
               'route_sha256': record.get('route_sha256', '')}
        outputs.append(out)
        for method in ('M_new', 'K_new'):
            core_row = baseline[row['map'], row['pool_seed'], method]
            if not verified_route or core_row['status'] != 'valid':
                reason = f"core:{core_row['status']}|supplement:{terminal_status}"
                missing_pairs[method][reason] += 1
                continue
            value = Fraction(10**6 * (int(score) - int(core_row['checked_length'])), int(score))
            pairs[method][row['map']].append(value)
            strata[method][row['stratum']].add(row['map'])
            paired_rows.append({'method': method, 'map': row['map'], 'seed': row['pool_seed'], 'stratum': row['stratum'],
                                'paired_core_length': core_row['checked_length'], 'later_eax_length': score,
                                'ppm': float(value), 'exact_ppm': str(value)})
    profiles = {}
    map_effect_rows = []
    for method in ('M_new', 'K_new'):
        profiles[method] = comparison_summary(pairs[method])
        profiles[method]['missing_pair_categories'] = dict(missing_pairs[method])
        profiles[method]['map_exact_means_ppm'] = {map_id: str(mean(vals)) for map_id, vals in sorted(pairs[method].items())}
        profiles[method]['descriptive_strata'] = {key: {
            'available_maps': len(available),
            'available_pairs': sum(len(pairs[method][name]) for name in available),
            'map_equal_mean_ppm': float(mean(mean(pairs[method][name]) for name in sorted(available))),
        } for key, available in sorted(strata[method].items())}
        for map_id, series in sorted(pairs[method].items()):
            map_effect = mean(series)
            map_effect_rows.append({'method': method, 'map': map_id, 'valid_pairs': len(series),
                                    'shorter': sum(value > 0 for value in series),
                                    'tied': sum(value == 0 for value in series),
                                    'longer': sum(value < 0 for value in series),
                                    'mean_ppm': float(map_effect), 'exact_mean_ppm': str(map_effect)})
    calculable = sorted((result['two_sided_exact_signflip_p'], method) for method, result in profiles.items()
                        if result['two_sided_exact_signflip_p'] is not None)
    running = 0.0
    for index, (raw, method) in enumerate(calculable):
        running = max(running, min(1.0, (2 - index) * raw))
        profiles[method]['supplementary_holm_two_contrasts'] = running
    version_timeline = {}
    for policy in (A01_POLICY, A02_POLICY):
        rows = [item for item in outputs if item['postrun_audit_policy'] == policy]
        version_timeline[policy] = {
            'terminal_rows': len(rows), 'delivery': dict(Counter(item['status'] for item in rows)),
            'earliest_started_utc': min(item['started_utc'] for item in rows),
            'latest_terminal_utc': max(item['terminal_utc'] for item in rows),
            'earliest_run_id': rows[0]['run_id'], 'last_run_id': rows[-1]['run_id'],
        }
    ensure(version_timeline[A01_POLICY]['terminal_rows'] == 79 and version_timeline[A02_POLICY]['terminal_rows'] == 121,
           'the a01 to a02 79/121 boundary differs from the frozen continuation')
    resources = {}
    for key in ('wrapper_cpu_seconds_charged', 'external_sampler_cpu_s', 'outer_controller_cpu_s',
                'outer_controller_total_wall_s'):
        values = [item[key] for item in outputs if item['verified_independently'] and item[key] is not None]
        if values:
            resources[key] = {'recorded_valid_runs': len(values), 'minimum_s': min(values),
                              'median_s': median(values), 'maximum_s': max(values)}
    report = {
        'scope': 'later independently executed EAX supplemental phase; frozen original 600 untouched',
        'notice': 'Comparisons use paired accepted original M/K and later EAX; periods differ. The original four-item Holm snapshot remains unchanged.',
        'planned': 200, 'terminals': len(outputs), 'delivery': dict(Counter(item['status'] for item in outputs)),
        'independent_recounts': sum(item['verified_independently'] for item in outputs),
        'earliest_started_utc': min(item['started_utc'] for item in outputs),
        'latest_terminal_utc': max(item['terminal_utc'] for item in outputs),
        'plan_sha256': contract['planned_main_sha256'], 'native_sha256': contract['native_sha256'],
        'protocol': contract['version'], 'frozen_core_ledger_sha256': sha(saved_core),
        'phase_of_each_result': version_timeline, 'a02_continuation_sha256': sha(amendment_path),
        'preserved_first_failure': {'label': 'e0316', 'status': first_failure['retained_status'], 'score': None},
        'timed_native_and_recording_unchanged_at_a02': True,
        'recorded_resource_metrics_valid_only': resources,
        'resource_metric_scope': ('Charged wrapper CPU covers timed discovery, validation and save coordination together. '
                                  'External sampler CPU and outer controller overhead are reported as recorded. '
                                  'Controller wall is administrative elapsed outside and around the charged task. '
                                  'These metrics are not added or interpreted as exclusive candidate cost.'),
        'bootstraps_per_qualifying_comparison': BOOTSTRAP_REPEATS, 'bootstrap_seed': BOOTSTRAP_SEED,
        'p_test_unit': 'independent map conditional sign-flip, with null sign-exchangeability assumption', 'profiles': profiles,
    }
    dest.mkdir()
    write_csv(dest / 'supplemental_eax_200.csv', outputs)
    write_csv(dest / 'supplemental_eax_valid_pairs.csv', paired_rows)
    write_csv(dest / 'supplemental_eax_map_effects.csv', map_effect_rows)
    write_new(dest / 'supplemental_eax_summary.json', report)
    write_human_summary(dest / 'supplemental_eax_results.md', report)
    manifest = [f'{sha(path)}  {path.name}' for path in sorted(dest.iterdir()) if path.is_file()]
    with (dest / 'SHA256SUMS').open('x', encoding='ascii', newline='\n') as target:
        target.write('\n'.join(manifest) + '\n')
    return report


def write_human_summary(path, summary):
    lines = [
        '# R13 原定 EAX 补充批次结果', '',
        f"本次完成原 200 行中的 {summary['terminals']} 个终态，独立验环核对全部 {summary['independent_recounts']} 条有效 EAX 路线。未派发项为零。", '',
        '| EAX 终态 | 槽数 |', '| --- | ---: |',
        *[f'| {key} | {value} |' for key, value in summary['delivery'].items()], '',
        '## 实际版本和时段', '',
        '| 事后核验版本 | 终态 | 首次派发 UTC | 最后终态 UTC |', '| --- | ---: | --- | --- |',
    ]
    for key, info in summary['phase_of_each_result'].items():
        lines.append(f"| {key} | {info['terminal_rows']} | {info['earliest_started_utc']} | {info['latest_terminal_utc']} |")
    lines += ['', '两段原生二进制、包装器、验证、计时和资源约束一致。a02 只修正事后停止判定，将真实内核终止动作与准备记时分开。e0316 原首次失败和空分保留。', '',
              '## 与冻结 M/K 的后补比较', '',
              '| 对照 | 有效配对数 | 地图数 | 短／平／长 | 地图等权相对减少 ppm | 95% 地图抽样区间 ppm | 地图级精确符号翻转 p |',
              '| --- | ---: | ---: | --- | ---: | --- | ---: |']
    for method, profile in summary['profiles'].items():
        if profile['maps'] == 0:
            lines.append(f'| {method} 对 EAX | 0 | 0 | 未估 | 未估 | 未估 | 未估 |')
            continue
        short_tie_long = ' / '.join(str(value) for value in profile['short_tied_long'])
        lo, hi = profile['interval_95_ppm']
        lines.append(f"| {method} 对 EAX | {profile['n_valid_pairs']} | {profile['maps']} | {short_tie_long} | "
                     f"{profile['mean_ppm']:+.3f} | [{lo:+.3f}, {hi:+.3f}] | {profile['two_sided_exact_signflip_p']:.6g} |")
    lines += ['', '相对差异以 EAX 长度为分母，正值表示对应 M 或 K 的路线更短。失败与缺失单列。早期 M/K 与 EAX 在不同时间段取得。原 600 项、已登记四项 Holm 家族及当时两个 EAX 占位完全保持。', '',
              '## 预算与资源记录', '',
              '候选发现、验环和保存都在计费任务内发生。系统采样随任务进行。历史记录可以区分下列进程费用，无法将其中的验证和落盘单独解释为独占墙钟开销。控制器总墙钟包含计时任务之外的管理阶段。下列数值不加总。', '',
              '| 实测项目 | 有效记录数 | 中位秒 | 范围秒 |', '| --- | ---: | ---: | --- |']
    resource_labels = {
        'wrapper_cpu_seconds_charged': '计费窗口内包装器 CPU', 'external_sampler_cpu_s': '独立资源采样 CPU',
        'outer_controller_cpu_s': '外层控制器 CPU', 'outer_controller_total_wall_s': '外层控制器总墙钟',
    }
    for key, values in summary['recorded_resource_metrics_valid_only'].items():
        lines.append(f"| {resource_labels[key]} | {values['recorded_valid_runs']} | {values['median_s']:.3f} | "
                     f"[{values['minimum_s']:.3f}, {values['maximum_s']:.3f}] |")
    lines += ['', '[200 项实际终态](supplemental_eax_200.csv) · [有效质量配对](supplemental_eax_valid_pairs.csv) · [逐地图效果](supplemental_eax_map_effects.csv) · [机器统计及四层分布](supplemental_eax_summary.json)', '']
    with path.open('x', encoding='utf-8', newline='\n') as target:
        target.write('\n'.join(lines))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--frozen-core-ledger', required=True, type=Path)
    cli.add_argument('--output', required=True, type=Path)
    args = cli.parse_args()
    result = analyze(args.frozen_core_ledger, args.output)
    print({key: result[key] for key in ('planned', 'terminals', 'delivery', 'independent_recounts')})
