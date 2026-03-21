from __future__ import annotations

import argparse
import ast
import base64
import itertools
import json
import os
import pickle
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

EVENT_RESULT_CHANGED = "PY.DIFFTEST.RESULT_CHANGED"
EVENT_EXCEPTION_CHANGED = "PY.DIFFTEST.EXCEPTION_CHANGED"
SUPPORTED_ROOT = "python"
_RUNNER_SNIPPET = r'''
import base64
import contextlib
import importlib
import io
import json
import pickle
import sys
import warnings

payload = pickle.loads(base64.b64decode(sys.argv[1]))
module = importlib.import_module(payload["module"])
func = getattr(module, payload["function"])
args = payload["args"]
kwargs = payload["kwargs"]
trace_effects = payload["trace_effects"]
stdout = io.StringIO()
stderr = io.StringIO()
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            value = func(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001
        response = {
            "kind": "exception",
            "exception_type": type(exc).__name__,
            "exception_module": type(exc).__module__,
            "message": str(exc),
            "stdout": stdout.getvalue() if trace_effects else "",
            "stderr": stderr.getvalue() if trace_effects else "",
            "warnings": [str(item.message) for item in caught] if trace_effects else [],
        }
    else:
        serializable = False
        normalized_value = None
        try:
            normalized_value = json.loads(json.dumps(value, sort_keys=True))
            serializable = True
        except TypeError:
            normalized_value = None
        response = {
            "kind": "return",
            "return_type": type(value).__name__,
            "return_module": type(value).__module__,
            "serializable": serializable,
            "normalized_value": normalized_value,
            "repr": repr(value),
            "stdout": stdout.getvalue() if trace_effects else "",
            "stderr": stderr.getvalue() if trace_effects else "",
            "warnings": [str(item.message) for item in caught] if trace_effects else [],
        }
print(json.dumps(response, sort_keys=True))
'''


@dataclass(frozen=True)
class SupportedType:
    kind: str
    args: tuple["SupportedType", ...] = ()

    def describe(self) -> str:
        if not self.args:
            return self.kind
        return f"{self.kind}[{', '.join(arg.describe() for arg in self.args)}]"


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    annotation: SupportedType


@dataclass(frozen=True)
class FunctionCandidate:
    qualified_name: str
    module_name: str
    function_name: str
    relative_path: str
    lineno: int
    parameters: tuple[ParameterSpec, ...]
    return_annotation: SupportedType


@dataclass
class DifferentialEntry:
    function: str
    status: str
    reason: str
    cases_executed: list[dict[str, Any]] = field(default_factory=list)
    mismatch: dict[str, Any] | None = None
    proofs: list[str] = field(default_factory=list)
    event: str | None = None


@dataclass
class DifferentialOutcome:
    differential_tests: list[DifferentialEntry]

    def to_json(self) -> dict[str, Any]:
        return {"differential_tests": [asdict(item) for item in self.differential_tests]}


@dataclass(frozen=True)
class DifferentialConfig:
    repo_root: Path
    base_ref: str
    head_ref: str = "HEAD"
    source_root: str = SUPPORTED_ROOT
    result_path: Path = Path("result.json")
    max_cases: int = 12
    max_depth: int = 2
    timeout_seconds: float = 2.0
    trace_effects: bool = False


def _run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepoSnapshot:
    ref: str
    files: dict[str, str]


@dataclass
class SelectionRecord:
    candidate: FunctionCandidate | None = None
    skip_reason: str | None = None


@dataclass
class FunctionExecutionResult:
    status: str
    payload: dict[str, Any]


def load_snapshot(repo_root: Path, ref: str, source_root: str = SUPPORTED_ROOT) -> RepoSnapshot:
    try:
        listing = _run_git(repo_root, "ls-tree", "-r", "--name-only", ref, source_root)
    except subprocess.CalledProcessError as exc:
        raise SnapshotError(f"Impossible de lister {ref}: {exc.stderr.strip()}") from exc

    files: dict[str, str] = {}
    for raw_path in listing.splitlines():
        path = raw_path.strip()
        if not path.endswith(".py"):
            continue
        try:
            content = _run_git(repo_root, "show", f"{ref}:{path}")
        except subprocess.CalledProcessError as exc:
            raise SnapshotError(f"Impossible de lire {ref}:{path}: {exc.stderr.strip()}") from exc
        files[path] = content
    return RepoSnapshot(ref=ref, files=files)


def _module_name_from_path(relative_path: str, source_root: str) -> str:
    rel = Path(relative_path).relative_to(source_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _parse_supported_type(annotation: ast.AST, max_depth: int, depth: int = 0) -> SupportedType | None:
    if depth > max_depth:
        return None
    if isinstance(annotation, ast.Name):
        if annotation.id in {"bool", "int", "float", "str"}:
            return SupportedType(annotation.id)
        if annotation.id == "None":
            return SupportedType("None")
        return None
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return SupportedType("None")
    if isinstance(annotation, ast.Subscript):
        base_name = _annotation_name(annotation.value)
        args = _subscript_args(annotation)
        if base_name in {"Optional", "typing.Optional"} and len(args) == 1:
            child = _parse_supported_type(args[0], max_depth, depth + 1)
            if child is not None:
                return SupportedType("optional", (child,))
        if base_name in {"list", "typing.List"} and len(args) == 1:
            child = _parse_supported_type(args[0], max_depth, depth + 1)
            if child is not None:
                return SupportedType("list", (child,))
        if base_name in {"tuple", "typing.Tuple"} and args:
            children = tuple(
                child
                for child in (
                    _parse_supported_type(item, max_depth, depth + 1) for item in args
                )
                if child is not None
            )
            if len(children) == len(args):
                return SupportedType("tuple", children)
        if base_name in {"dict", "typing.Dict"} and len(args) == 2:
            key_type = _parse_supported_type(args[0], max_depth, depth + 1)
            value_type = _parse_supported_type(args[1], max_depth, depth + 1)
            if key_type == SupportedType("str") and value_type is not None:
                return SupportedType("dict", (key_type, value_type))
        return None
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        left = _parse_supported_type(annotation.left, max_depth, depth + 1)
        right = _parse_supported_type(annotation.right, max_depth, depth + 1)
        if left == SupportedType("None") and right is not None:
            return SupportedType("optional", (right,))
        if right == SupportedType("None") and left is not None:
            return SupportedType("optional", (left,))
    return None


def _annotation_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _annotation_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _subscript_args(node: ast.Subscript) -> list[ast.AST]:
    if isinstance(node.slice, ast.Tuple):
        return list(node.slice.elts)
    return [node.slice]


class PureLikeAnalyzer(ast.NodeVisitor):
    _DISALLOWED_CALLS = {
        "print",
        "open",
        "input",
        "exec",
        "eval",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "__import__",
    }
    _DISALLOWED_MODULES = {"os", "sys", "subprocess", "socket", "pathlib", "random", "time"}

    def __init__(self) -> None:
        self.reasons: list[str] = []

    def visit_Global(self, node: ast.Global) -> None:
        self.reasons.append("écriture globale interdite")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.reasons.append("écriture nonlocal interdite")

    def visit_Delete(self, node: ast.Delete) -> None:
        self.reasons.append("suppression d'état interdite")

    def visit_With(self, node: ast.With) -> None:
        self.reasons.append("bloc with potentiellement impur")

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.reasons.append("async with interdit")

    def visit_Await(self, node: ast.Await) -> None:
        self.reasons.append("await interdit")

    def visit_Yield(self, node: ast.Yield) -> None:
        self.reasons.append("yield interdit")

    def visit_YieldFrom(self, node: ast.YieldFrom) -> None:
        self.reasons.append("yield from interdit")

    def visit_Import(self, node: ast.Import) -> None:
        self.reasons.append("import dynamique interdit")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.reasons.append("import dynamique interdit")

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node.func)
        if name in self._DISALLOWED_CALLS:
            self.reasons.append(f"appel impur détecté: {name}")
        if name and name.split(".")[0] in self._DISALLOWED_MODULES:
            self.reasons.append(f"appel module impur détecté: {name}")
        self.generic_visit(node)


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


ALLOWED_BUILTIN_CALLS = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "range",
    "reversed",
    "round",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
}


def _is_probably_pure(function_node: ast.FunctionDef) -> tuple[bool, str | None]:
    analyzer = PureLikeAnalyzer()
    analyzer.visit(function_node)
    for child in ast.walk(function_node):
        if isinstance(child, ast.Call):
            name = _call_name(child.func)
            if name and "." not in name and name not in ALLOWED_BUILTIN_CALLS:
                continue
    if analyzer.reasons:
        return False, "; ".join(dict.fromkeys(analyzer.reasons))
    return True, None


def collect_candidates(snapshot: RepoSnapshot, source_root: str = SUPPORTED_ROOT, max_depth: int = 2) -> dict[str, SelectionRecord]:
    selected: dict[str, SelectionRecord] = {}
    for relative_path, source in snapshot.files.items():
        module_name = _module_name_from_path(relative_path, source_root)
        tree = ast.parse(source, filename=relative_path)
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef):
                qualified_name = f"{module_name}.{node.name}"
                selected[qualified_name] = SelectionRecord(skip_reason=_skip_message(relative_path, node.lineno, "fonction async exclue"))
                continue
            if not isinstance(node, ast.FunctionDef):
                continue
            qualified_name = f"{module_name}.{node.name}"
            if any(isinstance(child, (ast.Yield, ast.YieldFrom)) for child in ast.walk(node)):
                selected[qualified_name] = SelectionRecord(skip_reason=_skip_message(relative_path, node.lineno, "générateur exclu"))
                continue
            if node.args.vararg or node.args.kwarg:
                selected[qualified_name] = SelectionRecord(skip_reason=_skip_message(relative_path, node.lineno, "*args/**kwargs non supportés"))
                continue
            if node.args.posonlyargs:
                selected[qualified_name] = SelectionRecord(skip_reason=_skip_message(relative_path, node.lineno, "paramètres positionnels-only exclus"))
                continue
            parameters: list[ParameterSpec] = []
            unsupported = None
            for arg in node.args.args + node.args.kwonlyargs:
                annotation = arg.annotation
                if annotation is None:
                    unsupported = f"annotation manquante pour {arg.arg}"
                    break
                parsed = _parse_supported_type(annotation, max_depth)
                if parsed is None:
                    unsupported = f"type non supporté pour {arg.arg}"
                    break
                parameters.append(ParameterSpec(name=arg.arg, annotation=parsed))
            return_annotation = _parse_supported_type(node.returns, max_depth) if node.returns else None
            if unsupported is None and return_annotation is None:
                unsupported = "type de retour non supporté"
            if unsupported is not None:
                selected[qualified_name] = SelectionRecord(skip_reason=_skip_message(relative_path, node.lineno, unsupported))
                continue
            pure_like, reason = _is_probably_pure(node)
            if not pure_like:
                selected[qualified_name] = SelectionRecord(skip_reason=_skip_message(relative_path, node.lineno, f"fonction jugée non pure-like: {reason}"))
                continue
            selected[qualified_name] = SelectionRecord(
                candidate=FunctionCandidate(
                    qualified_name=qualified_name,
                    module_name=module_name,
                    function_name=node.name,
                    relative_path=relative_path,
                    lineno=node.lineno,
                    parameters=tuple(parameters),
                    return_annotation=return_annotation,
                )
            )
    return selected


def _skip_message(relative_path: str, lineno: int, reason: str) -> str:
    return f"{reason} @ {relative_path}:{lineno}"


def _value_pool(type_spec: SupportedType, max_depth: int) -> list[Any]:
    if max_depth < 0:
        return []
    if type_spec.kind == "bool":
        return [False, True]
    if type_spec.kind == "int":
        return [-1, 0, 1, 2]
    if type_spec.kind == "float":
        return [-1.5, 0.0, 1.5]
    if type_spec.kind == "str":
        return ["", "a", "xy"]
    if type_spec.kind == "None":
        return [None]
    if type_spec.kind == "optional":
        return [None, *_value_pool(type_spec.args[0], max_depth - 1)]
    if type_spec.kind == "list":
        child_values = _value_pool(type_spec.args[0], max_depth - 1)[:2]
        return [[], child_values[:1], child_values[:2]]
    if type_spec.kind == "tuple":
        child_pools = [_value_pool(item, max_depth - 1)[:2] for item in type_spec.args]
        tuples = [tuple(values) for values in itertools.product(*child_pools)]
        return tuples[:3] if tuples else [tuple()]
    if type_spec.kind == "dict":
        child_values = _value_pool(type_spec.args[1], max_depth - 1)[:2]
        values: list[dict[str, Any]] = [{}]
        if child_values:
            values.append({"k": child_values[0]})
        if len(child_values) > 1:
            values.append({"x": child_values[0], "y": child_values[1]})
        return values
    raise ValueError(f"Unsupported type kind: {type_spec.kind}")


def generate_cases(candidate: FunctionCandidate, max_cases: int, max_depth: int) -> list[dict[str, Any]]:
    pools = [_value_pool(param.annotation, max_depth) for param in candidate.parameters]
    cases: list[dict[str, Any]] = []
    for combination in itertools.product(*pools):
        args = {param.name: value for param, value in zip(candidate.parameters, combination)}
        cases.append(args)
        if len(cases) >= max_cases:
            break
    return cases


def _materialize_snapshot(snapshot: RepoSnapshot, root_dir: Path) -> None:
    for relative_path, content in snapshot.files.items():
        destination = root_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


def _execute_case(
    snapshot_dir: Path,
    candidate: FunctionCandidate,
    case: dict[str, Any],
    timeout_seconds: float,
    trace_effects: bool,
) -> FunctionExecutionResult:
    payload = {
        "module": candidate.module_name,
        "function": candidate.function_name,
        "args": [case[param.name] for param in candidate.parameters],
        "kwargs": {},
        "trace_effects": trace_effects,
    }
    encoded = base64.b64encode(pickle.dumps(payload)).decode("ascii")
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH")
    import_root = snapshot_dir / SUPPORTED_ROOT
    environment["PYTHONPATH"] = str(import_root) if not existing else f"{import_root}{os.pathsep}{existing}"
    try:
        completed = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(_RUNNER_SNIPPET), encoded],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=environment,
            check=True,
        )
    except subprocess.TimeoutExpired:
        return FunctionExecutionResult(status="timeout", payload={"message": f"timeout après {timeout_seconds}s"})
    except subprocess.CalledProcessError as exc:
        return FunctionExecutionResult(
            status="error",
            payload={
                "message": "subprocess en erreur",
                "stdout": exc.stdout,
                "stderr": exc.stderr,
            },
        )
    return FunctionExecutionResult(status="run", payload=json.loads(completed.stdout))


def compare_execution(old_result: dict[str, Any], new_result: dict[str, Any], trace_effects: bool) -> tuple[str | None, dict[str, Any] | None]:
    if old_result["kind"] == "exception" or new_result["kind"] == "exception":
        old_exc = f"{old_result.get('exception_module')}.{old_result.get('exception_type')}" if old_result["kind"] == "exception" else None
        new_exc = f"{new_result.get('exception_module')}.{new_result.get('exception_type')}" if new_result["kind"] == "exception" else None
        if old_exc != new_exc:
            return EVENT_EXCEPTION_CHANGED, {"old_exception": old_exc, "new_exception": new_exc}
        if trace_effects:
            trace_mismatch = _trace_mismatch(old_result, new_result)
            if trace_mismatch is not None:
                return EVENT_EXCEPTION_CHANGED, trace_mismatch
        return None, None

    old_type = f"{old_result['return_module']}.{old_result['return_type']}"
    new_type = f"{new_result['return_module']}.{new_result['return_type']}"
    if old_type != new_type:
        return EVENT_RESULT_CHANGED, {"old_return_type": old_type, "new_return_type": new_type}
    if old_result.get("serializable") and new_result.get("serializable"):
        if old_result.get("normalized_value") != new_result.get("normalized_value"):
            return EVENT_RESULT_CHANGED, {
                "old_value": old_result.get("normalized_value"),
                "new_value": new_result.get("normalized_value"),
            }
    if trace_effects:
        trace_mismatch = _trace_mismatch(old_result, new_result)
        if trace_mismatch is not None:
            return EVENT_RESULT_CHANGED, trace_mismatch
    return None, None


def _trace_mismatch(old_result: dict[str, Any], new_result: dict[str, Any]) -> dict[str, Any] | None:
    trace_keys = ["stdout", "stderr", "warnings"]
    delta = {key: {"old": old_result.get(key), "new": new_result.get(key)} for key in trace_keys if old_result.get(key) != new_result.get(key)}
    return {"trace": delta} if delta else None


def run_differential_analysis(config: DifferentialConfig) -> DifferentialOutcome:
    base_snapshot = load_snapshot(config.repo_root, config.base_ref, config.source_root)
    head_snapshot = load_snapshot(config.repo_root, config.head_ref, config.source_root)
    base_candidates = collect_candidates(base_snapshot, config.source_root, config.max_depth)
    head_candidates = collect_candidates(head_snapshot, config.source_root, config.max_depth)

    functions = sorted(set(base_candidates) | set(head_candidates))
    entries: list[DifferentialEntry] = []
    with tempfile.TemporaryDirectory(prefix="diff-base-") as base_dir_raw, tempfile.TemporaryDirectory(prefix="diff-head-") as head_dir_raw:
        base_dir = Path(base_dir_raw)
        head_dir = Path(head_dir_raw)
        _materialize_snapshot(base_snapshot, base_dir)
        _materialize_snapshot(head_snapshot, head_dir)

        for qualified_name in functions:
            base_record = base_candidates.get(qualified_name)
            head_record = head_candidates.get(qualified_name)
            if base_record is None or head_record is None:
                reason = "fonction absente de base ou head"
                if base_record is None and head_record and head_record.skip_reason:
                    reason = head_record.skip_reason
                elif head_record is None and base_record and base_record.skip_reason:
                    reason = base_record.skip_reason
                entries.append(DifferentialEntry(function=qualified_name, status="skip", reason=reason, proofs=["présence asymétrique entre snapshots"]))
                continue
            if base_record.skip_reason or head_record.skip_reason:
                reason = base_record.skip_reason or head_record.skip_reason or "fonction exclue"
                entries.append(DifferentialEntry(function=qualified_name, status="skip", reason=reason, proofs=["sélection différentielle filtrée"]))
                continue
            base_candidate = base_record.candidate
            head_candidate = head_record.candidate
            if base_candidate is None or head_candidate is None:
                entries.append(DifferentialEntry(function=qualified_name, status="skip", reason="candidat incomplet", proofs=["analyse AST incomplète"]))
                continue
            cases = generate_cases(head_candidate, config.max_cases, config.max_depth)
            if not cases:
                entries.append(DifferentialEntry(function=qualified_name, status="skip", reason="aucun cas déterministe généré", proofs=["générateur borné vide"]))
                continue
            mismatch: dict[str, Any] | None = None
            proofs: list[str] = []
            status = "run"
            reason = "comparaison exécutée"
            executed_cases: list[dict[str, Any]] = []
            event: str | None = None
            for case in cases:
                old_execution = _execute_case(base_dir, base_candidate, case, config.timeout_seconds, config.trace_effects)
                new_execution = _execute_case(head_dir, head_candidate, case, config.timeout_seconds, config.trace_effects)
                executed_cases.append({"inputs": case, "old_status": old_execution.status, "new_status": new_execution.status})
                if old_execution.status == "timeout" or new_execution.status == "timeout":
                    status = "timeout"
                    reason = "timeout subprocess"
                    mismatch = {"old": old_execution.payload, "new": new_execution.payload}
                    proofs.append(f"timeout sur le cas {case}")
                    break
                if old_execution.status == "error" or new_execution.status == "error":
                    status = "error"
                    reason = "erreur subprocess"
                    mismatch = {"old": old_execution.payload, "new": new_execution.payload}
                    proofs.append(f"erreur subprocess sur le cas {case}")
                    break
                event, mismatch = compare_execution(old_execution.payload, new_execution.payload, config.trace_effects)
                if event is not None:
                    proofs.append(f"divergence détectée sur le cas {case}")
                    mismatch = {
                        "event": event,
                        "details": mismatch,
                        "old": old_execution.payload,
                        "new": new_execution.payload,
                    }
                    reason = "différence observée"
                    break
            entries.append(
                DifferentialEntry(
                    function=qualified_name,
                    status=status,
                    reason=reason,
                    cases_executed=executed_cases,
                    mismatch=mismatch,
                    proofs=proofs or [f"{len(executed_cases)} cas exécuté(s)"],
                    event=event,
                )
            )
    outcome = DifferentialOutcome(differential_tests=entries)
    _write_result(config.result_path, outcome)
    return outcome


def _write_result(result_path: Path, outcome: DifferentialOutcome) -> None:
    if result_path.exists():
        current = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        current = {}
    current.update(outcome.to_json())
    result_path.write_text(json.dumps(current, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic Python differential tests between two git refs.")
    parser.add_argument("base_ref", help="Git ref used as the baseline snapshot.")
    parser.add_argument("--head-ref", default="HEAD", help="Git ref used as the head snapshot.")
    parser.add_argument("--repo-root", default=".", help="Repository root containing the Python sources.")
    parser.add_argument("--source-root", default=SUPPORTED_ROOT, help="Subdirectory containing Python modules.")
    parser.add_argument("--result-path", default="result.json", help="Path to the JSON result file to update.")
    parser.add_argument("--max-cases", type=int, default=12, help="Maximum deterministic cases per function.")
    parser.add_argument("--max-depth", type=int, default=2, help="Maximum recursive depth for supported input types.")
    parser.add_argument("--timeout-seconds", type=float, default=2.0, help="Timeout applied to each subprocess execution.")
    parser.add_argument("--trace-effects", action="store_true", help="Capture stdout/stderr/warnings and compare them too.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = DifferentialConfig(
        repo_root=Path(args.repo_root).resolve(),
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        source_root=args.source_root,
        result_path=Path(args.result_path),
        max_cases=args.max_cases,
        max_depth=args.max_depth,
        timeout_seconds=args.timeout_seconds,
        trace_effects=args.trace_effects,
    )
    outcome = run_differential_analysis(config)
    print(json.dumps(outcome.to_json(), indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
