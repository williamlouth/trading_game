from datetime import datetime

from flask import (Blueprint, request, render_template_string, redirect,
                   flash, get_flashed_messages, jsonify, abort)

from models import (db, Users, Trades, MinuteUpdates, GameState, FarmerDiscards,
                    minuteUpdate, tick_game, addUsers, generate_schedule,
                    validate_role, compute_results, compute_trade_highlights,
                    game_clock, dashboard_trades, dashboard_users, execute_trade)

bp = Blueprint('main', __name__)


@bp.before_request
def pulse():
    # Only pulse on specific routes to save database overhead
    if request.endpoint in ['main.dashboard', 'main.consumer_targets',
                            'main.api_dashboard']:
        tick_game()


@bp.route('/')
def hello_world():
    index_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Trading Game Terminal</title>
        <style>
            body { 
                font-family: 'Courier New', Courier, monospace; 
                background: #0a0a0a; 
                color: #ffffff; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                height: 100vh; 
                margin: 0; 
                overflow: hidden;
            }
            .welcome-container { 
                text-align: center; 
                padding: 60px; 
                border: 1px solid #333; 
                background: linear-gradient(145deg, #111, #050505); 
                box-shadow: 0 0 50px rgba(0, 0, 0, 0.5);
                max-width: 700px;
                border-radius: 4px;
            }
            .logo {
                font-size: 3.5rem;
                font-weight: bold;
                letter-spacing: 10px;
                margin-bottom: 20px;
                background: linear-gradient(to right, #00ff88, #007bff);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .divider {
                height: 2px;
                width: 100px;
                background: #00ff88;
                margin: 20px auto;
            }
            h2 { 
                font-size: 1.2rem; 
                color: #888; 
                text-transform: uppercase; 
                letter-spacing: 5px;
                margin-top: 0;
            }
            p { 
                color: #666; 
                font-size: 1rem; 
                line-height: 1.6;
                margin-top: 20px;
            }
            .status-line {
                margin-top: 40px;
                font-size: 0.7rem;
                color: #222;
                text-transform: uppercase;
            }
        </style>
    </head>
    <body>
        <div class="welcome-container">
            <div class="logo">THE TRADING GAME</div>
            <div class="divider"></div>
            <p>
                Welcome to the Apple exchange. <br>
                Monitor the tape, fill your targets, and manage your capital.
            </p>
        </div>
    </body>
    </html>
    '''
    return render_template_string(index_html)


@bp.route('/api/dashboard')
def api_dashboard():
    is_active, elapsed_seconds, current_minute = game_clock()
    block_start = (current_minute // 3) * 3
    return jsonify({
        'is_active': is_active,
        'elapsed_seconds': elapsed_seconds,
        'current_minute': current_minute,
        'block_start': block_start,
        'block_end': block_start + 2,
        'trades': dashboard_trades(),
        'users': dashboard_users(current_minute),
    })


@bp.route('/dashboard')
def dashboard():
    dashboard_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Market Dashboard</title>
        <style>
            body { font-family: 'Courier New', Courier, monospace; background: #121212; color: #e0e0e0; margin: 0; padding: 20px; }
            h1 { text-align: center; color: #ffffff; margin-bottom: 6px; }
            h2 { text-align: center; color: #ffffff; margin-bottom: 10px; }

            .clock-box { max-width: 420px; margin: 0 auto 24px; background: #1e1e1e; border: 1px solid #007bff; border-radius: 8px; padding: 14px; text-align: center; }
            .clock { font-size: 2.4rem; font-weight: bold; color: #007bff; letter-spacing: 2px; }
            .clock-sub { font-size: 0.8rem; color: #888; margin-top: 4px; }
            .status-tag { font-size: 0.8rem; padding: 4px 10px; border-radius: 4px; background: #222; margin-top: 8px; display: inline-block; }

            .container { display: flex; gap: 40px; padding: 0 20px; justify-content: center; align-items: flex-start; flex-wrap: wrap; }
            .column { flex: 1; min-width: 320px; max-width: 520px; }
            table { width: 100%; border-collapse: collapse; background: #1e1e1e; table-layout: fixed; }
            th, td { padding: 10px 8px; text-align: right; border-bottom: 1px solid #333; }
            th { color: #888; font-size: 0.75rem; text-transform: uppercase; }

            .col-arrow { width: 50px; text-align: center; }
            .buy { color: #00ff88; }
            .sell { color: #ff4d4d; }
            .arrow { font-size: 1.6rem; font-weight: bold; display: block; text-align: center; }
            .price-cell, .size-cell { font-weight: bold; font-size: 1.1rem; }

            td.user { text-align: left; color: #fff; font-weight: bold; }
            .role { color: #666; font-size: 0.7rem; text-transform: uppercase; }
            .money { color: #00ff88; }
            .apples-pos { color: #e0e0e0; }
            .apples-neg { color: #ffa500; }
            .apples-zero { color: #00ff88; }
            .empty { text-align: center; color: #666; font-style: italic; padding: 20px; }
        </style>
    </head>
    <body>
        <h1>Market Dashboard</h1>

        <div class="clock-box">
            <div class="clock-sub">GAME CLOCK</div>
            <div class="clock" id="clock">00:00</div>
            <div class="clock-sub" id="block-info">Minute 0 · Block T+0m–T+2m</div>
            <div class="status-tag" id="status">● —</div>
        </div>

        <div class="container">
            <div class="column">
                <h2>🍎 Market Tape</h2>
                <table>
                    <thead>
                        <tr>
                            <th class="col-arrow">Dir</th>
                            <th>Price</th>
                            <th>Size</th>
                        </tr>
                    </thead>
                    <tbody id="trades-body">
                        <tr><td colspan="3" class="empty">Loading…</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="column">
                <h2>👤 Players</h2>
                <table>
                    <thead>
                        <tr>
                            <th style="text-align:left">User</th>
                            <th>🍎 Apples</th>
                            <th>💰 Money</th>
                        </tr>
                    </thead>
                    <tbody id="users-body">
                        <tr><td colspan="3" class="empty">Loading…</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div style="text-align: center; margin-top: 30px;">
            <a href="/inputTrade" style="color: #666; text-decoration: none; border: 1px solid #444; padding: 10px 20px; border-radius: 5px;">[ Enter New Trade ]</a>
        </div>

        <script>
            let clockBase = 0;        // elapsed seconds reported by the server
            let clockSyncAt = 0;      // performance.now() when that value arrived
            let active = false;

            function fmt(secs) {
                const m = Math.floor(secs / 60);
                const s = secs % 60;
                return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
            }

            function renderClock() {
                let secs = clockBase;
                if (active) {
                    secs = clockBase + Math.floor((performance.now() - clockSyncAt) / 1000);
                }
                const minute = Math.floor(secs / 60);
                const blockStart = Math.floor(minute / 3) * 3;
                document.getElementById('clock').textContent = fmt(secs);
                document.getElementById('block-info').textContent =
                    'Minute ' + minute + ' · Block T+' + blockStart + 'm–T+' + (blockStart + 2) + 'm';
                const status = document.getElementById('status');
                status.textContent = active ? '● GAME ACTIVE' : '● GAME PAUSED';
                status.style.color = active ? '#00ff88' : '#ff4d4d';
            }

            function renderTrades(trades) {
                const body = document.getElementById('trades-body');
                if (!trades.length) {
                    body.innerHTML = '<tr><td colspan="3" class="empty">No trades yet.</td></tr>';
                    return;
                }
                body.innerHTML = trades.map(t => {
                    const cls = t.is_sell ? 'sell' : 'buy';
                    const arrow = t.is_sell ? '↓' : '↑';
                    const sign = t.is_sell ? '-' : '';
                    return '<tr class="' + cls + '">' +
                        '<td class="col-arrow"><span class="arrow">' + arrow + '</span></td>' +
                        '<td class="price-cell">' + t.price.toFixed(2) + '</td>' +
                        '<td class="size-cell">' + sign + t.size + '</td></tr>';
                }).join('');
            }

            function renderUsers(users) {
                const body = document.getElementById('users-body');
                if (!users.length) {
                    body.innerHTML = '<tr><td colspan="3" class="empty">No players.</td></tr>';
                    return;
                }
                body.innerHTML = users.map(u => {
                    let appleCls = 'apples-pos';
                    if (u.apples < 0) appleCls = 'apples-neg';
                    else if (u.role === 'consumer') appleCls = 'apples-zero';
                    const money = '$' + u.monies.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
                    return '<tr>' +
                        '<td class="user">' + u.username + ' <span class="role">' + u.role + '</span></td>' +
                        '<td class="' + appleCls + '">' + u.apples + '</td>' +
                        '<td class="money">' + money + '</td></tr>';
                }).join('');
            }

            async function refresh() {
                try {
                    const r = await fetch('/api/dashboard', {cache: 'no-store'});
                    const d = await r.json();
                    clockBase = d.elapsed_seconds;
                    clockSyncAt = performance.now();
                    active = d.is_active;
                    renderClock();
                    renderTrades(d.trades);
                    renderUsers(d.users);
                } catch (e) {
                    /* keep last good state on transient errors */
                }
            }

            setInterval(renderClock, 250);
            setInterval(refresh, 1000);
            refresh();
        </script>
    </body>
    </html>
    '''
    return render_template_string(dashboard_html)


GUIDE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>{{ title }} — Role Guide</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 40px; }
        .wrap { max-width: 760px; margin: auto; }
        .header { text-align: center; border: 1px solid {{ accent }}; border-radius: 12px;
                  padding: 30px; margin-bottom: 24px; background: #141414; }
        .emoji { font-size: 3rem; }
        h1 { margin: 8px 0; letter-spacing: 2px; }
        .intro { color: #aaa; line-height: 1.6; margin: 0 auto; max-width: 560px; }
        .card { background: #161616; border: 1px solid #222; border-radius: 12px;
                padding: 20px 26px; margin-bottom: 18px; }
        .card h2 { margin-top: 0; font-size: 1.05rem; text-transform: uppercase; letter-spacing: 1px;
                   border-bottom: 1px solid #2a2a2a; padding-bottom: 10px; }
        ul { margin: 0; padding-left: 22px; }
        li { margin: 10px 0; line-height: 1.55; }
        li b { color: #fff; }
        .nav { text-align: center; margin-top: 30px; }
        .nav a { color: #888; text-decoration: none; margin: 0 10px; border: 1px solid #444;
                 padding: 8px 16px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="wrap">
        <div class="header">
            <div class="emoji">{{ emoji }}</div>
            <h1>{{ title }}</h1>
            <p class="intro">{{ intro }}</p>
        </div>
        {% for heading, bullets in sections %}
        <div class="card">
            <h2 style="color: {{ accent }}">{{ heading }}</h2>
            <ul>
                {% for b in bullets %}<li>{{ b|safe }}</li>{% endfor %}
            </ul>
        </div>
        {% endfor %}
        <div class="nav">
            <a href="/dashboard">Dashboard</a>
            {% if show_targets %}<a href="/consumer-targets">Live Targets</a>{% endif %}
        </div>
    </div>
</body>
</html>
'''


def _render_guide(title, emoji, accent, intro, sections, show_targets=True):
    return render_template_string(
        GUIDE_HTML, title=title, emoji=emoji, accent=accent,
        intro=intro, sections=sections, show_targets=show_targets
    )


@bp.route('/farmer')
def farmer_guide():
    sections = [
        ("Your goal", [
            "Finish the game with as much <b>money</b> as possible.",
            "You earn money only by <b>selling apples</b> — there is nothing for you to buy.",
        ]),
        ("Growing apples", [
            "You start with <b>0 apples</b> and <b>$0</b>.",
            "Every minute you automatically <b>harvest more apples</b> on a fixed schedule — you don't have to do anything to receive them.",
            "Your barn holds at most <b>50 apples</b>. At the start of each minute, any apples above 50 are <b>lost</b>.",
        ]),
        ("Selling apples", [
            "You can <b>only sell</b> apples — you never buy.",
            "You sell your apples to the <b>Apple Makers</b>, who are the only buyers in the market.",
            "You're paid the agreed <b>price for every apple</b> you sell, so the higher the price, the more you earn.",
        ]),
        ("The 50-apple cap", [
            "Your barn holds at most <b>50 apples</b>.",
            "Any apples beyond 50 at the start of a minute are <b>lost</b>, so don't let your stock pile up.",
            "<b>Sell regularly</b> to keep your stock below the cap and waste nothing.",
        ]),
        ("Tips", [
            "<b>Sell high.</b> Hold out for Makers offering the best prices.",
            "Keep an eye on the <b>Dashboard</b> to watch the clock and your balances.",
        ]),
    ]
    return _render_guide(
        "Farmer", "🌾", "#00ff88",
        "You grow apples and sell them to Apple Makers. Your job is to harvest "
        "your crop and turn it into as much money as possible.",
        sections
    )


@bp.route('/maker')
def maker_guide():
    sections = [
        ("Your goal", [
            "Finish the game with as much <b>money</b> as possible.",
            "You profit by buying apples <b>cheaply from Farmers</b> and selling them <b>at a higher price to Consumers</b>.",
        ]),
        ("Your role in the market", [
            "You are the <b>market maker</b> for apples: every trade in the game goes through you.",
            "<b>Farmers sell</b> their apples to you, and <b>Consumers buy</b> apples from you.",
            "You can <b>both buy and sell</b>, and you decide the prices you offer.",
            "You start with <b>0 apples</b> and <b>$30,000</b> of capital.",
        ]),
        ("How your balances move", [
            "When a <b>Farmer sells</b> to you: you gain apples and pay out money.",
            "When a <b>Consumer buys</b> from you: you lose apples and take in money.",
            "You can never drop below <b>0 apples</b> or below <b>$0</b> — you need inventory to sell and cash to buy.",
        ]),
        ("Making a market (the spread)", [
            "Offer a <b>low price when buying</b> from Farmers and a <b>higher price when selling</b> to Consumers — the gap between them is your <b>spread</b>, and your profit.",
            "Manage your <b>inventory</b>: buy enough apples to meet the demand you expect from Consumers, but don't overpay or you'll erode your margin.",
        ]),
        ("Tips", [
            "Stay active on <b>both sides</b> of the market — you only profit when apples flow through you.",
            "Balance your buying and selling so you're rarely stuck with too many or too few apples.",
        ]),
    ]
    return _render_guide(
        "Apple Maker", "🏪", "#007bff",
        "You are the middle of the market. You buy apples from Farmers and sell "
        "them to Consumers, earning the spread between your prices.",
        sections
    )


@bp.route('/consumer')
def consumer_guide():
    sections = [
        ("Your goal", [
            "You are scored <b>first on how much of your apple target you fill</b>, then on <b>how much money you have left</b>.",
            "Meet every target — but spend wisely, because leftover cash is the tie-breaker.",
        ]),
        ("Your targets", [
            "The game is split into <b>3-minute blocks</b> (minutes 0–2, 3–5, 6–8, …).",
            "Each block you are given an <b>apple target</b>: the total apples you must buy during that block.",
            "Any apples you buy <b>during the block</b> count toward that block's target. Buying <b>more than the target earns no extra credit</b>.",
            "When a new block starts, a <b>fresh target</b> appears.",
        ]),
        ("Reading your target", [
            "On the <b>Dashboard</b> your target shows as a <b>negative number of apples</b> (for example <b>-130</b>).",
            "Each apple you buy moves it <b>toward 0</b>. When it reaches <b>0</b>, you've met the block target.",
        ]),
        ("Buying apples", [
            "You can <b>only buy</b> apples — you never sell.",
            "You buy your apples from the <b>Apple Makers</b>, who are the only sellers in the market.",
            "You start with <b>$100,000</b> to spend, and you pay the agreed <b>price for every apple</b> you buy.",
        ]),
        ("Tips", [
            "Don't leave a target to the last second — you have a <b>full 3 minutes</b> per block.",
            "<b>Buy low.</b> A filled target with cash to spare beats overpaying.",
        ]),
    ]
    return _render_guide(
        "Consumer", "🛒", "#ffa500",
        "You must buy a target number of apples in every 3-minute block. Hit your "
        "targets while spending as little as possible.",
        sections,
        show_targets=False
    )


@bp.route('/users')
def show_users():
    all_users = Users.query.all()

    users_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>User Directory</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; padding: 40px; }
            .container { max-width: 800px; margin: auto; }
            table { width: 100%; border-collapse: collapse; background: #1e1e1e; border-radius: 8px; overflow: hidden; }
            th, td { padding: 15px; text-align: left; border-bottom: 1px solid #333; }
            th { background: #252525; color: #888; text-transform: uppercase; font-size: 0.8rem; }
            tr:hover { background: #2a2a2a; }
            .money { color: #00ff88; font-family: monospace; }
            .apples { color: #ff4d4d; }
            .username { font-weight: bold; color: #fff; }
            h1 { text-align: center; }
            .back-link { display: block; text-align: center; margin-top: 20px; color: #666; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>User Balances</h1>
            <table>
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>🍎 Apples</th>
                        <th>💰 Money</th>
                    </tr>
                </thead>
                <tbody>
                    {% for user in users %}
                    <tr>
                        <td class="username">
                            {% if user.username.startswith('A') %}
                                <a href="/{{ user.username }}" style="color:#007bff; text-decoration:none;">{{ user.username }} 🏪</a>
                            {% else %}
                                {{ user.username }}
                            {% endif %}
                        </td>
                        <td class="apples">{{ user.apples }}</td>
                        <td class="money">${{ "{:,.2f}".format(user.monies) if user.monies else "0.00" }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <a href="/dashboard" class="back-link">← Back to Dashboard</a>
        </div>
    </body>
    </html>
    '''
    return render_template_string(users_html, users=all_users)


@bp.route('/inputTrade', methods=['GET', 'POST'])
def input_trade():
    if request.method == 'POST':
        ok, message = execute_trade(
            request.form.get('partyA'),
            request.form.get('partyB'),
            request.form.get('timeOffset'),
            request.form.get('price'),
            request.form.get('volume'),
        )
        flash(message, "success" if ok else "error")
        return redirect('/inputTrade?focus=apple' if ok else '/inputTrade')

    # Get the current minute for the auto-fill
    state = GameState.query.first()
    current_minute = 0
    if state and state.is_active and state.start_time:
        current_minute = int((datetime.now() - state.start_time).total_seconds() // 60)

    return render_template_string('''
        <style>
            body { font-family: sans-serif; background: #121212; color: #e0e0e0; }
            .container { display: flex; gap: 50px; padding: 20px; justify-content: center; }
            .box { flex: 1; max-width: 400px; border: 2px solid #ccc; padding: 20px; border-radius: 10px; }
            .apple-box { border-color: #ff4d4d; background: #1a1010; }
            input { width: 100%; margin-bottom: 10px; padding: 8px; box-sizing: border-box; background: #2d2d2d; color: white; border: 1px solid #444; }
            button { width: 100%; padding: 12px; cursor: pointer; font-weight: bold; border: none; border-radius: 5px; }

            .flash-container { max-width: 850px; margin: 20px auto; }
            .flash { padding: 15px; border-radius: 5px; margin-bottom: 10px; text-align: center; font-weight: bold; }
            .flash-success { background: #004d26; color: #00ff88; border: 1px solid #00ff88; }
            .flash-error { background: #4d0000; color: #ff4d4d; border: 1px solid #ff4d4d; }
            label { font-size: 0.8rem; color: #aaa; }
        </style>

        <div class="flash-container">
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}
        </div>

        <h1 style="text-align:center">Trading Floor</h1>
        <div class="container">
            <div class="box apple-box">
                <h2>🍎 Apple Trade</h2>
                <form method="POST">
                    <label>Taker (Party A)</label>
                    <input type="text" name="partyA" id="partyA_apple" placeholder="Username" required>
                    <label>Market Maker (Party B)</label>
                    <input type="text" name="partyB" placeholder="Username" required>
                    <label>Minute Offset</label>
                    <input type="number" name="timeOffset" value="{{ current_minute }}">
                    <label>Price</label>
                    <input type="number" step="any" name="price" required>
                    <label>Volume</label>
                    <input type="number" step="any" name="volume" required>
                    <button type="submit" style="background: #ff4d4d; color: white;">Execute Apple Trade</button>
                </form>
            </div>
        </div>
        
        <script>
            // Check the URL for the "focus" parameter
            const urlParams = new URLSearchParams(window.location.search);
            const focusTarget = urlParams.get('focus');

            if (focusTarget === 'apple') {
                document.getElementById('partyA_apple').focus();
            }
        </script>
        
        <p style="text-align: center;"><a href="/dashboard" style="color: #666;">View Live Dashboard</a></p>
    ''', current_minute=current_minute)


MAKER_TRADE_HTML = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ maker }} — Trade Desk</title>
        <style>
            body { font-family: sans-serif; background: #121212; color: #e0e0e0; }
            .container { display: flex; justify-content: center; padding: 20px; }
            .box { width: 100%; max-width: 420px; border: 2px solid #007bff; background: #101622; padding: 24px; border-radius: 10px; }
            input { width: 100%; margin-bottom: 12px; padding: 9px; box-sizing: border-box; background: #2d2d2d; color: white; border: 1px solid #444; }
            button { width: 100%; padding: 12px; cursor: pointer; font-weight: bold; border: none; border-radius: 5px; background: #007bff; color: white; }
            label { font-size: 0.8rem; color: #aaa; }
            .hint { font-size: 0.75rem; color: #777; margin: -6px 0 12px; }
            .summary { background: #0a0f18; border: 1px solid #007bff; border-radius: 6px;
                       padding: 12px; margin: 4px 0 16px; text-align: center; font-weight: bold;
                       color: #6cb2ff; min-height: 1.2em; }

            .flash-container { max-width: 420px; margin: 20px auto 0; }
            .flash { padding: 14px; border-radius: 5px; margin-bottom: 10px; text-align: center; font-weight: bold; }
            .flash-success { background: #004d26; color: #00ff88; border: 1px solid #00ff88; }
            .flash-error { background: #4d0000; color: #ff4d4d; border: 1px solid #ff4d4d; }
            h1 { text-align: center; }
            .maker-tag { color: #007bff; }
        </style>
    </head>
    <body>
        <div class="flash-container">
            {% with messages = get_flashed_messages(with_categories=true) %}
              {% if messages %}
                {% for category, message in messages %}
                  <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
              {% endif %}
            {% endwith %}
        </div>

        <h1>🏪 <span class="maker-tag">{{ maker }}</span> — Trade Desk</h1>
        <div class="container">
            <div class="box">
                <h2>🍎 Apple Trade as {{ maker }}</h2>
                <form method="POST">
                    <label>Volume</label>
                    <input type="number" step="any" id="volume" name="volume" required autofocus>
                    <div class="hint">Positive volume = {{ maker }} buys apples from the counterparty. Negative = {{ maker }} sells apples to the counterparty.</div>
                    <label>Price</label>
                    <input type="number" step="any" id="price" name="price" required>
                    <label>Counterparty</label>
                    <input type="text" id="counterparty" name="counterparty" placeholder="Farmer or Consumer (e.g. F0, C1)" required>
                    <div class="summary" id="summary"></div>
                    <button type="submit">Execute Trade as {{ maker }}</button>
                </form>
            </div>
        </div>
        <p style="text-align: center;"><a href="/dashboard" style="color: #666;">View Live Dashboard</a></p>
        <script>
            const makerName = "{{ maker }}";
            const volEl = document.getElementById('volume');
            const priceEl = document.getElementById('price');
            const cpEl = document.getElementById('counterparty');
            const summaryEl = document.getElementById('summary');
            function updateSummary() {
                const v = parseFloat(volEl.value);
                const p = parseFloat(priceEl.value);
                const cp = (cpEl.value || '').trim().toUpperCase() || '???';
                if (isNaN(v) || v === 0 || isNaN(p)) {
                    summaryEl.textContent = 'Enter volume, price and counterparty to preview the trade.';
                    return;
                }
                const qty = Math.abs(v);
                const verb = v > 0 ? 'Buying' : 'Selling';
                const direction = v > 0 ? 'from' : 'to';
                summaryEl.textContent = makerName + ' ' + verb + ' ' + qty + ' apples at $' + p + ' an apple ' + direction + ' ' + cp;
            }
            [volEl, priceEl, cpEl].forEach(el => el.addEventListener('input', updateSummary));
            updateSummary();
        </script>
    </body>
    </html>
'''


@bp.route('/<maker>', methods=['GET', 'POST'])
def maker_trade(maker):
    user_b = Users.query.filter_by(username=maker).first()
    if not user_b or not user_b.username.startswith('A'):
        abort(404)

    if request.method == 'POST':
        # The trade is always booked at the current game minute.
        _, _, current_minute = game_clock()

        # Volume is entered from the maker's point of view: positive = the maker
        # buys. execute_trade expects the counterparty's (taker's) delta, which
        # is the opposite sign.
        try:
            maker_volume = int(request.form.get('volume') or 0)
        except (TypeError, ValueError):
            maker_volume = 0

        ok, message = execute_trade(
            request.form.get('counterparty'),
            maker,
            current_minute,
            request.form.get('price'),
            -maker_volume,
        )
        flash(message, "success" if ok else "error")
        return redirect('/' + maker)

    return render_template_string(MAKER_TRADE_HTML, maker=maker)


@bp.route('/schedule')
def show_schedule():
    # We join with Users so we can display the name 'F1' instead of ID '1'
    updates = db.session.query(MinuteUpdates, Users).join(Users, MinuteUpdates.party == Users.id).order_by(
        MinuteUpdates.timeOffset).all()

    schedule_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Minute Update Schedule</title>
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; padding: 40px; }
            .container { max-width: 900px; margin: auto; }
            table { width: 100%; border-collapse: collapse; background: #1e1e1e; border-radius: 8px; overflow: hidden; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
            th { background: #252525; color: #888; text-transform: uppercase; font-size: 0.75rem; }
            .offset { color: #007bff; font-weight: bold; }
            .plus { color: #00ff88; }
            .minus { color: #ff4d4d; }
            h1 { text-align: center; }
            .nav { text-align: center; margin-bottom: 20px; }
            .nav a { color: #888; text-decoration: none; margin: 0 15px; border: 1px solid #444; padding: 5px 15px; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Ledger: Minute Updates</h1>
            <div class="nav">
                <a href="/dashboard">Dashboard</a>
                <a href="/users">Users</a>
                <a href="/admin">Admin</a>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Minute (Offset)</th>
                        <th>User</th>
                        <th>🍎 Apples</th>
                    </tr>
                </thead>
                <tbody>
                    {% for update, user in updates %}
                    <tr>
                        <td class="offset">T + {{ update.timeOffset }}m</td>
                        <td><strong>{{ user.username }}</strong></td>
                        <td class="{{ 'plus' if update.apples > 0 else 'minus' if update.apples < 0 }}">
                            {{ "+" if update.apples > 0 }}{{ update.apples or 0 }}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    '''
    return render_template_string(schedule_html, updates=updates)


@bp.route('/consumer-targets')
def consumer_targets():
    state = GameState.query.first()

    # 1. Calculate the current game minute
    current_minute = 0
    if state and state.is_active and state.start_time:
        total_seconds = (datetime.now() - state.start_time).total_seconds()
        current_minute = int(total_seconds // 60)

    # 2. Filter for Consumers (C) and the current 3-minute block.
    #    Targets are issued at the start of each block (minutes 0, 3, 6, ...).
    block_start = (current_minute // 3) * 3
    block_end = block_start + 2
    targets = db.session.query(MinuteUpdates, Users).join(
        Users, MinuteUpdates.party == Users.id
    ).filter(
        Users.username.startswith('C'),
        MinuteUpdates.timeOffset == block_start
    ).all()

    targets_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Consumer Targets</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body { font-family: 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 40px; text-align: center; }
            .container { max-width: 600px; margin: auto; }
            .clock-box { background: #1e1e1e; padding: 15px; border-radius: 8px; border: 1px solid #007bff; margin-bottom: 20px; }
            .minute-display { font-size: 2rem; color: #007bff; font-weight: bold; }
            table { width: 100%; border-collapse: collapse; background: #151515; border-radius: 8px; overflow: hidden; margin-top: 20px; }
            th, td { padding: 15px; text-align: left; border-bottom: 1px solid #222; }
            th { background: #202020; color: #888; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 1px; }
            .user { color: #fff; font-weight: bold; }
            .val { font-family: 'Courier New', monospace; font-weight: bold; font-size: 1.1rem; }
            .apple { color: #ff4d4d; }
            .empty-state { padding: 40px; color: #666; font-style: italic; }
            .status-tag { font-size: 0.8rem; padding: 4px 8px; border-radius: 4px; background: #222; margin-top: 10px; display: inline-block; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Current Block Targets</h1>

            <div class="clock-box">
                <div style="font-size: 0.8rem; color: #888;">GAME CLOCK</div>
                <div class="minute-display">T + {{ current_minute }}m</div>
                <div style="font-size: 0.8rem; color: #007bff; margin-top: 4px;">
                    Block window: T + {{ block_start }}m – T + {{ block_end }}m
                </div>
                <div class="status-tag" style="color: {{ '#00ff88' if is_active else '#ff4d4d' }}">
                    ● {{ "GAME ACTIVE" if is_active else "GAME PAUSED" }}
                </div>
            </div>

            {% if targets %}
            <table>
                <thead>
                    <tr>
                        <th>Consumer</th>
                        <th>🍎 Apples</th>
                    </tr>
                </thead>
                <tbody>
                    {% for update, user in targets %}
                    <tr>
                        <td class="user">{{ user.username }}</td>
                        <td class="val apple">{{ update.apples if update.apples else 0 }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty-state">
                No consumer targets scheduled for this block.
            </div>
            {% endif %}

            <div style="margin-top: 30px;">
                <a href="/dashboard" style="color: #444; text-decoration: none;">← Return to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    '''
    return render_template_string(
        targets_html,
        targets=targets,
        current_minute=current_minute,
        block_start=block_start,
        block_end=block_end,
        is_active=(state.is_active if state else False)
    )


@bp.route('/results')
def results():
    user_map = {u.id: u.username for u in Users.query.all()}
    results_data = compute_results()
    h = compute_trade_highlights()

    # Template Logic
    # Define the awards we want to display
    awards = [
        ('apple_best_buy', '🍎 Best Apple Buy (Lowest)'),
        ('apple_worst_buy', '🍎 Worst Apple Buy (Highest)'),
        ('apple_best_sell', '🍎 Best Apple Sell (Highest)'),
        ('apple_worst_sell', '🍎 Worst Apple Sell (Lowest)'),
        ('apple_big', '🍎 Largest Apple Trade')
    ]

    results_html = '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Final Market Results</title>
                <style>
                    body { font-family: 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }
                    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-bottom: 40px; }
                    .card { background: #161616; padding: 20px; border-radius: 12px; border: 1px solid #222; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
                    h2 { border-bottom: 1px solid #333; padding-bottom: 12px; color: #fff; font-size: 1.1rem; text-transform: uppercase; letter-spacing: 1px; }
                    table { width: 100%; border-collapse: collapse; }
                    th { text-align: left; color: #666; font-size: 0.7rem; text-transform: uppercase; padding: 10px; }
                    td { padding: 12px 10px; border-bottom: 1px solid #1f1f1f; font-size: 0.9rem; }
                    .money { color: #00ff88; font-family: 'Courier New', monospace; }
                    .user-tag { color: #007bff; font-weight: bold; }
                    .val-tag { color: #ffd700; font-weight: bold; font-family: 'Courier New', monospace; }
                    .time-tag { color: #888; font-style: italic; font-size: 0.8rem; }
                    .award-name { color: #aaa; font-weight: bold; font-size: 0.85rem; }
                </style>
            </head>
            <body>
                <h1 style="text-align:center; letter-spacing: 4px; margin-bottom: 40px;">MARKET RECAP</h1>

                <div class="grid">
                    {% for category, players in data.items() %}
                    <div class="card">
                        <h2>{{ category }}</h2>
                        <table>
                            <thead>
                                <tr><th>User</th><th style="text-align:right">Metric</th><th style="text-align:right">Cash</th></tr>
                            </thead>
                            <tbody>
                                {% for p in players %}
                                <tr>
                                    <td>{{ "🏆 " if loop.first }}{{ p.username }}</td>
                                    <td style="text-align:right">{{ p.fulfillment ~ '%' if 'C' in category else p.apples ~ ' 🍎' }}</td>
                                    <td class="money" style="text-align:right">${{ "{:,.2f}".format(p.monies) }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    {% endfor %}
                </div>

                <div class="card" style="max-width: 1000px; margin: 0 auto; border-color: #ffd700;">
                    <h2 style="color: #ffd700;">🌟 Market Hall of Fame</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Record</th>
                                <th>Party A (Taker)</th>
                                <th>Party B (Maker)</th>
                                <th style="text-align:right">Price</th>
                                <th style="text-align:right">Volume</th>
                                <th style="text-align:right">Time</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for key, label in awards %}
                            {% set t = h[key] %}
                            {% if t %}
                                {% set raw_vol = t.apples %}
                                {% set price = (t.monies / raw_vol) | abs %}
                                
                                <tr>
                                    <td class="award-name">{{ label }}</td>
                                    <td class="user-tag">{{ um[t.partyA] }}</td>
                                    <td class="user-tag">{{ um[t.partyB] }}</td>
                                    <td class="val-tag" style="text-align:right">${{ "{:.2f}".format(price) }}</td>
                                    <td class="val-tag" style="text-align:right; color: {{ '#ff4d4d' if raw_vol < 0 else '#00ff88' }};">
                                        {{ raw_vol | int }}
                                    </td>
                                    <td class="time-tag" style="text-align:right">T + {{ t.timeOffset }}m</td>
                                </tr>
                            {% endif %}
                            {% endfor %}
                        </tbody>
                    </table>
                </div>

                <p style="text-align:center; margin-top:50px;"><a href="/dashboard" style="color:#444; text-decoration:none;">[ RETURN TO DASHBOARD ]</a></p>
            </body>
            </html>
        '''
    return render_template_string(results_html, data=results_data, h=h, um=user_map, awards=awards)


@bp.route('/adjust', methods=['GET', 'POST'])
def adjust_user():
    message = ""
    if request.method == 'POST':
        target_username = request.form.get('username')
        user = Users.query.filter_by(username=target_username).first()

        if user:
            try:
                # Get values from form, default to 0 if empty
                d_apples = int(request.form.get('apples') or 0)
                d_monies = int(request.form.get('monies') or 0)

                # Apply increments
                user.apples = (user.apples or 0) + d_apples
                user.monies = (user.monies or 0) + d_monies

                db.session.commit()
                message = f"Successfully updated {target_username}!"
            except ValueError:
                message = "Error: Please enter valid numbers."
        else:
            message = "User not found."

    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Adjust Balances</title>
        <style>
            body { font-family: sans-serif; background: #121212; color: white; display: flex; justify-content: center; padding-top: 50px; }
            .card { background: #1e1e1e; padding: 30px; border-radius: 8px; border: 1px solid #333; width: 300px; }
            input { width: 100%; padding: 10px; margin: 10px 0; background: #2d2d2d; border: 1px solid #444; color: white; box-sizing: border-box; }
            button { width: 100%; padding: 10px; background: #007bff; color: white; border: none; cursor: pointer; font-weight: bold; }
            .msg { color: #00ff88; text-align: center; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>Adjust User</h2>
            {% if message %}<p class="msg">{{ message }}</p>{% endif %}
            <form method="POST">
                <input type="text" name="username" placeholder="Username (e.g. F1, C0)" required>
                <label>Add Apples:</label>
                <input type="number" name="apples" value="0">
                <label>Add Money:</label>
                <input type="number" name="monies" value="0">
                <button type="submit">Apply Adjustment</button>
            </form>
            <p style="text-align:center"><a href="/dashboard" style="color:#666;">Dashboard</a></p>
        </div>
    </body>
    </html>
    ''', message=message)


@bp.route('/admin', methods=['GET', 'POST'])
def admin():
    message = ""
    state = GameState.query.first()
    if not state:
        state = GameState(is_active=False)
        db.session.add(state)
        db.session.commit()

    if request.method == 'POST':
        action = request.form.get('action')

        # --- New Toggle Logic ---
        if action == 'toggle':
            if not state.is_active:
                state.is_active = True
                # Set start time only if it's the first time starting
                if not state.start_time:
                    state.start_time = datetime.now()
                state.last_tick = datetime.now()
                message = "Game Clock Started!"
                minuteUpdate(0)
            else:
                state.is_active = False
                message = "Game Clock Paused."
            db.session.commit()

        elif action == 'reset':
            db.session.query(Trades).delete()
            db.session.query(MinuteUpdates).delete()
            db.session.query(FarmerDiscards).delete()
            db.session.query(Users).delete()
            state.is_active = False
            state.start_time = None
            state.last_tick = None

            f = int(request.form.get('f_count') or 2)
            a = int(request.form.get('a_count') or 2)
            c = int(request.form.get('c_count') or 3)

            addUsers(f, a, c)
            generate_schedule()
            db.session.commit()
            message = "Game Fully Reset."

    # Determine button label and color based on state
    btn_label = "STOP GAME CLOCK" if state.is_active else "START GAME CLOCK"
    btn_class = "btn-stop" if state.is_active else "btn-start"

    admin_html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Control Panel</title>
        <style>
            body {{ font-family: sans-serif; background: #121212; color: white; padding: 40px; text-align: center; }}
            .card {{ background: #1e1e1e; padding: 20px; border-radius: 8px; border: 1px solid #333; 
                    display: inline-block; min-width: 350px; margin-bottom: 20px; vertical-align: top; }}
            .btn {{ display: block; width: 100%; padding: 12px; margin: 10px 0; border: none; 
                   border-radius: 4px; cursor: pointer; font-weight: bold; text-decoration: none; font-size: 0.9rem; }}
            .btn-start {{ background: #00ff88; color: #000; }}
            .btn-stop {{ background: #ffa500; color: #000; }}
            .btn-reset {{ background: #ff4d4d; color: white; margin-top: 20px; }}

            .input-group {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
            .input-group label {{ font-size: 0.8rem; color: #aaa; }}
            .input-group input {{ width: 50px; background: #333; border: 1px solid #444; color: white; padding: 5px; text-align: center; }}

            .nav-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px; }}
            .nav-link {{ background: #333; color: #eee; padding: 10px; text-decoration: none; border-radius: 4px; font-size: 0.8rem; border: 1px solid #444; }}
        </style>
    </head>
    <body>
        <h1>Admin Control Panel</h1>
        {{% if msg %}}<p style="color: #00ff88;">{{{{ msg }}}}</p>{{% endif %}}

        <div class="card">
            <h2>Game Status</h2>
            <form method="POST">
                <button type="submit" name="action" value="toggle" class="btn {btn_class}">{btn_label}</button>
            </form>
            <p style="font-size: 0.8rem; color: #666;">
                Status: <strong>{"ACTIVE" if state.is_active else "PAUSED"}</strong>
            </p>
        </div>

        <div class="card">
            <h2>Initialize Game</h2>
            <form method="POST">
                <div class="input-group"><label>Farmers (F)</label><input type="number" name="f_count" value="2"></div>
                <div class="input-group"><label>AppleMakers (A)</label><input type="number" name="a_count" value="2"></div>
                <div class="input-group"><label>Consumers (C)</label><input type="number" name="c_count" value="3"></div>
                <button type="submit" name="action" value="reset" class="btn btn-reset" 
                        onclick="return confirm('DANGER: This will delete ALL trades. Proceed?')">
                    WIPE & RESET GAME
                </button>
            </form>
        </div>

        <br>

        <div class="card" style="min-width: 720px;">
            <div class="nav-grid">
                <a href="/" class="nav-link">Home</a>
                <a href="/dashboard" class="nav-link">Dashboard</a>
                <a href="/inputTrade" class="nav-link">Trade Floor</a>
                <a href="/users" class="nav-link">User List</a>
                <a href="/consumer-targets" class="nav-link">Live Targets</a>
                <a href="/adjust" class="nav-link">Adjust Balances</a>
                <a href="/results" class="nav-link">Final Results</a>
                <a href="/schedule" class="nav-link">Ledger</a>
                <a href="/farmer" class="nav-link">🌾 Farmer Guide</a>
                <a href="/maker" class="nav-link">🏪 Maker Guide</a>
                <a href="/consumer" class="nav-link">🛒 Consumer Guide</a>
            </div>
        </div>
    </body>
    </html>
    '''
    return render_template_string(admin_html, msg=message)


@bp.route('/toggle_game', methods=['POST'])
def toggle_game():
    state = GameState.query.first()

    # If no state exists yet, create the singleton row
    if not state:
        state = GameState(is_active=False)
        db.session.add(state)
        db.session.commit()  # Commit here to ensure it exists before we modify it
        state = GameState.query.first()

    if not state.is_active:
        # STARTING THE GAME
        state.is_active = True
        state.start_time = datetime.now()
        state.last_tick = state.start_time
        db.session.commit()
        minuteUpdate(0)
    else:
        # STOPPING THE GAME
        state.is_active = False

    db.session.commit()
    return redirect('/admin')
