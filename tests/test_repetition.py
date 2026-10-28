"""Planted cases for the repetition rates, and the SQL version against the Python loop."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from repetition import Event, all_rates, rate_generator, rate_plot, rates_sql, redset_query_hash

S = lambda key, tables: Event("select", key, tuple(tables))
W = lambda table, qtype="insert": Event(qtype, f"w-{table}", (), table)


def test_plain_repeat_counts():
    ev = [S("a", ["t"]), S("a", ["t"])]
    assert rate_generator(ev, dml_aware=False, scanset=False) == 0.5
    assert rate_generator(ev, dml_aware=True, scanset=False) == 0.5


def test_write_to_read_table_invalidates_only_dml_aware():
    ev = [S("a", ["t"]), W("t"), S("a", ["t"])]
    assert rate_generator(ev, dml_aware=False, scanset=False) == 0.5
    assert rate_generator(ev, dml_aware=True, scanset=False) == 0.0


def test_write_to_other_table_does_not_invalidate():
    ev = [S("a", ["t"]), W("u"), S("a", ["t"])]
    assert rate_generator(ev, dml_aware=True, scanset=False) == 0.5


def test_write_before_first_select_does_not_invalidate():
    ev = [W("t"), S("a", ["t"]), S("a", ["t"])]
    assert rate_generator(ev, dml_aware=True, scanset=False) == 0.5


def test_scanset_repeat_with_different_keys():
    ev = [S("a", ["t", "u"]), S("b", ["t", "u"])]
    assert rate_generator(ev, dml_aware=False, scanset=False) == 0.0
    assert rate_generator(ev, dml_aware=False, scanset=True) == 0.5


def test_plot_definition_stops_after_row_1001():
    ev = [W("x")] * 1002 + [S("a", ["t"]), S("a", ["t"])]
    assert rate_plot(ev, dml_aware=False, scanset=False, first_1k=True) == 0.0
    assert rate_plot(ev, dml_aware=False, scanset=False, first_1k=False) == 0.5


def test_redset_hash_matches_authors_format():
    assert redset_query_hash("ab", 1, 0, "45939") == "ab#1#0#(45939,)"
    assert redset_query_hash("ab", 2, 1, "5,3") == "ab#2#1#(3, 5)"
    assert redset_query_hash("ab", 0, 0, None) == "ab#0#0"


@pytest.mark.parametrize("seed", range(5))
def test_sql_matches_python_on_random_traces(seed):
    rng = random.Random(seed)
    tables = ["t1", "t2", "t3", "t4"]
    ev = []
    for _ in range(400):
        if rng.random() < 0.3:
            ev.append(W(rng.choice(tables), rng.choice(["insert", "update", "delete"])))
        else:
            ts = tuple(sorted(rng.sample(tables, rng.randint(1, 2))))
            ev.append(S(f"q{rng.randint(0, 15)}{ts}", ts))
    assert rates_sql(ev) == pytest.approx(all_rates(ev, "generator"))
