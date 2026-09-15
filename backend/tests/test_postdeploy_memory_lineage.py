from datetime import date
from types import SimpleNamespace

from app.utils.hashing import stable_hash
from app.utils.input_lineage import BAR_FIELDS, history_digest


def test_streaming_digest_is_byte_equivalent_for_all_fields_and_missing_values():
    rows = [SimpleNamespace(trade_date=date(2024,1,1), open=1., high=1.2, low=.9, close=1.1,
        pre_close=None, volume=None, amount=0., pct_change=-0., adjust='none',source='真实源'),
        SimpleNamespace(trade_date=date(2024,1,2), close=2.)]
    expected=stable_hash([{key:getattr(row,key,None) for key in BAR_FIELDS} for row in rows])
    assert history_digest(iter(rows))==expected
    assert history_digest(iter([]))==stable_hash([])


def test_single_pass_history_digest_does_not_require_a_materialized_sequence():
    class OnePass:
        def __init__(self): self.called=False
        def __iter__(self):
            assert not self.called
            self.called=True
            for i in range(800): yield SimpleNamespace(close=float(i), source='fixture')
    assert len(history_digest(OnePass()))==64
