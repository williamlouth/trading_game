from datetime import datetime, timedelta

import pytest
from flask import Flask

from models import (db, Users, MinuteUpdates, GameState, FarmerDiscards,
                    minuteUpdate, tick_game, addUser, addUsers, validate_role,
                    generateFarmer, generateConsumer, generate_schedule)


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


def test_generate_consumer_creates_sequential_updates(app):
    addUsers(0, 0, 1)
    consumer = Users.query.filter_by(username="C0").first()

    generateConsumer(consumer.id, [5, 15])
    db.session.commit()

    rows = (MinuteUpdates.query
            .filter_by(party=consumer.id)
            .order_by(MinuteUpdates.timeOffset)
            .all())
    assert [r.timeOffset for r in rows] == [0, 1]
    assert [r.apples for r in rows] == [5, 15]


def test_generate_schedule_targets_farmers_and_consumers(app):
    addUsers(2, 1, 2)
    generate_schedule()

    farmer = Users.query.filter_by(username="F0").first()
    consumer = Users.query.filter_by(username="C0").first()
    maker = Users.query.filter_by(username="A0").first()

    assert MinuteUpdates.query.filter_by(party=farmer.id).count() == 15
    assert MinuteUpdates.query.filter_by(party=consumer.id).count() == 15
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
