import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filters import load_schema, predicate_types


def test_schema_types():
    s = load_schema()
    assert s["title"]["title"] == "string"
    assert s["title"]["production_year"] == "numeric"


def test_joins_are_not_filters_and_aliases_resolve():
    sql = ("SELECT COUNT(*) FROM title AS t, movie_info AS mi "
           "WHERE t.id = mi.movie_id AND t.production_year > 2000 AND mi.info ILIKE '%drama%'")
    assert sorted(predicate_types(sql)) == ["numeric", "string"]


def test_versioned_tables_map_to_schema_table():
    sql = 'SELECT * FROM "title_1" WHERE "title_1"."kind_id" IN (1, 2) AND "title_1"."title" = \'x\''
    assert sorted(predicate_types(sql)) == ["numeric", "string"]
