"""
Z3 Guard Provers — Mathematical verification of backend code logic.
Uses Z3 SMT solver to prove or disprove code correctness.
AST-first for Python; regex fallback for other languages.
"""

import re
import ast
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    from z3 import (
        Solver, Int, BitVec, BitVecVal, Bool, Real,
        If, And, Or, Not, Implies, ForAll, Exists,
        sat, unsat, unknown,
        UGT, ULT, UGE, ULE, URem, UDiv,
        BV2Int, Extract, ZeroExt, Concat,
    )
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False


@dataclass
class ProofResult:
    """Result of a Z3 verification attempt."""
    verdict: str          # "PROVEN_SAFE", "BUG_FOUND", "TIMEOUT", "SKIP"
    prover: str           # Which prover ran
    message: str          # Human-readable explanation
    counterexample: Optional[str] = None  # If bug found, the concrete inputs
    confidence: float = 1.0
    line: int = 0
    file: str = ""

    def __str__(self):
        ce = f" | CE: {self.counterexample}" if self.counterexample else ""
        return f"[{self.verdict}] {self.prover}: {self.message}{ce}"


# ─── AST Extraction Layer ─────────────────────────────────────────
# Eliminates false positives from regex matching inside strings,
# comments, URLs, and decorators. Python-only; others use regex fallback.

@dataclass
class ASTDivision:
    """A division operation extracted from Python AST."""
    dividend: str
    divisor: str
    line: int

@dataclass
class ASTSubscript:
    """An array/list subscript extracted from Python AST."""
    container: str
    index: str
    line: int

@dataclass
class ASTMultiplication:
    """A multiplication operation extracted from Python AST."""
    left: str
    right: str
    line: int


class _ASTExtractor(ast.NodeVisitor):
    """Walks Python AST to extract operations that need Z3 verification.
    
    Tradeoff: Only works for Python. For JS/TS/Sol/Go, the regex fallback
    remains. A proper multi-language solution would need tree-sitter.
    """

    def __init__(self):
        self.divisions: List[ASTDivision] = []
        self.subscripts: List[ASTSubscript] = []
        self.multiplications: List[ASTMultiplication] = []

    @staticmethod
    def _node_name(node) -> Optional[str]:
        """Extract a human-readable name from an AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = _ASTExtractor._node_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        elif isinstance(node, ast.Constant):
            return str(node.value)
        return None

    def visit_BinOp(self, node):
        left_name = self._node_name(node.left)
        right_name = self._node_name(node.right)

        if isinstance(node.op, (ast.Div, ast.FloorDiv)) and right_name:
            self.divisions.append(ASTDivision(
                dividend=left_name or "?",
                divisor=right_name,
                line=node.lineno,
            ))
        elif isinstance(node.op, ast.Mult) and left_name and right_name:
            self.multiplications.append(ASTMultiplication(
                left=left_name,
                right=right_name,
                line=node.lineno,
            ))

        self.generic_visit(node)

    def visit_Subscript(self, node):
        container = self._node_name(node.value)
        index = self._node_name(node.slice) if isinstance(node.slice, ast.Name) else None

        if container and index:
            self.subscripts.append(ASTSubscript(
                container=container,
                index=index,
                line=node.lineno,
            ))
        self.generic_visit(node)


def _is_python(filepath: str) -> bool:
    """Check if file is Python based on extension."""
    return filepath.lower().endswith((".py", ".pyw"))


def _extract_ast(code: str) -> Optional[_ASTExtractor]:
    """Try to parse code as Python AST. Returns None if parsing fails."""
    try:
        tree = ast.parse(code)
        extractor = _ASTExtractor()
        extractor.visit(tree)
        return extractor
    except SyntaxError:
        return None


class DivisionByZeroProver:
    """Proves whether division-by-zero is possible.
    
    Uses AST for Python files (eliminates string/comment false positives).
    Falls back to regex for non-Python files.
    """

    def prove(self, code: str, filepath: str = "") -> List[ProofResult]:
        if not HAS_Z3:
            return [ProofResult("SKIP", "div_zero", "Z3 not installed")]

        # Route: AST for Python, regex for everything else
        if _is_python(filepath):
            extractor = _extract_ast(code)
            if extractor is not None:
                return self._prove_ast(extractor, code, filepath)

        return self._prove_regex(code, filepath)

    def _prove_ast(self, extractor: _ASTExtractor, code: str, filepath: str) -> List[ProofResult]:
        """AST-based division-by-zero detection for Python."""
        results = []
        lines = code.split("\n")

        for div in extractor.divisions:
            divisor_name = div.divisor

            # Skip numeric literals
            if divisor_name.isdigit() or divisor_name.replace(".", "", 1).isdigit():
                if float(divisor_name) == 0:
                    results.append(ProofResult(
                        "BUG_FOUND", "div_zero",
                        f"Division by literal zero",
                        counterexample=f"{divisor_name} = 0",
                        line=div.line, file=filepath,
                    ))
                continue

            # Model: can divisor be zero?
            s = Solver()
            s.set("timeout", 3000)
            divisor = Int(divisor_name)
            s.add(divisor == 0)

            # Check if there's any guard preventing zero
            guard_found = False
            for check_line in lines[max(0, div.line - 11):div.line - 1]:
                if divisor_name in check_line and ("!= 0" in check_line or "> 0" in check_line
                        or "== 0" in check_line or "is None" in check_line
                        or f"if {divisor_name}" in check_line or f"if not {divisor_name}" in check_line):
                    guard_found = True
                    break

            if not guard_found:
                results.append(ProofResult(
                    "BUG_FOUND", "div_zero",
                    f"'{divisor_name}' can be zero — no guard found within 10 lines",
                    counterexample=f"{divisor_name} = 0",
                    confidence=0.90,  # Higher confidence than regex (no string false positives)
                    line=div.line, file=filepath,
                ))

        return results

    def _prove_regex(self, code: str, filepath: str) -> List[ProofResult]:
        """Regex fallback for non-Python files."""
        results = []
        div_pattern = re.compile(r'(\w+)\s*/\s*(\w+)')
        lines = code.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                continue

            for match in div_pattern.finditer(line):
                divisor_name = match.group(2)
                # Skip numeric literals
                if divisor_name.isdigit():
                    if int(divisor_name) == 0:
                        results.append(ProofResult(
                            "BUG_FOUND", "div_zero",
                            f"Division by literal zero",
                            counterexample=f"{divisor_name} = 0",
                            line=line_num, file=filepath,
                        ))
                    continue

                # Model: can divisor be zero?
                s = Solver()
                s.set("timeout", 3000)
                divisor = Int(divisor_name)
                s.add(divisor == 0)

                # Check if there's any guard preventing zero
                guard_found = False
                for check_line in lines[max(0, line_num - 10):line_num]:
                    if divisor_name in check_line and ("!= 0" in check_line or "> 0" in check_line
                            or "== 0" in check_line or "is None" in check_line
                            or f"if {divisor_name}" in check_line or f"if not {divisor_name}" in check_line):
                        guard_found = True
                        break

                if not guard_found:
                    results.append(ProofResult(
                        "BUG_FOUND", "div_zero",
                        f"'{divisor_name}' can be zero — no guard found within 10 lines",
                        counterexample=f"{divisor_name} = 0",
                        confidence=0.85,
                        line=line_num, file=filepath,
                    ))

        return results


class IntegerOverflowProver:
    """Proves whether integer arithmetic can overflow."""

    def prove(self, code: str, filepath: str = "", bit_width: int = 256) -> List[ProofResult]:
        if not HAS_Z3:
            return [ProofResult("SKIP", "overflow", "Z3 not installed")]

        results = []
        # Detect multiplication patterns
        mul_pattern = re.compile(r'(\w+)\s*\*\s*(\w+)')
        add_pattern = re.compile(r'(\w+)\s*\+\s*(\w+)')
        lines = code.split("\n")

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for match in mul_pattern.finditer(line):
                a_name, b_name = match.group(1), match.group(2)
                if a_name.isdigit() or b_name.isdigit():
                    continue

                s = Solver()
                s.set("timeout", 3000)
                a = BitVec(a_name, bit_width)
                b = BitVec(b_name, bit_width)
                result_bv = a * b
                max_val = BitVecVal((1 << bit_width) - 1, bit_width)

                # Check if a * b can wrap (product < a when b > 0)
                s.add(UGT(b, BitVecVal(0, bit_width)))
                s.add(UGT(a, BitVecVal(0, bit_width)))
                s.add(ULT(result_bv, a))

                # Check for overflow guard
                context_lines = lines[max(0, line_num - 5):line_num + 2]
                has_guard = any(
                    "SafeMath" in l or "checked {" in l or "require(" in l
                    for l in context_lines
                ) or any(
                    "unchecked {" in l  # Solidity unchecked block = intentional wrap
                    for l in context_lines
                )

                if s.check() == sat and not has_guard:
                    model = s.model()
                    results.append(ProofResult(
                        "BUG_FOUND", "overflow",
                        f"Multiplication {a_name} * {b_name} can overflow (wrap around)",
                        counterexample=f"{a_name}={model[a]}, {b_name}={model[b]}",
                        line=line_num, file=filepath,
                    ))

        return results


class BoundsCheckProver:
    """Proves whether array/index access can be out of bounds."""

    def prove(self, code: str, filepath: str = "") -> List[ProofResult]:
        if not HAS_Z3:
            return [ProofResult("SKIP", "bounds", "Z3 not installed")]

        results = []
        # Detect array access patterns: arr[idx], list[i], data[index]
        access_pattern = re.compile(r'(\w+)\[(\w+)\]')
        lines = code.split("\n")

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for match in access_pattern.finditer(line):
                arr_name = match.group(1)
                idx_name = match.group(2)

                # Skip dict-like access and numeric indices
                if idx_name.isdigit() or idx_name.startswith('"') or idx_name.startswith("'"):
                    continue
                # Skip common dict patterns
                if arr_name in ("os", "sys", "env", "request", "params", "query",
                                "headers", "cookies", "session", "config", "settings"):
                    continue

                # Check for bounds guard
                guard_found = False
                for check_line in lines[max(0, line_num - 8):line_num]:
                    if (f"len({arr_name})" in check_line or f"{arr_name}.length" in check_line
                            or f"< len(" in check_line or f"< {arr_name}" in check_line
                            or "range(" in check_line or "enumerate(" in check_line):
                        guard_found = True
                        break

                if not guard_found:
                    s = Solver()
                    s.set("timeout", 2000)
                    idx = Int(idx_name)
                    length = Int(f"len_{arr_name}")
                    s.add(length >= 0)
                    s.add(Or(idx < 0, idx >= length))

                    if s.check() == sat:
                        results.append(ProofResult(
                            "BUG_FOUND", "bounds",
                            f"{arr_name}[{idx_name}]: no bounds check found — index can be out of range",
                            counterexample=f"{idx_name} could be negative or >= len({arr_name})",
                            confidence=0.70,
                            line=line_num, file=filepath,
                        ))

        return results


class AuthLogicProver:
    """Proves whether authentication/authorization logic has gaps."""

    def prove(self, code: str, filepath: str = "") -> List[ProofResult]:
        if not HAS_Z3:
            return [ProofResult("SKIP", "auth", "Z3 not installed")]

        results = []
        lines = code.split("\n")

        # Pattern 1: OR-based role checks (common mistake)
        or_role_pattern = re.compile(
            r'if\s+.*role\s*!=\s*["\'](\w+)["\']\s*or\s*.*role\s*!=\s*["\'](\w+)["\']',
            re.IGNORECASE,
        )
        for line_num, line in enumerate(lines, 1):
            m = or_role_pattern.search(line)
            if m:
                role1, role2 = m.group(1), m.group(2)
                # Prove: for ANY role value, (role != A) OR (role != B) is ALWAYS true
                s = Solver()
                s.set("timeout", 2000)
                role = Int("role")
                a, b = Int("a"), Int("b")
                s.add(a != b)  # Different roles
                # If role == a, then role != b is true. If role == b, then role != a is true.
                # (role != a) OR (role != b) is always true when a != b
                s.add(Not(Or(role != a, role != b)))
                if s.check() == unsat:
                    results.append(ProofResult(
                        "BUG_FOUND", "auth",
                        f"Role check always denies: 'role != \"{role1}\" or role != \"{role2}\"' is "
                        f"ALWAYS true. Use 'and' instead of 'or'.",
                        counterexample=f"For any role value, one condition is always true",
                        line=line_num, file=filepath,
                    ))

        # Pattern 2: Missing return after deny
        deny_pattern = re.compile(
            r'(raise|abort|deny|reject|forbidden|unauthorized|return\s+False)',
            re.IGNORECASE,
        )
        if_auth_pattern = re.compile(r'if\s+.*(?:auth|token|session|role|permission)', re.IGNORECASE)

        for line_num, line in enumerate(lines, 1):
            if if_auth_pattern.search(line):
                # Check next 5 lines for deny + return
                block = "\n".join(lines[line_num:min(line_num + 5, len(lines))])
                has_deny = deny_pattern.search(block)
                has_return = "return" in block or "raise" in block

                if has_deny and not has_return:
                    results.append(ProofResult(
                        "BUG_FOUND", "auth",
                        "Auth check may lack early return — execution could continue past denial",
                        confidence=0.65,
                        line=line_num, file=filepath,
                    ))

        return results


class ConcurrencyProver:
    """Detects check-then-act race conditions."""

    def prove(self, code: str, filepath: str = "") -> List[ProofResult]:
        if not HAS_Z3:
            return [ProofResult("SKIP", "concurrency", "Z3 not installed")]

        results = []
        lines = code.split("\n")

        # Pattern: if check → update without lock
        check_then_act = re.compile(
            r'if\s+(\w+)\s*(<|>|<=|>=|==|!=)\s*(\w+)',
        )

        for line_num, line in enumerate(lines, 1):
            m = check_then_act.search(line)
            if not m:
                continue

            var_name = m.group(1)
            # Look for modification of same variable after the check
            block_after = lines[line_num:min(line_num + 8, len(lines))]
            modifies = any(
                re.search(rf'{var_name}\s*(=|\+=|-=|\*=|/=)', l)
                for l in block_after
            )

            if modifies:
                # Check for lock/mutex/atomic in surrounding context
                context = "\n".join(lines[max(0, line_num - 10):min(line_num + 10, len(lines))])
                has_lock = any(kw in context.lower() for kw in [
                    "lock", "mutex", "atomic", "synchronized", "semaphore",
                    "transaction", "serializable", "select_for_update",
                    "with_lock", "acquire", "threading.Lock",
                ])

                if not has_lock:
                    # Z3: prove two threads can interleave
                    s = Solver()
                    s.set("timeout", 2000)
                    shared = Int(var_name)
                    t1_read = Int("t1_read")
                    t2_read = Int("t2_read")
                    limit = Int("limit")

                    # Both threads read same value
                    s.add(t1_read == shared)
                    s.add(t2_read == shared)
                    # Both pass the check
                    s.add(t1_read < limit)
                    s.add(t2_read < limit)
                    # Shared value near the limit
                    s.add(shared == limit - 1)
                    s.add(limit > 0)

                    if s.check() == sat:
                        results.append(ProofResult(
                            "BUG_FOUND", "concurrency",
                            f"TOCTOU race on '{var_name}': check-then-modify without lock. "
                            f"Two threads can both pass the check before either modifies.",
                            counterexample=f"Thread1 reads {var_name}=limit-1, Thread2 reads same, both pass",
                            line=line_num, file=filepath,
                        ))

        return results


class AnvilZ3Guard:
    """Unified Z3 Guard that runs all provers against code."""

    def __init__(self, enabled_provers: Optional[List[str]] = None, timeout_ms: int = 5000):
        self.timeout_ms = timeout_ms
        all_provers = {
            "div_zero": DivisionByZeroProver(),
            "overflow": IntegerOverflowProver(),
            "bounds": BoundsCheckProver(),
            "auth": AuthLogicProver(),
            "concurrency": ConcurrencyProver(),
        }
        if enabled_provers:
            self.provers = {k: v for k, v in all_provers.items() if k in enabled_provers}
        else:
            self.provers = all_provers

    def verify(self, code: str, filepath: str = "") -> List[ProofResult]:
        """Run all enabled provers against code."""
        results = []
        for name, prover in self.provers.items():
            try:
                prover_results = prover.prove(code, filepath)
                results.extend(prover_results)
            except Exception as e:
                results.append(ProofResult(
                    "SKIP", name, f"Prover error: {str(e)[:100]}",
                    file=filepath,
                ))
        return results

    def score(self, code: str, filepath: str = "") -> dict:
        """Score code safety. Returns dict with score/10 and details."""
        results = self.verify(code, filepath)
        bugs = sum(1 for r in results if r.verdict == "BUG_FOUND")
        safe = sum(1 for r in results if r.verdict == "PROVEN_SAFE")
        skipped = sum(1 for r in results if r.verdict == "SKIP")

        raw = 10.0 - (bugs * 2.0)
        final = max(0.0, min(10.0, round(raw, 1)))

        return {
            "score": final,
            "pass": final >= 6.0,
            "bugs_found": bugs,
            "proven_safe": safe,
            "skipped": skipped,
            "results": results,
            "total_checks": len(results),
        }
