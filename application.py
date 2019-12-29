import os
from datetime import datetime

import sqlite3
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import *

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
# app.jinja_env.filters["currencify"] = currencify

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Create sqlite database
db = sqlite3.connect('database.db', check_same_thread=False)

# Configure database
db.execute(""" CREATE TABLE IF NOT EXISTS users (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               username TEXT NOT NULL,
               hash TEXT NOT NULL
               ); """)
db.execute(""" CREATE TABLE IF NOT EXISTS trips (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   name TEXT NOT NULL,
                   pri_curr TEXT NOT NULL,
                   curr_opt TEXT NOT NULL,
                   hist_rate TEXT NOT NULL
               ); """)
db.execute(""" CREATE TABLE IF NOT EXISTS transactions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   description TEXT NOT NULL,
                   amount REAL NOT NULL,
                   lender_id INTEGER NOT NULL,
                   borrower_id INTEGER NOT NULL,
                   time TEXT NOT NULL
               ); """)
db.execute(""" CREATE TABLE IF NOT EXISTS trip_connect (
                   trip_id INTEGER NOT NULL,
                   user_id INTEGER NOT NULL
               ); """)

@app.route("/")
@login_required
def index():
    return redirect("/index")

@app.route("/index", methods=["GET"])
@login_required
def table():
    user_id = session["user_id"]

    # Obtain all trips pertaining to user
    trips = db.execute(""" SELECT id, name, pri_curr
                        FROM (trips LEFT JOIN trip_connect ON (trips.id=trip_connect.trip_id)) AS a
                        WHERE a.user_id = ? """,
                        (user_id,)).fetchall()

    # Obtain sum of money owed to the user and sum of money user owes to other people
    owed = db.execute(""" SELECT t1.amount, t2.pri_curr
                            FROM transactions AS t1 LEFT JOIN trips AS t2 ON (t1.trip_id=t2.id)
                            WHERE lender_id = ? """, (user_id,)).fetchall()
    sum_owed = 0
    for row in owed:
        amt = row[0]
        curr = row[1]
        usd_amt = currency_convert(amt, "USD", curr)
        sum_owed += usd_amt
    owed = "US" + currencify(sum_owed, "USD")

    owing = db.execute(""" SELECT t1.amount, t2.pri_curr
                            FROM transactions AS t1 LEFT JOIN trips AS t2 ON (t1.trip_id=t2.id)
                            WHERE borrower_id = ? """, (user_id,)).fetchall()
    sum_owing = 0
    for row in owing:
        amt = row[0]
        curr = row[1]
        usd_amt = currency_convert(amt, "USD", curr)
        sum_owing += usd_amt
    owing = "US" + currencify(sum_owing, "USD")

    sum_net = sum_owed - sum_owing
    net = "US" + currencify(sum_net, "USD")

    return render_template("index.html", user_id=user_id, trips=trips, owed=owed, owing=owing, net=net)

@app.route("/update/<id>", methods=["GET", "POST"])
@login_required
def trip_update(id):
    user_id = session["user_id"]
    trip_id = id
    pri_curr = db.execute("SELECT pri_curr FROM trips WHERE id = ?", (trip_id,)).fetchall()[0][0]
    cur_list = ['USD', 'CAD', 'HKD', 'ISK', 'PHP', 'DKK', 'HUF', 'CZK', 'GBP', 'RON', 'SEK', 'IDR', 'INR', 'BRL', 'RUB', 'HRK', 'JPY', 'THB', 'CHF', 'EUR', 'MYR', 'BGN', 'TRY', 'CNY', 'NOK', 'NZD', 'ZAR', 'USD', 'MXN', 'SGD', 'AUD', 'ILS', 'KRW', 'PLN']

    if request.method == "POST":
        # check if fields are all completed
        if not request.form.get("amount") or not request.form.get("currency") or not request.form.get("receipient") or not request.form.get("description"):
            return apology("Please complete all the fields", 400)
        
        # prevent posting transaction to self
        if int(request.form.get("receipient")) == user_id:
            return apology("Cannot post transaction to self", 400)

        # update transactions table
        now = datetime.now()
        description = request.form.get("description")
        amount = currency_convert(request.form.get("amount"), pri_curr, request.form.get("currency"))
        borrower_id = request.form.get("receipient")
        db.execute(""" INSERT INTO transactions(description, amount, lender_id, borrower_id, time, trip_id)
                        VALUES(?, ?, ?, ?, ?, ?) """, (description, amount, user_id, borrower_id, now, trip_id))
        db.commit()

        # success
        return redirect("/update/" + trip_id)
    else:
        trip_name = db.execute("SELECT name FROM trips WHERE id = ?", (trip_id,)).fetchall()

        # Check if trip exists
        if len(trip_name) == 0:
            return apology("Unable to find trip", 400)
        # Check if user is authorized to view trip details
        trip_check = db.execute("SELECT * FROM trip_connect WHERE trip_id = ? AND user_id = ?", (trip_id, user_id)).fetchall()
        if len(trip_check) == 0:
            return apology("Not authorized to view content", 400)

        balance_info = db.execute(""" WITH sum_owed AS (SELECT users.id, COALESCE(SUM(transactions.amount), 0) AS owed
                                        FROM users LEFT JOIN transactions ON users.id = lender_id
                                        WHERE transactions.trip_id = ?
                                        GROUP BY users.id), 
										sum_owing AS (SELECT users.id, COALESCE(SUM(transactions.amount), 0) AS owing
                                        FROM users LEFT JOIN transactions ON users.id = borrower_id
                                        WHERE transactions.trip_id = ?
                                        GROUP BY users.id),
										distinct_id AS (SELECT DISTINCT(user_id) FROM trip_connect WHERE trip_id = ? ORDER BY user_id)
										
										SELECT a.user_id, users.username,  COALESCE(b.owed, 0) - COALESCE(c.owing, 0) AS NET
										FROM distinct_id AS a
										LEFT JOIN sum_owed AS b ON (a.user_id = b.id)
										LEFT JOIN sum_owing AS c ON (a.user_id = c.id)
										LEFT JOIN users ON (a.user_id  = users.id) """, (trip_id, trip_id, trip_id)).fetchall()
        # add currency symbol
        balances = []
        for balance in balance_info:
            tmp_list = []
            tmp_list.append(balance[0])
            tmp_list.append(balance[1])
            tmp_list.append(currencify(balance[2], pri_curr))
            balances.append(tmp_list)

        # query transactions info
        transactions_info = db.execute(""" SELECT u1.username, u2.username, t.amount, t.time, t.description 
                                        FROM transactions AS t LEFT JOIN users AS u1 ON t.lender_id = u1.id
                                        LEFT JOIN users AS u2 ON t.borrower_id = u2.id
                                        WHERE trip_id = ?""", (trip_id,)).fetchall()

        # add currency symbol
        transactions = []
        for transaction in transactions_info:
            tmp_list = []
            tmp_list.append(transaction[0])
            tmp_list.append(transaction[1])
            tmp_list.append(currencify(transaction[2],pri_curr))
            tmp_list.append(transaction[3])
            tmp_list.append(transaction[4])
            transactions.append(tmp_list)

        return render_template("update_trip.html", trip_id=trip_id, trip_name=trip_name[0][0].upper(), balances=balances, cur_list=cur_list, pri_curr=pri_curr, transactions=transactions, user_id=int(user_id))

@app.route("/participants/<id>", methods=["GET", "POST"])
@login_required
def participants(id):
    trip_id = id
    if request.method == "POST":
        # ensure field is not blank
        if not request.form.get("participant"):
            return apology("Please fill in all the fields", 400)

        participant_user = request.form.get("participant")
        # ensure username of participant exists
        participant_check = db.execute("SELECT id FROM users WHERE username = ?", (participant_user,)).fetchall()
        if len(participant_check) != 1:
            return apology("Participant does not exist", 400)
        
        # add participant to trip_connect table
        participant_id = participant_check[0][0]
        db.execute("INSERT INTO trip_connect(user_id, trip_id) VALUES(?, ?)", (participant_id, trip_id))
        db.commit()

        # success
        return redirect("/participants/" + trip_id)
    else:
        # Obtain all participants pertaining to trip
        participants = db.execute(""" SELECT b.username, b.id
                                FROM trip_connect AS a LEFT JOIN users AS b ON a.user_id = b.id
                                WHERE trip_id = ? """,
                                (trip_id,)).fetchall()

        return render_template("participants.html", trip_id=trip_id, participants=participants)

@app.route("/remove", methods=["GET"])
def remove():
    participant_id = request.args.get('participant_id', 0, type=int)
    trip_id = request.args.get('trip_id', 0, type=int)
    # remove records
    db.execute("DELETE FROM trip_connect WHERE user_id = ? AND trip_id = ?", (participant_id, trip_id))
    db.execute("DELETE FROM transactions WHERE (lender_id = ? OR borrower_id = ?) AND trip_id = ?", (participant_id, participant_id, trip_id))
    db.commit()
    # success
    return jsonify(remove_success="true")

@app.route("/remove_trip", methods=["GET"])
def remove_trip():
    trip_id = request.args.get('trip_id', 0, type=int)
    # remove records
    db.execute("DELETE FROM trip_connect WHERE trip_id = ?", (trip_id,))
    db.execute("DELETE FROM transactions WHERE trip_id = ?", (trip_id,))
    db.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
    db.commit()
    # success
    return jsonify(remove_success="true")

@app.route("/add_trip", methods=["GET", "POST"])
@login_required
def add_trip():
    user_id = session["user_id"]
    if request.method == "POST":
        # Ensure form submitted has no nil entries
        if not request.form.get("trip") or not request.form.get("currency"):
            return apology("Please make sure the form has been filled up", 400)
        # Create trip in database
        trip_name = request.form.get("trip")
        primary_currency = request.form.get("currency")
        db.execute("INSERT INTO trips(name, pri_curr) VALUES(?, ?)", (trip_name, primary_currency))
        db.commit()

        # Update trip_connect table to connect user to trip
        last_id = db.execute("SELECT id FROM trips WHERE id=(SELECT max(id) FROM trips)").fetchall()[0][0]
        db.execute("INSERT INTO trip_connect(trip_id, user_id) VALUES(?, ?)", (last_id, user_id))
        db.commit()

        # Success
        return redirect("/")
    else:
        cur_list = ['USD', 'CAD', 'HKD', 'ISK', 'PHP', 'DKK', 'HUF', 'CZK', 'GBP', 'RON', 'SEK', 'IDR', 'INR', 'BRL', 'RUB', 'HRK', 'JPY', 'THB', 'CHF', 'EUR', 'MYR', 'BGN', 'TRY', 'CNY', 'NOK', 'NZD', 'ZAR', 'USD', 'MXN', 'SGD', 'AUD', 'ILS', 'KRW', 'PLN']
        return render_template("addtrip.html", cur_list=cur_list)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          (request.form.get("username"),)).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0][2], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0][0]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get('username', 0, type=str)
    if len(username) > 1:
        checkAvailability = db.execute("SELECT COUNT(*) AS count FROM users WHERE username = ?", (username,)).fetchall()
        if checkAvailability[0][0] == 0:
            return jsonify(availability="true")
    return jsonify(availability="false")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST
    if request.method == "POST":
        # Ensure username was created
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was created
        elif not request.form.get("password"):
            return apology("must provide password", 400)
            
        # Ensure password was confirmed
        elif not request.form.get("confirmation"):
            return apology("must enter confirmation", 400)
        
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        
        # Ensure passwords match
        if password != confirmation:
            return apology("passwords do not match", 400)
            
        # Reject duplicate username
        checkAvailability = db.execute("SELECT COUNT(*) AS count FROM users WHERE username = ?", (username,)).fetchall()
        if checkAvailability[0][0] > 0:
            return apology("username already exists", 400)
            
        # Insert new user into db
        hashed_pw = generate_password_hash(password)
        db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", (username, hashed_pw))
        db.commit()
        
        # Redirect user to login page
        return redirect("/login")
        
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
