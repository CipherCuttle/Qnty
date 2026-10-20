"""Synthetic only. The original Qnty evaluator is NOT imported or executed."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from math import isclose, log
import pytest

from quantbot.experiment.causal_v2_evaluation import Bar, Config, evaluate
from quantbot.data.types import Bar as OriginalBar
from quantbot.strategy.tsmom_strategy import TSMOMStrategy
from quantbot.experiment.volnorm_portfolio import VolatilityTracker, compute_vol_normed_weights


def bars(closes: dict[str,list[float]], opens: dict[str,list[float]]|None=None):
    opens=opens or {s: [values[0]] + values[:-1] for s, values in closes.items()}
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    return {s:[Bar((t+timedelta(hours=i*8)).isoformat(),float(opens[s][i]),float(c)) for i,c in enumerate(vals)] for s,vals in closes.items()}


def rates(b, rate=0.0):
    return {(s,bar.timestamp):rate for s,arr in b.items() for bar in arr}


def test_a_jump_only_visible_at_close_does_not_generate_phantom_gain():
    # Original source pattern credits log(200/100) to bar t on signal computed at close t.
    prices=[100.0]*20 + [200.0]*4
    b=bars({'BTCUSDT':prices},{'BTCUSDT':[100.0]*21+[200.0]*3})
    result=evaluate(b,rates(b),config=Config(fee_bps_per_side=0,slippage_bps_per_side=0))
    assert sum(1 for f in result.fills if f.side=='BUY')==1
    assert result.fills[0].fill_timestamp == b['BTCUSDT'][21].timestamp
    assert result.fills[0].decision_timestamp == b['BTCUSDT'][20].timestamp
    assert all(isclose(s.equity,10000) for s in result.snapshots)
    assert isclose(log(200/100),0.6931471805599453) # historical same-bar credited log-return


def test_future_suffix_changes_do_not_change_prefix_decisions_or_equity():
    length=110
    common_btc=[100*(1+0.001*i + 0.005*((-1)**i)) for i in range(length)]
    common_eth=[100*(1+0.002*i + 0.008*((-1)**(i//2))) for i in range(length)]
    first=bars({'BTCUSDT':common_btc,'ETHUSDT':common_eth})
    wild=bars({'BTCUSDT':common_btc+[200,70,150,50],'ETHUSDT':common_eth+[x*1.01 for x in common_eth[-4:]]})
    cfg=Config(fee_bps_per_side=0,slippage_bps_per_side=0)
    a=evaluate(first,rates(first),config=cfg)
    z=evaluate(wild,rates(wild),config=cfg)
    assert a.snapshots==z.snapshots[:length]
    assert a.decisions==z.decisions[:len(a.decisions)]
    assert any(len(d.target_weights)==2 for d in a.decisions)


def test_five_identical_assets_get_one_x_not_five_x_benchmark():
    closes={s:[100]*21+[120] for s in ['A','B','C','D','E']}
    b=bars(closes, {s:[100]*22 for s in closes})
    zero=Config(fee_bps_per_side=0,slippage_bps_per_side=0)
    r=evaluate(b,rates(b),config=zero,mode='equal_weight_buy_hold')
    assert len([f for f in r.fills if f.side=='BUY'])==5
    assert isclose(r.summary()['simple_return'],.20,abs_tol=1e-12)
    assert isclose(sum([log(1.2)]*5),5*log(1.2))  # historical improper 5x log benchmark


def test_one_snapshot_per_bar_in_strict_temporal_order():
    closes=[100]*21+[120,85,120,85,120]
    b=bars({'BTCUSDT':closes})
    r=evaluate(b,rates(b),config=Config(fee_bps_per_side=0,slippage_bps_per_side=0),mode='equal_weight_buy_hold')
    assert len(r.snapshots)==len(closes)
    assert [s.timestamp for s in r.snapshots]==[x.timestamp for x in b['BTCUSDT']]
    assert r.summary()['max_drawdown']>0.25


def test_fees_and_slippage_reduce_equity_even_when_price_flat():
    closes=[100]*20+[101]+[101]*3
    b=bars({'BTCUSDT':closes})
    r=evaluate(b,rates(b),config=Config(fee_bps_per_side=5,slippage_bps_per_side=5))
    z=evaluate(b,rates(b),config=Config(fee_bps_per_side=0,slippage_bps_per_side=0))
    assert r.summary()['final_equity'] < z.summary()['final_equity']
    assert r.summary()['total_fees']>0
    assert r.fills[0].executed_price>101  # adverse buy-side slippage
    assert all(s.gross_exposure<=1.00001 for s in r.snapshots)


def test_funding_missing_fails_closed_and_signed_rates_have_opposite_effect():
    closes=[100]*20+[101]+[101]*3
    b=bars({'BTCUSDT':closes})
    z=rates(b,0.0)
    zero=Config(fee_bps_per_side=0,slippage_bps_per_side=0,cash_reserve_fraction=0.01)
    missing=z.copy(); del missing[('BTCUSDT',b['BTCUSDT'][21].timestamp)]
    with pytest.raises(ValueError,match='Missing funding coverage'):
        evaluate(b,missing,config=zero)
    charge=z.copy(); charge[('BTCUSDT',b['BTCUSDT'][21].timestamp)]=0.005
    credit=z.copy(); credit[('BTCUSDT',b['BTCUSDT'][21].timestamp)]=-0.005
    a=evaluate(b,charge,config=zero)
    c=evaluate(b,credit,config=zero)
    assert a.snapshots[21].funding_cashflow<0
    assert c.snapshots[21].funding_cashflow>0
    assert a.snapshots[-1].equity<c.snapshots[-1].equity


def test_duplicate_bar_or_gap_is_rejected():
    b=bars({'BTCUSDT':[100]*23})
    b['BTCUSDT'][21]=Bar(b['BTCUSDT'][20].timestamp,100,100)
    with pytest.raises(ValueError,match='Duplicate'):
        evaluate(b,rates(b))
    b=bars({'BTCUSDT':[100]*23})
    b['BTCUSDT'][22]=Bar('2026-01-10T00:00:00+00:00',100,100)
    with pytest.raises(ValueError,match='contiguous'):
        evaluate(b,rates(b))


def test_repeat_is_bitwise_deterministic():
    closes=[100*(1+.003*i) for i in range(25)]
    b=bars({'BTCUSDT':closes})
    a=evaluate(b,rates(b))
    z=evaluate(b,rates(b))
    assert a==z


def test_all_cash_baseline_stays_flat_and_has_no_fees():
    b=bars({'BTCUSDT':[100]*20+[140,70,200]})
    r=evaluate(b,{},mode='cash')
    assert not r.fills
    assert not r.decisions
    assert r.summary()['simple_return']==0


def test_extra_half_spread_penalty_is_explicit_and_not_double_counted_by_default():
    closes=[100]*20+[101]+[101]*3
    b=bars({'BTCUSDT':closes})
    base=evaluate(b,rates(b),config=Config(fee_bps_per_side=0,slippage_bps_per_side=5,spread_bps_per_side=0))
    wider=evaluate(b,rates(b),config=Config(fee_bps_per_side=0,slippage_bps_per_side=5,spread_bps_per_side=2))
    assert wider.fills[0].executed_price>base.fills[0].executed_price
    assert wider.snapshots[-1].equity<base.snapshots[-1].equity


def test_nonfinite_funding_fails_closed():
    closes=[100]*20+[101]+[101]*3
    b=bars({'BTCUSDT':closes})
    values=rates(b)
    values[('BTCUSDT',b['BTCUSDT'][21].timestamp)]=float('nan')
    with pytest.raises(ValueError,match='Nonfinite funding'):
        evaluate(b,values)


def test_integrated_uses_original_tsmom_on_jump():
    prices=[100.0]*20+[200.0]*4
    b=bars({'BTCUSDT':prices})
    signal=TSMOMStrategy(return_period=20, threshold=0.0, symbol='BTCUSDT')
    observed=[]
    for i,bar in enumerate(b['BTCUSDT']):
        src=OriginalBar(bar.timestamp,bar.open,max(bar.open,bar.close),min(bar.open,bar.close),bar.close,1.0)
        if signal.on_bar(src) is not None:
            observed.append(i)
    assert observed==[20,21,22,23]


def test_integrated_original_vol_tracker_weighting():
    tr={s:VolatilityTracker() for s in ('BTCUSDT','ETHUSDT')}
    for i in range(90):
        tr['BTCUSDT'].update(.001*(-1)**i)
        tr['ETHUSDT'].update(.004*(-1)**i)
    weights=compute_vol_normed_weights(['BTCUSDT','ETHUSDT'],tr)
    assert abs(sum(weights.values())-1)<1e-12
    assert weights['BTCUSDT']>weights['ETHUSDT']


def test_integrated_future_suffix_no_retroactive_changes():
    prices=[100*(1+.002*i + .003*((-1)**i)) for i in range(110)]
    alt=[100*(1+.001*i + .005*((-1)**(i//2))) for i in range(110)]
    prefix=bars({'BTCUSDT':prices,'ETHUSDT':alt})
    extended=bars({'BTCUSDT':prices+[125,70,160],'ETHUSDT':alt+[210,80,120]})
    cfg=Config(fee_bps_per_side=0,slippage_bps_per_side=0)
    r=evaluate(prefix,rates(prefix),config=cfg)
    r2=evaluate(extended,rates(extended),config=cfg)
    assert r.snapshots==r2.snapshots[:len(prices)]
    assert r.decisions==r2.decisions[:len(r.decisions)]
