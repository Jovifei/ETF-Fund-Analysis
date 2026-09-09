from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import session_scope
from app.models import Holding, Instrument
from app.services.holding_service import HoldingService
from app.workspace import imports
from app.workspace.jobs import WorkspaceError
from app.workspace.protocol import content_hash


def test_import_requires_unambiguous_unit_cost_header():
    with pytest.raises(WorkspaceError, match='cost_price'):
        imports.parse_file('代码,份额,成本\n510300,100,3.2\n'.encode(), '.csv')
    rows = imports.parse_file('基金代码,持有份额,每份成本\n510300,100,3.200\n'.encode(), '.csv')
    assert rows[0]['ts_code'] == '510300'
    assert rows[0]['cost_price'] == '3.200'


@pytest.mark.parametrize('value', ['=1+2', '-10', 'nan', 'inf', '1e3', '50%', '1,000'])
def test_import_rejects_ambiguous_or_executable_numbers(value):
    with pytest.raises(ValueError):
        imports.decimal_value(value)


def test_import_preview_confirmation_and_undo(bootstrapped):
    with session_scope() as db:
        inst = db.scalar(select(Instrument).where(Instrument.kind == 'ETF').order_by(Instrument.id).limit(1))
        old = imports.holding_state(db, None, [inst.ts_code])[inst.ts_code]
        candidates = [{'row_index': 1, 'ts_code': inst.ts_code, 'shares': '123', 'cost_price': '3.123', 'selected': True}]
        row = imports.preview_rows(db, candidates, content_hash({'unique': uuid4().hex}), 'manual', None)
        assert imports.holding_state(db, None, [inst.ts_code])[inst.ts_code] == old
        assert not row.candidates_json[0]['errors']
        digest = content_hash(row.candidates_json)
        imports.confirm(db, row, digest)
        assert row.status == 'confirmed'
        assert imports.holding_state(db, None, [inst.ts_code])[inst.ts_code]['shares'] == '123'
        imports.confirm(db, row, digest)
        imports.undo(db, row)
        assert row.status == 'undone'
        assert imports.holding_state(db, None, [inst.ts_code])[inst.ts_code] == old


def test_undo_does_not_overwrite_later_manual_changes(bootstrapped):
    with session_scope() as db:
        inst = db.scalar(select(Instrument).where(Instrument.kind == 'ETF').order_by(Instrument.id).limit(1))
        before = imports.holding_state(db, None, [inst.ts_code])[inst.ts_code]
        row = imports.preview_rows(db, [{'row_index': 1, 'ts_code': inst.ts_code, 'shares': '100', 'cost_price': '3.2', 'selected': True}], content_hash({'unique': uuid4().hex}), 'manual', None)
        imports.confirm(db, row, content_hash(row.candidates_json))
        HoldingService().upsert(db, user_id=None, ts_code=inst.ts_code, shares=200, cost_price=3.5)
        with pytest.raises(WorkspaceError, match='cannot_undo'):
            imports.undo(db, row)
        # This test does not change another test's existing holdings.
        if before:
            HoldingService().upsert(db, user_id=None, ts_code=inst.ts_code, shares=Decimal(before['shares']), cost_price=Decimal(before['cost_price']), target_weight=before['target_weight'], notes=before['notes'])
        else:
            HoldingService().delete(db, inst.ts_code, user_id=None)
