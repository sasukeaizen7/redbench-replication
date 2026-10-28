"""The simulated result cache must hit exactly the selects counted by QRR_DML."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from execute import cache_hits
from repetition import events_from_workload, rate_generator


def _workload(seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for _ in range(300):
        if rng.random() < 0.3:
            t = rng.choice(["a", "b", "c"])
            rows.append({"query_type": "insert", "sql": f"INSERT INTO {t} ...", "read_tables": None, "write_table": t})
        else:
            ts = ",".join(sorted(rng.sample(["a", "b", "c"], rng.randint(1, 2))))
            rows.append({"query_type": "select", "sql": f"SELECT {rng.randint(0, 9)} FROM {ts}",
                         "read_tables": ts, "write_table": None})
    return pd.DataFrame(rows)


def test_hits_equal_dml_aware_qrr():
    for seed in range(5):
        w = _workload(seed)
        hits = pd.Series(cache_hits(w))
        qrr_dml = rate_generator(events_from_workload(w), dml_aware=True, scanset=False)
        assert hits[w.query_type == "select"].mean() == qrr_dml


def test_write_between_repeats_is_a_miss():
    w = pd.DataFrame([
        {"query_type": "select", "sql": "S", "read_tables": "a", "write_table": None},
        {"query_type": "insert", "sql": "I", "read_tables": None, "write_table": "a"},
        {"query_type": "select", "sql": "S", "read_tables": "a", "write_table": None},
        {"query_type": "select", "sql": "S", "read_tables": "a", "write_table": None},
    ])
    assert cache_hits(w) == [False, False, False, True]
