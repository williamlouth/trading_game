from datetime import datetime

from flask import (Blueprint, request, render_template_string, redirect,
                   flash, get_flashed_messages, jsonify)

from models import (db, Users, Trades, MinuteUpdates, GameState, FarmerDiscards,
                    minuteUpdate, tick_game, addUsers, generate_schedule,
                    validate_role, compute_results, compute_trade_highlights,
                    game_clock, dashboard_trades, dashboard_users)

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
                        <td class="username">{{ user.username }}</td>
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
        name_a = request.form.get('partyA')
        name_b = request.form.get('partyB')

        try:
            t_offset = int(request.form.get('timeOffset') or 0)
            price = int(request.form.get('price') or 0)
            volume = int(request.form.get('volume') or 0)

            if price <= 0:
                flash("Error: Price must be positive.", "error")
                return redirect('/inputTrade')
            if volume == 0:
                flash("Error: Volume cannot be zero.", "error")
                return redirect('/inputTrade')

            money_total = price * volume
            dA = volume

            user_a = Users.query.filter_by(username=name_a).first()
            user_b = Users.query.filter_by(username=name_b).first()

            if not user_a or not user_b:
                flash("Error: One or both users not found.", "error")
                return redirect('/inputTrade')

            if user_a.username[0] == 'A':
                flash(f"Error: {user_a.username} is a market maker and must always be Party B.", "error")
                return redirect('/inputTrade')

            if user_b.username[0] != 'A':
                flash(f"Error: {user_b.username} is not a market maker — Party B must be an Apple Maker (A).", "error")
                return redirect('/inputTrade')

            state = GameState.query.first()

            now = datetime.now()
            current_game_minute = 0
            if state and state.is_active and state.start_time:
                current_game_minute = int((now - state.start_time).total_seconds() // 60)

            # For late farmer apple sales, include discarded apples in validation
            is_late_farmer_apple_sale = (
                user_a.username.startswith("F") and
                dA < 0 and
                current_game_minute > t_offset
            )
            farmer_discard_record = None
            discard_apples = 0
            if is_late_farmer_apple_sale:
                farmer_discard_record = FarmerDiscards.query.filter_by(
                    party=user_a.id, timeOffset=t_offset
                ).first()
                discard_apples = farmer_discard_record.apples if farmer_discard_record else 0
                user_a.apples = (user_a.apples or 0) + discard_apples

            error_a = validate_role(user_a, dA, -money_total)

            if is_late_farmer_apple_sale:
                user_a.apples = (user_a.apples or 0) - discard_apples  # restore

            if error_a:
                flash(error_a, "error")
                return redirect('/inputTrade')

            # Party B: Loses apples, Gains money
            error_b = validate_role(user_b, -dA, money_total)
            if error_b:
                flash(error_b, "error")
                return redirect('/inputTrade')

            # If everything passes:
            if is_late_farmer_apple_sale and discard_apples > 0:
                absorbed = min(discard_apples, -dA)
                farmer_discard_record.apples -= absorbed
                user_a.apples = (user_a.apples or 0) + dA + absorbed
            else:
                user_a.apples += dA
            user_b.apples -= dA
            user_a.monies -= money_total
            user_b.monies += money_total

            new_trade = Trades(
                partyA=user_a.id,
                partyB=user_b.id,
                apples=dA,
                monies=-money_total,
                timeOffset=t_offset
            )
            db.session.add(new_trade)
            db.session.commit()

            # The Summary Message
            resource = "🍎 Apples"
            if volume > 0:
                 summary = f"Trade Executed: {name_a} bought {abs(volume)} {resource} from {name_b} at ${price:.2f} (Total: ${abs(money_total):.2f}) at T+{t_offset}m"
            else:
                summary = f"Trade Executed: {name_a} sold {abs(volume)} {resource} to {name_b} at ${price:.2f} (Total: ${abs(money_total):.2f}) at T+{t_offset}m"
            flash(summary, "success")

            return redirect('/inputTrade?focus=apple')


        except Exception as e:
            db.session.rollback()
            flash(f"System Error: {str(e)}", "error")
            return redirect('/inputTrade')

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

            f = int(request.form.get('f_count') or 4)
            a = int(request.form.get('a_count') or 4)
            c = int(request.form.get('c_count') or 4)

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
                <div class="input-group"><label>Farmers (F)</label><input type="number" name="f_count" value="4"></div>
                <div class="input-group"><label>AppleMakers (A)</label><input type="number" name="a_count" value="4"></div>
                <div class="input-group"><label>Consumers (C)</label><input type="number" name="c_count" value="4"></div>
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
