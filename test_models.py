from datetime import datetime, timedelta

import pytest
from flask import Flask

from models import (db, Users, Trades, MinuteUpdates, GameState, FarmerDiscards,
                    minuteUpdate, tick_game, addUser, addUsers, validate_role,
                    generateFarmer, generateConsumer, generate_schedule,
                    consumer_fulfillment, compute_results, compute_trade_highlights,
                    consumer_block_remaining, game_clock, dashboard_trades,
                    dashboard_users)


@pytest.fixture
def app():
    """Provide a fresh in-memory database inside an app context for each test."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def make_user(username, apples=0, monies=0):
    user = Users(username=username, apples=apples, monies=monies)
    db.session.add(user)
    db.session.commit()
    return user


def make_trade(partyA, partyB, apples, monies, timeOffset):
    trade = Trades(partyA=partyA, partyB=partyB, apples=apples,
                   monies=monies, timeOffset=timeOffset)
    db.session.add(trade)
    db.session.commit()
    return trade


# --- addUser / addUsers ---

def test_add_user_sets_balances(app):
    addUser("F0", 5, 100)
    db.session.commit()

    user = Users.query.filter_by(username="F0").first()
    assert user is not None
    assert user.apples == 5
    assert user.monies == 100


def test_add_users_counts_and_starting_money(app):
    assert addUsers(2, 3, 1) is True

    assert Users.query.count() == 6
    assert Users.query.filter_by(username="F0").first().monies == 0
    assert Users.query.filter_by(username="A0").first().monies == 20000
    assert Users.query.filter_by(username="C0").first().monies == 100000


def test_add_users_creates_only_fac_prefixes(app):
    addUsers(1, 1, 1)
    prefixes = sorted(u.username[0] for u in Users.query.all())
    assert prefixes == ["A", "C", "F"]


# --- validate_role ---

def test_farmer_cannot_buy_apples(app):
    user = make_user("F0", apples=10, monies=0)
    assert validate_role(user, 5, -50) == "User F0 can only sell apples."


def test_consumer_cannot_sell_apples(app):
    user = make_user("C0", apples=10, monies=1000)
    assert validate_role(user, -5, 50) == "User C0 can only buy apples."


def test_insufficient_apples(app):
    user = make_user("A0", apples=3, monies=1000)
    assert validate_role(user, -5, 50) == "User A0 has insufficient apples."


def test_insufficient_funds(app):
    user = make_user("C0", apples=0, monies=10)
    assert validate_role(user, 5, -50) == "User C0 has insufficient funds."


def test_valid_consumer_buy_returns_none(app):
    user = make_user("C0", apples=0, monies=1000)
    assert validate_role(user, 5, -50) is None


def test_valid_farmer_sell_returns_none(app):
    user = make_user("F0", apples=20, monies=0)
    assert validate_role(user, -5, 25) is None


# --- minuteUpdate ---

def test_minute_update_gives_farmer_apples(app):
    addUsers(1, 0, 0)
    farmer = Users.query.filter_by(username="F0").first()
    db.session.add(MinuteUpdates(party=farmer.id, timeOffset=0, apples=50))
    db.session.commit()

    minuteUpdate(0)
    db.session.commit()

    assert Users.query.filter_by(username="F0").first().apples == 50


def test_minute_update_caps_farmer_and_records_discard(app):
    addUsers(1, 0, 0)
    farmer = Users.query.filter_by(username="F0").first()
    farmer.apples = 120
    db.session.add(MinuteUpdates(party=farmer.id, timeOffset=1, apples=30))
    db.session.commit()

    minuteUpdate(1)
    db.session.commit()

    farmer = Users.query.filter_by(username="F0").first()
    # apples are capped to 100 before the new 30 are added
    assert farmer.apples == 130

    discard = FarmerDiscards.query.filter_by(party=farmer.id, timeOffset=0).first()
    assert discard is not None
    assert discard.apples == 20


def test_minute_update_does_not_apply_consumer_targets(app):
    addUsers(0, 0, 1)
    consumer = Users.query.filter_by(username="C0").first()
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=40))
    db.session.commit()

    minuteUpdate(0)
    db.session.commit()

    # consumer MinuteUpdates are targets only, never added to the balance
    assert Users.query.filter_by(username="C0").first().apples == 0


# --- schedule generation ---

def test_generate_farmer_creates_sequential_updates(app):
    addUsers(1, 0, 0)
    farmer = Users.query.filter_by(username="F0").first()

    generateFarmer(farmer.id, [10, 20, 30])
    db.session.commit()

    rows = (MinuteUpdates.query
            .filter_by(party=farmer.id)
            .order_by(MinuteUpdates.timeOffset)
            .all())
    assert [r.timeOffset for r in rows] == [0, 1, 2]
    assert [r.apples for r in rows] == [10, 20, 30]


def test_generate_consumer_aggregates_into_blocks(app):
    addUsers(0, 0, 1)
    consumer = Users.query.filter_by(username="C0").first()

    # 4 minutes of demand collapse into two 3-minute blocks (0-2, 3)
    generateConsumer(consumer.id, [5, 15, 10, 20])
    db.session.commit()

    rows = (MinuteUpdates.query
            .filter_by(party=consumer.id)
            .order_by(MinuteUpdates.timeOffset)
            .all())
    assert [r.timeOffset for r in rows] == [0, 3]
    assert [r.apples for r in rows] == [30, 20]


def test_generate_schedule_targets_farmers_and_consumers(app):
    addUsers(2, 1, 2)
    generate_schedule()

    farmer = Users.query.filter_by(username="F0").first()
    consumer = Users.query.filter_by(username="C0").first()
    maker = Users.query.filter_by(username="A0").first()

    # farmers still produce every minute (15 entries)
    assert MinuteUpdates.query.filter_by(party=farmer.id).count() == 15
    # 15 minutes of consumer demand collapse into five 3-minute blocks
    assert MinuteUpdates.query.filter_by(party=consumer.id).count() == 5
    assert [r.timeOffset for r in MinuteUpdates.query
            .filter_by(party=consumer.id)
            .order_by(MinuteUpdates.timeOffset).all()] == [0, 3, 6, 9, 12]
    # market makers have no schedule
    assert MinuteUpdates.query.filter_by(party=maker.id).count() == 0


# --- tick_game ---

def test_tick_game_no_state_is_noop(app):
    tick_game()
    assert GameState.query.first() is None


def test_tick_game_inactive_is_noop(app):
    addUsers(1, 0, 0)
    farmer = Users.query.filter_by(username="F0").first()
    db.session.add(MinuteUpdates(party=farmer.id, timeOffset=0, apples=10))
    db.session.add(GameState(is_active=False, start_time=datetime.now()))
    db.session.commit()

    tick_game()

    assert Users.query.filter_by(username="F0").first().apples == 0


def test_tick_game_active_processes_elapsed_minutes(app):
    addUsers(1, 0, 0)
    farmer = Users.query.filter_by(username="F0").first()
    for offset in range(3):
        db.session.add(MinuteUpdates(party=farmer.id, timeOffset=offset, apples=10))
    db.session.add(GameState(
        is_active=True,
        start_time=datetime.now() - timedelta(seconds=130),
        last_tick=None,
    ))
    db.session.commit()

    tick_game()

    # minutes 0, 1 and 2 each grant 10 apples
    assert Users.query.filter_by(username="F0").first().apples == 30
    assert GameState.query.first().last_tick is not None


# --- consumer_fulfillment ---

def test_consumer_fulfillment_counts_trades_across_block(app):
    addUsers(0, 1, 1)
    consumer = Users.query.filter_by(username="C0").first()
    maker = Users.query.filter_by(username="A0").first()
    # one block target of 100 apples starting at minute 0 (covers minutes 0-2)
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=100))
    db.session.commit()

    # consumer buys 40 at minute 1 and 30 at minute 2, both inside the block
    make_trade(consumer.id, maker.id, apples=40, monies=-400, timeOffset=1)
    make_trade(consumer.id, maker.id, apples=30, monies=-300, timeOffset=2)

    earned, possible, pct = consumer_fulfillment(consumer)
    assert earned == 70
    assert possible == 100
    assert pct == 70.0


def test_consumer_fulfillment_excludes_trades_outside_block(app):
    addUsers(0, 1, 1)
    consumer = Users.query.filter_by(username="C0").first()
    maker = Users.query.filter_by(username="A0").first()
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=100))
    db.session.commit()

    # a trade at minute 3 is in the next block and must not count
    make_trade(consumer.id, maker.id, apples=50, monies=-500, timeOffset=3)

    earned, possible, pct = consumer_fulfillment(consumer)
    assert earned == 0
    assert possible == 100
    assert pct == 0.0


def test_consumer_fulfillment_caps_at_target(app):
    addUsers(0, 1, 1)
    consumer = Users.query.filter_by(username="C0").first()
    maker = Users.query.filter_by(username="A0").first()
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=50))
    db.session.commit()

    # buying more than the target cannot earn more than the target
    make_trade(consumer.id, maker.id, apples=80, monies=-800, timeOffset=0)

    earned, possible, pct = consumer_fulfillment(consumer)
    assert earned == 50
    assert possible == 50
    assert pct == 100.0


# --- compute_results ---

def test_compute_results_groups_and_ranks(app):
    addUsers(0, 2, 0)
    a0 = Users.query.filter_by(username="A0").first()
    a1 = Users.query.filter_by(username="A1").first()
    a0.monies = 100
    a1.monies = 500
    db.session.commit()

    results = compute_results()
    assert set(results.keys()) == {"Farmers (F)", "AppleMakers (A)", "Consumers (C)"}
    # makers ranked by money descending
    assert [p["username"] for p in results["AppleMakers (A)"]] == ["A1", "A0"]


def test_compute_results_ranks_consumers_by_fulfillment(app):
    addUsers(0, 1, 2)
    maker = Users.query.filter_by(username="A0").first()
    c0 = Users.query.filter_by(username="C0").first()
    c1 = Users.query.filter_by(username="C1").first()
    # both target 100 in block 0; C1 fully fills it, C0 does not
    db.session.add(MinuteUpdates(party=c0.id, timeOffset=0, apples=100))
    db.session.add(MinuteUpdates(party=c1.id, timeOffset=0, apples=100))
    db.session.commit()
    make_trade(c0.id, maker.id, apples=40, monies=-400, timeOffset=0)
    make_trade(c1.id, maker.id, apples=100, monies=-1000, timeOffset=0)

    consumers = compute_results()["Consumers (C)"]
    assert [p["username"] for p in consumers] == ["C1", "C0"]
    assert consumers[0]["fulfillment"] == 100.0
    assert consumers[1]["fulfillment"] == 40.0


# --- compute_trade_highlights ---

def test_compute_trade_highlights_picks_records(app):
    addUsers(1, 1, 1)
    f0 = Users.query.filter_by(username="F0").first()
    a0 = Users.query.filter_by(username="A0").first()
    c0 = Users.query.filter_by(username="C0").first()

    # farmer sells 30 @ 4 and 50 @ 6 (sells -> negative apples)
    cheap_sell = make_trade(f0.id, a0.id, apples=-30, monies=120, timeOffset=0)
    rich_sell = make_trade(f0.id, a0.id, apples=-50, monies=300, timeOffset=1)
    # consumer buys 20 @ 8 and 10 @ 5 (buys -> positive apples)
    pricey_buy = make_trade(c0.id, a0.id, apples=20, monies=-160, timeOffset=0)
    cheap_buy = make_trade(c0.id, a0.id, apples=10, monies=-50, timeOffset=1)

    h = compute_trade_highlights()
    assert h["apple_big"].id == rich_sell.id          # largest volume (50)
    assert h["apple_best_sell"].id == rich_sell.id    # highest sell price (6)
    assert h["apple_worst_sell"].id == cheap_sell.id  # lowest sell price (4)
    assert h["apple_best_buy"].id == cheap_buy.id     # lowest buy price (5)
    assert h["apple_worst_buy"].id == pricey_buy.id   # highest buy price (8)


def test_compute_trade_highlights_empty(app):
    h = compute_trade_highlights()
    assert all(v is None for v in h.values())


# --- consumer_block_remaining ---

def test_consumer_block_remaining_starts_at_negative_target(app):
    addUsers(0, 0, 1)
    consumer = Users.query.filter_by(username="C0").first()
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=100))
    db.session.commit()

    # no trades yet -> full outstanding demand shown as negative
    assert consumer_block_remaining(consumer, current_minute=1) == -100


def test_consumer_block_remaining_moves_toward_zero(app):
    addUsers(0, 1, 1)
    consumer = Users.query.filter_by(username="C0").first()
    maker = Users.query.filter_by(username="A0").first()
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=100))
    db.session.commit()
    make_trade(consumer.id, maker.id, apples=30, monies=-300, timeOffset=1)

    assert consumer_block_remaining(consumer, current_minute=2) == -70


def test_consumer_block_remaining_zero_when_met(app):
    addUsers(0, 1, 1)
    consumer = Users.query.filter_by(username="C0").first()
    maker = Users.query.filter_by(username="A0").first()
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=50))
    db.session.commit()
    make_trade(consumer.id, maker.id, apples=80, monies=-800, timeOffset=0)

    # buying past the target clamps to 0, not positive
    assert consumer_block_remaining(consumer, current_minute=0) == 0


def test_consumer_block_remaining_uses_current_block_only(app):
    addUsers(0, 1, 1)
    consumer = Users.query.filter_by(username="C0").first()
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=40))
    db.session.commit()

    # at minute 3 we are in the next block, which has no target row
    assert consumer_block_remaining(consumer, current_minute=3) == 0


# --- game_clock ---

def test_game_clock_no_state(app):
    assert game_clock() == (False, 0, 0)


def test_game_clock_active_reports_elapsed(app):
    db.session.add(GameState(
        is_active=True,
        start_time=datetime.now() - timedelta(seconds=125),
    ))
    db.session.commit()

    is_active, elapsed, minute = game_clock()
    assert is_active is True
    assert elapsed >= 125
    assert minute == elapsed // 60


# --- dashboard_trades ---

def test_dashboard_trades_newest_first_with_direction(app):
    addUsers(1, 1, 1)
    f0 = Users.query.filter_by(username="F0").first()
    a0 = Users.query.filter_by(username="A0").first()
    c0 = Users.query.filter_by(username="C0").first()
    make_trade(f0.id, a0.id, apples=-30, monies=150, timeOffset=0)   # sell @ 5
    make_trade(c0.id, a0.id, apples=20, monies=-160, timeOffset=0)   # buy  @ 8

    trades = dashboard_trades()
    assert len(trades) == 2
    # newest first: the buy
    assert trades[0] == {'is_sell': False, 'price': 8.0, 'size': 20}
    assert trades[1] == {'is_sell': True, 'price': 5.0, 'size': 30}


# --- dashboard_users ---

def test_dashboard_users_consumer_shows_negative_target(app):
    addUsers(1, 1, 1)
    farmer = Users.query.filter_by(username="F0").first()
    farmer.apples = 40
    consumer = Users.query.filter_by(username="C0").first()
    db.session.add(MinuteUpdates(party=consumer.id, timeOffset=0, apples=60))
    db.session.commit()

    rows = {u['username']: u for u in dashboard_users(current_minute=0)}
    # farmer shows real inventory, consumer shows negative outstanding target
    assert rows['F0']['apples'] == 40
    assert rows['F0']['role'] == 'farmer'
    assert rows['A0']['role'] == 'maker'
    assert rows['C0']['apples'] == -60
    assert rows['C0']['role'] == 'consumer'
