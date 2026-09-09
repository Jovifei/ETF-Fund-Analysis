"""Factor diagnostic matrices rank each complete pair, not mismatched universes."""
import numpy as np
import pandas as pd
from app.workspace.factor_diagnostics import correlation_summary


def test_pairwise_missing_values_are_ranked_after_pair_selection():
    frame = pd.DataFrame({'trade_date':['2026-09-01'] * 6, 'a':[1,2,3,4,100,200], 'b':[4,1,3,2,np.nan,np.nan], 'c':[1,np.nan,np.nan,2,np.nan,np.nan]})
    matrix, counts = correlation_summary(frame, ['a','b','c'])
    pair = frame[['a','b']].dropna()
    expected = pair.a.corr(pair.b, method='spearman')
    assert abs(matrix[0][1] - expected) < 1e-12
    assert counts[0][1] == 1
    assert matrix[0][2] is None and counts[0][2] == 0


def test_correlation_is_date_local_and_constant_columns_are_unknown():
    frame = pd.DataFrame({'trade_date':['2026-09-01'] * 4 + ['2026-09-02'] * 4, 'a':[1,2,3,4,40,30,20,10], 'b':[4,3,2,1,10,20,30,40], 'c':[2]*8})
    matrix, counts = correlation_summary(frame, ['a','b','c'])
    assert matrix[0][1] == -1.0 and counts[0][1] == 2
    assert matrix[2][2] is None and counts[2][2] == 0
