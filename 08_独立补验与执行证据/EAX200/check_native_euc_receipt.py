"""Invoke GA-EAX's frozen --validate-input path without entering genetic search."""
from pathlib import Path
import subprocess

from decimal_eax_candidate import parse_coordinates
from review_eax_bindings import OUTPUTS, ROOT, NATIVE_SHA, ensure, read, sha, write_new


NATIVE_ROOT = OUTPUTS / 'lkh_v24_3_confirmation_20261116/formal_216/r4/eax_parser'


def main():
    manifest_path = NATIVE_ROOT / 'build_manifest.json'
    manifest = read(manifest_path)
    source_hashes = {row['name']: row['r4_sha256'] for row in manifest['files']}
    evidence = {}
    for basename in ('main.cpp', 'evaluator.cpp', 'indi.h', 'cross.cpp'):
        path = NATIVE_ROOT / 'source' / basename
        ensure(sha(path) == source_hashes[basename], 'frozen source changed: ' + basename)
        evidence[basename] = sha(path)
    ensure('using TourCost = std::int64_t;' in (NATIVE_ROOT / 'source' / 'indi.h').read_text(encoding='utf-8'),
           'native 64-bit TourCost declaration missing')
    native = Path(manifest['binary'])
    ensure(sha(native) == manifest['binary_sha256'] == NATIVE_SHA, 'wrong EAX executable')
    work = ROOT / 'native_static_fixture'
    work.mkdir()
    # Alternating signed magnitudes keep every edge below the original
    # neighbor sentinel while giving a closed-tour cost above uint32.
    dimension = 60
    city_rows = [f'{idx} {"-49000000.25" if idx % 2 else "49000000.25"} {idx}.125'
                 for idx in range(1, dimension + 1)]
    text = 'NAME: CMK_finite_signed_fractional_probe\nTYPE: TSP\nDIMENSION: 60\nEDGE_WEIGHT_TYPE: EUC_2D\n'
    text += 'NODE_COORD_SECTION\n' + '\n'.join(city_rows) + '\nEOF\n'
    instance = work / 'signed.tsp'
    instance.write_text(text, encoding='ascii')
    arcs = [(a, b) for a in range(1, dimension + 1) for b in range(a + 1, dimension + 1)]
    pair_file = work / 'pairs.txt'
    pair_file.write_text(''.join(f'{a} {b}\n' for a, b in arcs), encoding='ascii')
    native_output = work / 'eval.txt'
    invocation = [str(native), '--validate-input', str(instance), str(pair_file), str(native_output)]
    completed = subprocess.run(invocation, cwd=work, capture_output=True, text=True, timeout=15, check=True)
    ensure(not completed.stderr, 'frozen native validation emitted unexpected stderr')
    coordinates = parse_coordinates(text)
    measured_tour = None
    reported_pairs = reported_cities = 0
    model = []
    for a, b in arcs:
        x1, y1 = coordinates.points[a - 1]
        x2, y2 = coordinates.points[b - 1]
        # Independent squared half-distance comparison supports exactly finite decimals.
        from math import isqrt
        q = (x1 - x2)**2 + (y1 - y2)**2
        k = isqrt(q) // coordinates.scale
        model.append((a, b, k + (4 * q >= ((2 * k + 1) * coordinates.scale)**2)))
    for line in native_output.read_text(encoding='ascii').splitlines():
        fields = line.split()
        if fields[0] == 'N':
            ensure(fields == ['N', str(dimension)], 'native coordinate count differs')
        elif fields[0] == 'TYPE':
            ensure(fields == ['TYPE', 'EUC_2D'], 'native distance model differs')
        elif fields[0] == 'C':
            number, x, y = fields[1:]
            a, b = coordinates.points[int(number) - 1]
            ensure((float(x), float(y)) == (a / coordinates.scale, b / coordinates.scale),
                   'native signed decimal coordinate was changed')
            reported_cities += 1
        elif fields[0] == 'P':
            ensure(tuple(map(int, fields[1:])) == model[reported_pairs], 'native distance disagrees with exact EUC_2D')
            reported_pairs += 1
        elif fields[0] == 'PAIRS':
            ensure(int(fields[1]) == len(arcs) == reported_pairs, 'pair output incomplete')
        elif fields[0] == 'TOUR':
            measured_tour = int(fields[1])
        else:
            raise ValueError('unrecognized native output: ' + line)
    ensure(reported_cities == dimension and reported_pairs == len(arcs), 'native validation output incomplete')
    ensure(measured_tour == coordinates.length(list(range(1, dimension + 1))) and measured_tour > 2**32,
           'native validation tour did not preserve the 64-bit cost')
    write_new(ROOT / 'native_euc_static_receipt.json', {
        'scope': 'actual native read-only validation, zero EAX genetic search iterations or new scores',
        'executable_sha256': sha(native), 'build_manifest_sha256': sha(manifest_path),
        'checked_source_sha256': evidence, 'signed_fractional_coordinates_matched': reported_cities,
        'exact_edge_distances_matched': reported_pairs, 'closed_ordered_cost_int64': measured_tour,
        'synthetic_fixture_sha256': sha(instance), 'native_validator_output_sha256': sha(native_output),
        'native_exit_code': completed.returncode, 'formal_slots_started': 0,
    })
    print(f'passed native --validate-input without genetic search: {reported_cities} coordinates, '
          f'{reported_pairs} edges, 64-bit ordered cost {measured_tour}')


if __name__ == '__main__':
    main()
