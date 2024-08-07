import json
from datetime import datetime, timedelta
import requests
from flask import jsonify
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from babel.numbers import format_currency as babel_format_currency
import random

plaid_api_instance = plaid_api.PlaidApi(plaid.ApiClient(plaid.Configuration(
    host=plaid.Environment.Sandbox,
    api_key={
        'clientId': '66a82b3f210c9b001a1cd0d7',  # Replace with your actual Plaid client ID
        'secret': '6311247e64d6f29f0cb12b790a5789',  # Replace with your actual Plaid secret
    }
)))

def create_link_token(user_id):
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Financial App",
        country_codes=[CountryCode('US')],
        language='en',
        user={
            'client_user_id': str(user_id),
        }
    )
    response = plaid_api_instance.link_token_create(request)
    return response

def exchange_public_token(public_token):
    request_data = ItemPublicTokenExchangeRequest(
        public_token=public_token
    )
    response = plaid_api_instance.item_public_token_exchange(request_data)
    return response['access_token'], response['item_id']

def fetch_transactions(access_token):
    start_date = datetime.now() - timedelta(days=365)
    end_date = datetime.today()

    request = TransactionsGetRequest(
        access_token=access_token,
        start_date=start_date.date(),
        end_date=end_date.date()
    )
    response = plaid_api_instance.transactions_get(request)
    
    transactions = response['transactions']

    # Pagination to get all transactions
    while len(transactions) < response['total_transactions']:
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date.date(),
            end_date=end_date.date(),
            options=TransactionsGetRequestOptions(
                offset=len(transactions)
            )
        )
        response = plaid_api_instance.transactions_get(request)
        transactions.extend(response['transactions'])

    # Convert date fields to strings
    for transaction in transactions:
        transaction['date'] = transaction['date'].strftime('%Y-%m-%d')

    return transactions

def extract_and_analyze(transactions_data):
    # Placeholder for actual analysis logic
    total_spent = sum(txn['amount'] for txn in transactions_data if txn['amount'] < 0)
    total_earned = sum(txn['amount'] for txn in transactions_data if txn['amount'] > 0)
    net_income = total_earned + total_spent  # total_spent is negative
    year = datetime.today().year  # Placeholder

    ai_data = {
        'total_spent': total_spent,
        'total_earned': total_earned,
        'net_income': net_income,
        'year': year,
        'bank_name': "Your Bank"
    }

    planet_data = {
        "leadership_index": 0.8,
        "decision_confidence": 0.9,
        "financial_stability_index": 0.85,
        "emotional_spending_tracker": 0.1,
        "opportunity_pursuit_score": 0.7,
        "risk_adjusted_return": 0.75,
        "market_analysis_accuracy": 0.6,
        "communication_effectiveness": 0.7,
        "wealth_growth_rate": 0.8,
        "long_term_investment_success": 0.9,
        "asset_appreciation_rate": 0.85,
        "lifestyle_quality_index": 0.7,
        "savings_rate": 0.6,
        "financial_plan_adherence": 0.75,
        "ambition_index": 0.8,
        "innovative_investment_success": 0.7,
        "financial_freedom_score": 0.85,
        "minimalist_wealth_growth": 0.6
    }

    return json.dumps(ai_data), json.dumps(planet_data)

def convert_currency(amount, from_currency, to_currency, conversion_rate):
    if from_currency == to_currency:
        return amount
    elif from_currency == "USD" and to_currency == "INR":
        return amount * conversion_rate
    elif from_currency == "INR" and to_currency == "USD":
        return amount / conversion_rate
    return amount

def get_exchange_rate():
    api_url = "https://api.exchangerate-api.com/v4/latest/USD"
    response = requests.get(api_url)
    data = response.json()
    return data["rates"]["INR"]

def format_kpi_texts(planet_data):
    return planet_data

def get_dynamic_title_subtitle(analysis_type, year):
    titles_analytics1 = [
        f"Your Year {year} in Review",
        f"{year} Summary - Your Money Matters",
        f"Taking a Look Back at Your {year} Finances",
        f"How Your Wallet Fared in {year}",
        f"{year} Financial Recap - Let's Dive In!"
    ]

    titles_analytics2 = [
        f"Unveiling Your {year} Financial Story",
        f"Breaking Down Your {year} Expenses and Earnings",
        f"Discovering Your {year} Financial Journey",
        f"{year} Financial Highlights"
    ]

    subtitles_analytics2 = [
        f"{year} - Your Financial Journey Unfolded",
        f"A Deep Dive into Your {year} Finances",
        f"How You Made and Spent Money in {year}",
        f"Exploring Your {year} Financial Peaks",
        f"Your {year} Money Matters"
    ]

    if analysis_type == "analytics1":
        return random.choice(titles_analytics1), None
    elif analysis_type == "analytics2":
        return random.choice(titles_analytics2), random.choice(subtitles_analytics2)
    else:
        return "", ""

def get_dynamic_text(username, year):
    text_templates = [
        f"{username}, {year} has been great for you, getting your detailed analysis now.",
        f"Hang tight, {username}! Your {year} financial insights are on the way.",
        f"{username}, let's dive into your {year} financial journey!",
        f"Ready to see how {year} treated your wallet, {username}? Here we go!",
        f"{username}, {year} was a big year. Your financial breakdown is coming up!"
    ]
    return random.choice(text_templates)

def get_dynamic_text2(username, netincome, currency):
    netincome = round(float(netincome))
    formatted_income = babel_format_currency(int(netincome), currency)
    text_templates = [
        f"Wow, {username}! You have a net income of {formatted_income}.",
        f"Fantastic job, {username}! Your net income stands at {formatted_income}.",
        f"Impressive, {username}! With a net income of {formatted_income}, you're officially a money wizard!",
        f"Wowza, {username}! With a net income of {formatted_income}, you're a financial superstar!",
        f"Bravo, {username}! You've earned {formatted_income}. Your financial game is strong!"
    ]
    return random.choice(text_templates)
