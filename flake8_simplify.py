# Core Library
import ast
import sys
from collections import defaultdict
from typing import Any, DefaultDict, Generator, List, Tuple, Type

# Third party
import astor

if sys.version_info < (3, 8):  # pragma: no cover (<PY38)
    # Third party
    import importlib_metadata
else:  # pragma: no cover (PY38+)
    # Core Library
    import importlib.metadata as importlib_metadata

SIM101 = (
    "SIM101 Multiple isinstance-calls which can be merged into a single "
    "call for variable '{var}'"
)
SIM201 = "SIM201 Used 'not {left} == {right}' instead of '{left} != {right}'"


def _get_duplicated_isinstance_call_by_node(node: ast.BoolOp) -> List[str]:
    """
    Get a list of isinstance arguments which could be shortened.

    Examples
    --------
    >> g = _get_duplicated_isinstance_call_by_node
    >> g("isinstance(a, int) or isinstance(a, float) or isinstance(b, int)
    ['a']
    >> g("isinstance(a, int) or isinstance(b, float) or isinstance(b, int)
    ['b']
    """
    counter: DefaultDict[str, int] = defaultdict(int)

    for call in node.values:
        # Make sure that this function call is actually a call of the built-in
        # "isinstance"
        if not isinstance(call, ast.Call) or len(call.args) != 2:
            continue
        function_name = astor.to_source(call.func).strip()
        if function_name != "isinstance":
            continue

        # Collect the name of the argument
        isinstance_arg0_name = astor.to_source(call.args[0]).strip()
        counter[isinstance_arg0_name] += 1
    return [arg0_name for arg0_name, count in counter.items() if count > 1]


def _get_duplicated_isinstance_calls(
    node: ast.BoolOp,
) -> List[Tuple[int, int, str]]:
    """Get a positions where the duplicate isinstance problem appears."""
    errors: List[Tuple[int, int, str]] = []
    if not isinstance(node.op, ast.Or):
        return errors

    for var in _get_duplicated_isinstance_call_by_node(node):
        errors.append((node.lineno, node.col_offset, SIM101.format(var=var)))
    return errors


def _get_not_equal_calls(node: ast.UnaryOp) -> List[Tuple[int, int, str]]:
    """Get a list of all calls where an unary 'not' is used for an quality."""
    errors: List[Tuple[int, int, str]] = []
    if (
        not isinstance(node.op, ast.Not)
        or not isinstance(node.operand, ast.Compare)
        or len(node.operand.ops) != 1
        or not isinstance(node.operand.ops[0], ast.Eq)
    ):
        return errors
    comparison = node.operand
    left = astor.to_source(comparison.left).strip()
    right = astor.to_source(comparison.comparators[0]).strip()
    errors.append(
        (node.lineno, node.col_offset, SIM201.format(left=left, right=right))
    )

    return errors


class Visitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: List[Tuple[int, int, str]] = []

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.errors += _get_duplicated_isinstance_calls(node)
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        self.errors += _get_not_equal_calls(node)
        self.generic_visit(node)


class Plugin:
    name = __name__
    version = importlib_metadata.version(__name__)

    def __init__(self, tree: ast.AST):
        self._tree = tree

    def run(self) -> Generator[Tuple[int, int, str, Type[Any]], None, None]:
        visitor = Visitor()
        visitor.visit(self._tree)

        for line, col, msg in visitor.errors:
            yield line, col, msg, type(self)
