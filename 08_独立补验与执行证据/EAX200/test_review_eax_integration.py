"""No native dispatch. Verify decimal output recounts and isolated gate binding."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import review_eax_bindings as binding
import run_review_eax as controller


class ReviewEAXIntegration(unittest.TestCase):
    def test_decimal_callbacks_agree_with_frozen_delivered_route(self):
        panel = controller.PANEL_INPUTS / 'usa13509.tsp'
        for row in controller.csv_rows(controller.PLAN):
            if row['map'] != 'usa13509' or row['method'] != 'C_ref':
                continue
            result = controller.STATE / 'main' / f"{int(row['slot']):04d}" / 'terminal.json'
            result = binding.read(result)
            if result['status'] == 'valid':
                break
        self.assertEqual(result['status'], 'valid')
        score = result['result']
        fake = SimpleNamespace(batch=SimpleNamespace(), registry=SimpleNamespace())
        binding.install_outer_callbacks(fake)
        replay1 = fake.batch.import_recount().verify(panel, score['route'])
        replay2 = fake.registry.recount(panel, score['route'])
        self.assertEqual(replay1['euc_2d_integer_length'], score['length'])
        self.assertEqual(replay2['length'], score['length'])
        self.assertEqual(replay1['route_sha256'], replay2['route_sha256'])
        self.assertEqual(replay1['route_sha256'], score['route_sha256'])
        self.assertEqual(replay1['problem_sha256'], replay2['map_sha256'])

    def test_qualification_dispatch_protected(self):
        self.dispatch_fixture('qualification')

    def test_formal_dispatch_requires_matching_gate(self):
        self.dispatch_fixture('formal')

    def dispatch_fixture(self, scope):
        with tempfile.TemporaryDirectory(prefix='cmk_eax_gate_nonsolving_') as d:
            test_dir = Path(d)
            observer = test_dir / 'eax_decimal_observer.py'
            observer.write_text('# no executable, test sentinel only', encoding='utf-8')
            problem = test_dir / 'input.tsp'
            problem.write_text('outside the real study, test bytes', encoding='utf-8')
            candidate = test_dir / 'native.exe'
            candidate.write_text('no executable, test sentinel only', encoding='utf-8')
            attempt = 'x1'
            item = {'map': 'test fixture only'}
            contract = test_dir / 'runtime_contract.json'
            contract.write_text(json.dumps({'cutoffs_s': binding.CUTS, 'run_root': str(test_dir / 'runs'), 'qualification_cases': [item],
                                            'planned_eax_rows': [item]}), encoding='utf-8')
            admission = test_dir / 'formal_admission.json'
            work = test_dir / 'runs' / scope / attempt / 'w'
            args = SimpleNamespace(output=work, seed=1, run_id='test-fixture', method='EAX_r',
                                   problem=problem, exe=candidate, cpu=0)
            with patch.object(binding, 'ROOT', test_dir):
                dispatch = binding.bound_dispatch_path(scope, attempt)
                dispatch.parent.mkdir(parents=True)
                record = {'scope': scope, 'run_id': args.run_id, 'seed': args.seed, 'cpu': args.cpu,
                          'method': args.method, 'cutoffs_s': binding.CUTS, 'work': str(work),
                          'problem': str(problem), 'native': str(candidate), 'native_sha256': binding.NATIVE_SHA,
                          'wrapper_sha256': binding.sha(observer), 'input_sha256': binding.sha(problem),
                          'runtime_contract_sha256': binding.sha(contract), 'source_row': item,
                          'admission_sha256': None}
                dispatch.write_text(json.dumps(record), encoding='utf-8')
                if scope == 'formal':
                    with self.assertRaises(FileNotFoundError):
                        binding.verify_dispatch(args)
                    admission.write_text(json.dumps({'admitted': True,
                                                     'runtime_contract_sha256': binding.sha(contract)}), encoding='utf-8')
                    record['admission_sha256'] = binding.sha(admission)
                    dispatch.write_text(json.dumps(record), encoding='utf-8')
                binding.verify_dispatch(args)
                args.seed = 2
                with self.assertRaisesRegex(ValueError, 'recorded dispatch'):
                    binding.verify_dispatch(args)
                args.seed = 1
                problem.write_text('incorrect changed bytes', encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'dispatch hash'):
                    binding.verify_dispatch(args)

    def test_archived_native_pe_unchanged(self):
        ancestry = controller.get_ancestry()
        native, runtime = ancestry.established_runtime()
        self.assertEqual(binding.sha(native), binding.NATIVE_SHA)
        self.assertEqual(runtime[str(native)], binding.NATIVE_SHA)
        self.assertEqual(controller.pe_format(native), 'PE32+ x86_64')
        self.assertEqual(len(controller.read_planned_rows()), 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
