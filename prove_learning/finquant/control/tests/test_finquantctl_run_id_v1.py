"""M1 run_id format contract."""
import re

from finquant.control.finquantctl import new_run_id


_RE_RUN_ID = re.compile(
    r"^(?P<day>\d{8})_(?P<hms>\d{6})_(?P<mode>smoke|full)_(?P<h>[0-9a-f]{7})$"
)


def test_new_run_id_smoke_matches_directive() -> None:
    rid = new_run_id("smoke")
    m = _RE_RUN_ID.match(rid)
    assert m is not None, rid
    assert m.group("mode") == "smoke"


def test_new_run_id_full_matches_directive() -> None:
    rid = new_run_id("full")
    m = _RE_RUN_ID.match(rid)
    assert m is not None, rid
    assert m.group("mode") == "full"
