"""Expression evaluator handles JS-style operators and unsafe input."""
from backend.engine.expressions import eval_row, eval_scalar


def test_basic_comparison():
    row = {"score": 85, "stage": "qualified"}
    assert eval_row("row.score >= 80", row) is True
    assert eval_row("row['stage'] === 'qualified'", row) is True
    assert eval_row("row.score < 50", row) is False


def test_logical_operators():
    row = {"a": 1, "b": 2}
    assert eval_row("row.a < row.b && row.b > 0", row) is True
    assert eval_row("row.a > 100 || row.b > 0", row) is True


def test_safe_against_garbage():
    # Bad expression returns False, never raises.
    assert eval_row("this..is..not python", {"a": 1}) is False


def test_raw_mode_returns_value():
    assert eval_row("row.x * 2", {"x": 5}, raw=True) == 10


def test_scalar_eval():
    assert eval_scalar("1 + 1") == 2
    assert eval_scalar("nope_var") is False  # safe on undefined
  