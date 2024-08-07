import os
import json
import random
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode
from urllib.parse import quote_plus
import random
import locale
from babel.numbers import format_currency as babel_format_currency
from extract import create_link_token, exchange_public_token, fetch_transactions, extract_and_analyze, convert_currency, get_exchange_rate, format_kpi_texts, get_dynamic_title_subtitle, get_dynamic_text, get_dynamic_text2

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with your secret key

# Configure Plaid
PLAID_CLIENT_ID = '66a82b3f210c9b001a1cd0d7'  # Replace with your actual Plaid client ID
PLAID_SECRET = '6311247e64d6f29f0cb12b790a5789'  # Replace with your actual Plaid secret
PLAID_ENV = os.getenv('PLAID_ENV', 'sandbox')  # Replace with your Plaid environment

if not PLAID_CLIENT_ID or not PLAID_SECRET:
    raise ValueError("PLAID_CLIENT_ID and PLAID_SECRET must be set")

configuration = plaid.Configuration(
    host=getattr(plaid.Environment, PLAID_ENV.capitalize()),  # or use plaid.Environment.Development or plaid.Environment.Production
    api_key={
        'clientId': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
    }
)
client = plaid.ApiClient(configuration)
plaid_api_instance = plaid_api.PlaidApi(client)

# Configure SQLAlchemy with SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


def format_currency(amount, currency):
    if currency == 'INR':
        return babel_format_currency(amount, 'INR', locale='en_IN')
    else:
        return babel_format_currency(amount, 'USD', locale='en_US')

# Define User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(150), nullable=False)
    access_token = db.Column(db.String(500), nullable=True)
    item_id = db.Column(db.String(500), nullable=True)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200))
    category = db.Column(db.String(200))
    account_id = db.Column(db.String(100))
    pending = db.Column(db.Boolean)

# Initialize database
with app.app_context():
    db.create_all()

@app.route('/', methods=['GET', 'POST'])
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['access_token'] = user.access_token
            session['item_id'] = user.item_id

            if user.access_token and user.item_id:
                return redirect(url_for('get_transactions'))
            else:
                return redirect(url_for('index'))

        else:
            return 'Invalid email or password'
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/index', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    return render_template('index.html')

@app.route('/create_link_token', methods=['POST'])
def create_link_token_route():
    user = User.query.get(session['user_id'])
    client_user_id = str(user.id)

    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Financial App",
        country_codes=[CountryCode('US')],
        language='en',
        user={
            'client_user_id': client_user_id,
        }
    )
    response = plaid_api_instance.link_token_create(request)
    return jsonify(response.to_dict())

@app.route('/exchange_public_token', methods=['POST'])
def exchange_public_token_route():
    public_token = request.json.get('public_token')
    if not public_token:
        return jsonify({'error': 'public_token not provided'}), 400
    
    try:
        access_token, item_id = exchange_public_token(public_token)
        
        # Save the access token and item_id to the user record
        user = User.query.get(session['user_id'])
        user.access_token = access_token
        user.item_id = item_id
        db.session.commit()

        session['access_token'] = access_token
        session['item_id'] = item_id
        return jsonify({'public_token_exchange': 'complete', 'redirect_url': url_for('get_transactions')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_transactions', methods=['GET'])
def get_transactions():
    access_token = session.get('access_token')
    user_id = session.get('user_id')
    if not access_token:
        return jsonify({'error': 'Access token not found'}), 400

    # Check if transactions already exist in the database for this user
    existing_transactions = Transaction.query.filter_by(user_id=user_id).all()
    if existing_transactions:
        # Redirect to the dashboard if transactions already exist
        return redirect(url_for('dashboard'))

    try:
        # Fetch transactions from Plaid
        all_transactions = fetch_transactions(access_token)
        
        # Save transactions to SQLite
        for txn in all_transactions:
            transaction = Transaction(
                user_id=user_id,
                transaction_id=txn['transaction_id'],
                amount=txn['amount'],
                date=txn['date'],
                name=txn.get('name'),
                category=','.join(txn['category']) if txn.get('category') else None,
                account_id=txn['account_id'],
                pending=txn['pending']
            )
            db.session.add(transaction)
        db.session.commit()

        # Redirect to the dashboard
        return redirect(url_for('dashboard'))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/dashboard', methods=['GET'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    transactions_data = [{
        'transaction_id': txn.transaction_id,
        'amount': txn.amount,
        'date': txn.date,
        'name': txn.name,
        'category': txn.category,
        'account_id': txn.account_id,
        'pending': txn.pending
    } for txn in transactions]

    balance = sum(txn['amount'] for txn in transactions_data)
    income_this_month = sum(txn['amount'] for txn in transactions_data if txn['amount'] > 0)
    expense_this_month = sum(txn['amount'] for txn in transactions_data if txn['amount'] < 0)

    # Format values to 2 decimal places and remove negative sign
    balance_formatted = f"{abs(balance):.2f}"
    income_this_month_formatted = f"{abs(income_this_month):.2f}"
    expense_this_month_formatted = f"{abs(expense_this_month):.2f}"
    total_balance = balance_formatted  # Adjust this calculation based on your specific needs

    return render_template('dashboard.html', transactions=transactions_data, balance=balance_formatted, income_this_month=income_this_month_formatted, expense_this_month=expense_this_month_formatted, total_balance=total_balance)


@app.route('/get_chart_data')
def get_chart_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    data_type = request.args.get('type', 'income')
    period = int(request.args.get('period', 30))

    end_date = datetime.now()
    start_date = end_date - timedelta(days=period)

    transactions = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.date >= start_date.strftime('%Y-%m-%d'),
        Transaction.date <= end_date.strftime('%Y-%m-%d')
    ).all()

    if data_type == 'income':
        filtered_transactions = [txn for txn in transactions if txn.amount > 0]
    elif data_type == 'expense':
        filtered_transactions = [txn for txn in transactions if txn.amount < 0]
    elif data_type == 'savings':
        filtered_transactions = [txn for txn in transactions if 'savings' in (txn.category or '').lower()]
    elif data_type == 'investment':
        filtered_transactions = [txn for txn in transactions if 'investment' in (txn.category or '').lower()]
    else:
        filtered_transactions = transactions

    labels = []
    values = []

    date_range = (end_date - start_date).days + 1
    for i in range(date_range):
        date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
        labels.append(date)
        daily_total = sum(txn.amount for txn in filtered_transactions if txn.date == date)
        values.append(daily_total)

    return jsonify({
        'labels': labels,
        'values': values
    })


@app.route('/analytics1', methods=['GET', 'POST'])
def analytics1():
    access_token = session.get('access_token')
    if not access_token:
        return redirect(url_for('login'))

    transactions = Transaction.query.filter_by(user_id=session['user_id']).all()
    transactions_data = [{
        'transaction_id': txn.transaction_id,
        'amount': txn.amount,
        'date': txn.date,
        'name': txn.name,
        'category': txn.category,
        'account_id': txn.account_id,
        'pending': txn.pending
    } for txn in transactions]

    if not transactions_data:
        return redirect(url_for('index'))

    ai_analysis, planet_analysis = extract_and_analyze(transactions_data)
    session['ai_analysis'] = ai_analysis
    session['planet_analysis'] = planet_analysis
    
    ai_data = json.loads(ai_analysis)
    title, _ = get_dynamic_title_subtitle("analytics1", ai_data['year'])

    currency = request.args.get('currency', 'USD')
    original_currency = 'INR' if 'Bank' in ai_data['bank_name'] else 'USD'
    conversion_rate = get_exchange_rate()  # Fetch the current exchange rate

    ai_data['total_spent'] = convert_currency(ai_data['total_spent'], original_currency, currency, conversion_rate)
    ai_data['total_earned'] = convert_currency(ai_data['total_earned'], original_currency, currency, conversion_rate)
    ai_data['net_income'] = convert_currency(ai_data['net_income'], original_currency, currency, conversion_rate)

    ai_data['total_spent'] = format_currency(ai_data['total_spent'], currency)
    ai_data['total_earned'] = format_currency(ai_data['total_earned'], currency)
    ai_data['net_income'] = format_currency(ai_data['net_income'], currency)

    if request.method == 'POST':
        return redirect(url_for('post_analytics1', currency=currency))
    
    return render_template('analytics1.html', title=title, ai_data=ai_data, currency=currency)

@app.route('/transition1')
def transition1():
    ai_analysis = session.get('ai_analysis')
    ai_data = json.loads(ai_analysis)
    username = session.get('username')
    year = ai_data.get('year')
    dynamic_text = get_dynamic_text(username, year)
    return render_template('transition1.html', ai_analysis=ai_analysis, dynamic_text=dynamic_text)

@app.route('/post_analytics1', methods=['POST'])
def post_analytics1():
    currency = request.args.get('currency', 'USD')
    return redirect(url_for('transition1', currency=currency))

@app.route('/analytics2', methods=['GET', 'POST'])
def analytics2():
    ai_analysis = session.get('ai_analysis')
    if not ai_analysis:
        return redirect(url_for('index'))

    try:
        ai_data = json.loads(ai_analysis)
    except json.JSONDecodeError as e:
        return f"JSON decode error: {e}"
    except Exception as e:
        return f"An error occurred: {e}"
    
    title, subtitle = get_dynamic_title_subtitle("analytics2", ai_data['year'])

    currency = request.args.get('currency', 'USD')
    original_currency = 'INR' if 'Bank' in ai_data['bank_name'] else 'USD'
    conversion_rate = get_exchange_rate()  # Fetch the current exchange rate

    ai_data['total_spent'] = convert_currency(ai_data['total_spent'], original_currency, currency, conversion_rate)
    ai_data['total_earned'] = convert_currency(ai_data['total_earned'], original_currency, currency, conversion_rate)

    ai_data['total_spent'] = format_currency(ai_data['total_spent'], currency)
    ai_data['total_earned'] = format_currency(ai_data['total_earned'], currency)
    
    if request.method == 'POST':
        return redirect(url_for('post_analytics2', currency=currency))
    
    return render_template('analytics2.html', ai_data=ai_data, title=title, subtitle=subtitle, currency=currency)

@app.route('/transition2')
def transition2():
    ai_analysis = session.get('ai_analysis')
    ai_data = json.loads(ai_analysis)
    username = session.get('username')
    netincome = ai_data.get('net_income')
    currency = request.args.get('currency', 'USD')
    original_currency = 'INR' if 'Bank' in ai_data['bank_name'] else 'USD'
    conversion_rate = get_exchange_rate()  # Fetch the current exchange rate

    netincome = convert_currency(netincome, original_currency, currency, conversion_rate)
    dynamic_text = get_dynamic_text2(username, netincome, currency)
    return render_template('transition2.html', ai_analysis=ai_analysis, dynamic_text=dynamic_text, currency=currency)

@app.route('/post_analytics2', methods=['POST'])
def post_analytics2():
    currency = request.args.get('currency', 'USD')
    return redirect(url_for('transition2', currency=currency))

@app.route('/analytics3', methods=['GET', 'POST'])
def analytics3():
    ai_analysis = session.get('ai_analysis')
    planet_analysis = session.get('planet_analysis')
    currency = request.args.get('currency', 'USD')
    if not ai_analysis or not planet_analysis:
        return redirect(url_for('index'))

    try:
        ai_data = json.loads(ai_analysis)
        planet_data = json.loads(planet_analysis)
    except json.JSONDecodeError as e:
        return f"JSON decode error: {e}"
    except Exception as e:
        return f"An error occurred: {e}"
    
    title = "Final Summary"
    if request.method == 'POST':
        return redirect(url_for('post_analytics3', currency=currency))
    
    return render_template('analytics3.html', ai_data=ai_data, planet_data=planet_data, title=title, currency=currency)

@app.route('/transition3')
def transition3():
    ai_analysis = session.get('ai_analysis')
    ai_data = json.loads(ai_analysis)
    username = session.get('username')
    netincome = ai_data.get('net_income')
    currency = request.args.get('currency', 'USD')
    original_currency = 'INR' if 'Bank' in ai_data['bank_name'] else 'USD'
    conversion_rate = get_exchange_rate()  # Fetch the current exchange rate

    netincome = convert_currency(netincome, original_currency, currency, conversion_rate)
    dynamic_text = get_dynamic_text2(username, netincome, currency)
    return render_template('transition3.html', ai_analysis=ai_analysis, dynamic_text=dynamic_text, currency=currency)

@app.route('/post_analytics3', methods=['POST'])
def post_analytics3():
    currency = request.args.get('currency', 'USD')
    return redirect(url_for('transition3', currency=currency))

@app.route('/analytics4', methods=['GET', 'POST'])
def analytics4():
    ai_analysis = session.get('ai_analysis')
    planet_analysis = session.get('planet_analysis')
    currency = request.args.get('currency', 'USD')
    if not ai_analysis or not planet_analysis:
        return redirect(url_for('index'))

    try:
        ai_data = json.loads(ai_analysis)
        planet_data = json.loads(planet_analysis)
    except json.JSONDecodeError as e:
        return f"JSON decode error: {e}"
    except Exception as e:
        return f"An error occurred: {e}"
    
    title = "Final Summary"
    kpi_texts = format_kpi_texts(planet_data)
    if request.method == 'POST':
        return redirect(url_for('post_analytics4', currency=currency))
    
    return render_template('analytics4.html', ai_data=ai_data, planet_data=planet_data, kpi_texts=kpi_texts, title=title, currency=currency)

if __name__ == '__main__':
    app.run(debug=True)
