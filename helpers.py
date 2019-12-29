import os
import requests
import urllib.parse
import json

from flask import redirect, render_template, request, session
from functools import wraps


def apology(message, code=400):
    """Render message as an apology to user."""
    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("apology.html", code=code, message=message), code

def login_required(f):
    """
    Decorate routes to require login.

    http://flask.pocoo.org/docs/1.0/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

def currencify(value, currency):
    value = float(value)
    """Format value as currency."""
    if currency in ["USD", "CAD", "HKD", "SGD", "AUD", "NZD", "MXN"]:
        return f"${value:,.2f}"
    if currency == "PHP":
        return f"₱{value:,.2f}"
    elif currency in ["ISK", "DKK", "SEK", "NOK"]:
        return f"{value:,.2f}Kr"
    elif currency == "HUF":
        return f"{value:,.2f}Ft"
    elif currency == "CZK":
        return f"{value:,.2f}Kč"
    elif currency == "GBP":
        return f"£{value:,.2f}"
    elif currency == "RON":
        return f"{value:,.2f}lei"
    elif currency == "IDR":
        return f"{value:,.2f}Rp"
    elif currency == "INR":
        return f"₹{value:,.2f}"
    elif currency == "BRL":
        return f"R${value:,.2f}"
    elif currency == "RUB":
        return f"₽{value:,.2f}"
    elif currency == "HRK":
        return f"{value:,.2f}kn"
    elif currency == "JPY":
        return f"¥{value:,.2f}"
    elif currency == "THB":
        return f"฿{value:,.2f}"
    elif currency == "CHF":
        return f"{value:,.2f}SFr"
    elif currency == "EUR":
        return f"€{value:,.2f}"
    elif currency == "MYR":
        return f"{value:,.2f}RM"
    elif currency == "BGN":
        return f"{value:,.2f}Лв"
    elif currency == "TRY":
        return f"₺{value:,.2f}"
    elif currency == "CNY":
        return f"¥{value:,.2f}"
    elif currency == "ZAR":
        return f"{value:,.2f}R"
    elif currency == "ILS":
        return f"₪{value:,.2f}"
    elif currency == "KRW":
        return f"₩{value:,.2f}"
    elif currency == "PLN":
        return f"{value:,.2f}zł"

def currency_convert(amount, home_currency, converting_currency):
    x = home_currency
    response = requests.get("https://api.exchangeratesapi.io/latest?base=" + x)
    response_json = response.json()
    rate = float(response_json["rates"][converting_currency])
    return float(amount) / rate