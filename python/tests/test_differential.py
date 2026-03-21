from __future__ import annotations

import json
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from specfence_py.differential import (
    DifferentialConfig,
    EVENT_EXCEPTION_CHANGED,
    EVENT_RESULT_CHANGED,
    FunctionCandidate,
    ParameterSpec,
    RepoSnapshot,
    SupportedType,
    collect_candidates,
    compare_execution,
    generate_cases,
    run_differential_analysis,
)


class DifferentialHelpersTests(unittest.TestCase):
    def test_collect_candidates_filters_async_and_generator(self) -> None:
        snapshot = RepoSnapshot(
            ref="HEAD",
            files={
                "python/pkg/sample.py": textwrap.dedent(
                    """
                    async def async_fn(x: int) -> int:
                        return x

                    def gen_fn(x: int) -> int:
                        yield x

                    def ok(x: int) -> int:
                        return x + 1
                    """
                )
            },
        )

        records = collect_candidates(snapshot, source_root="python", max_depth=2)

        self.assertIn("pkg.sample.async_fn", records)
        self.assertTrue(records["pkg.sample.async_fn"].skip_reason)
        self.assertIn("pkg.sample.gen_fn", records)
        self.assertTrue(records["pkg.sample.gen_fn"].skip_reason)
        self.assertIsNotNone(records["pkg.sample.ok"].candidate)

    def test_generate_cases_is_deterministic_and_bounded(self) -> None:
        candidate = FunctionCandidate(
            qualified_name="pkg.sample.combine",
            module_name="pkg.sample",
            function_name="combine",
            relative_path="python/pkg/sample.py",
            lineno=1,
            parameters=(
                ParameterSpec("flag", SupportedType("bool")),
                ParameterSpec("items", SupportedType("list", (SupportedType("int"),))),
            ),
            return_annotation=SupportedType("int"),
        )

        cases = generate_cases(candidate, max_cases=4, max_depth=2)

        self.assertEqual(4, len(cases))
        self.assertEqual({"flag": False, "items": []}, cases[0])
        self.assertEqual(cases, generate_cases(candidate, max_cases=4, max_depth=2))

    def test_compare_execution_detects_result_and_exception_changes(self) -> None:
        event, mismatch = compare_execution(
            {"kind": "return", "return_module": "builtins", "return_type": "int", "serializable": True, "normalized_value": 1},
            {"kind": "return", "return_module": "builtins", "return_type": "int", "serializable": True, "normalized_value": 2},
            trace_effects=False,
        )
        self.assertEqual(EVENT_RESULT_CHANGED, event)
        self.assertEqual({"old_value": 1, "new_value": 2}, mismatch)

        event, mismatch = compare_execution(
            {"kind": "exception", "exception_module": "builtins", "exception_type": "ValueError"},
            {"kind": "return", "return_module": "builtins", "return_type": "int", "serializable": True, "normalized_value": 2},
            trace_effects=False,
        )
        self.assertEqual(EVENT_EXCEPTION_CHANGED, event)
        self.assertEqual({"old_exception": "builtins.ValueError", "new_exception": None}, mismatch)


class DifferentialIntegrationTests(unittest.TestCase):
    def test_run_differential_analysis_updates_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Codex"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "codex@example.com"], cwd=repo, check=True, capture_output=True)
            (repo / "python/pkg").mkdir(parents=True)
            (repo / "python/pkg/__init__.py").write_text("", encoding="utf-8")
            (repo / "python/pkg/sample.py").write_text(
                textwrap.dedent(
                    """
                    def stable(x: int) -> int:
                        return x + 1

                    def changed(x: int) -> int:
                        return x + 1
                    """
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "python/pkg/__init__.py", "python/pkg/sample.py"], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
            base_ref = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
            (repo / "python/pkg/sample.py").write_text(
                textwrap.dedent(
                    """
                    def stable(x: int) -> int:
                        return x + 1

                    def changed(x: int) -> int:
                        return x + 2
                    """
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "commit", "-am", "head"], cwd=repo, check=True, capture_output=True)

            result_path = repo / "result.json"
            outcome = run_differential_analysis(
                DifferentialConfig(repo_root=repo, base_ref=base_ref, head_ref="HEAD", result_path=result_path)
            )

            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertIn("differential_tests", payload)
            changed = next(item for item in outcome.differential_tests if item.function == "pkg.sample.changed")
            self.assertEqual("run", changed.status)
            self.assertEqual(EVENT_RESULT_CHANGED, changed.event)
            self.assertTrue(changed.mismatch)


if __name__ == "__main__":
    unittest.main()
