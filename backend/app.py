from flask import Flask, request, jsonify
from jose import jwt
import requests
from flask_cors import CORS
import os
from polygon import RESTClient
from datetime import datetime, timedelta
import time
import yfinance as yf
import boto3
import json
from boto3.dynamodb.conditions import Key

# Initialize
dynamodb = boto3.resource('dynamodb')
portfolio_table = dynamodb.Table('UserPortfolios')

app = Flask(__name__)
CORS(app)

COGNITO_REGION = "us-east-1"
USER_POOL_ID = "us-east-1_zxEXADgC5"
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"
JWKS = requests.get(JWKS_URL).json()

# Initialize SSM client
ssm_client = boto3.client('ssm', region_name="us-east-1")  # Set correct region

def get_symbols_from_ssm():
    response = ssm_client.get_parameter(Name='/stocktracker/symbols')
    symbols_string = response['Parameter']['Value']
    symbols_list = [s.strip() for s in symbols_string.split(',')]
    return symbols_list
    
def get_secret(secret_name):
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name='us-east-1')

    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret = response['SecretString']
        return json.loads(secret)
    except Exception as e:
        print(f"Error fetching secret {secret_name}: {e}")
        raise e

secrets = get_secret("stock-tracker/polygon-api-key")
TIINGO_API_KEY = secrets["TIINGO_API_KEY"]

def get_public_key(token):
    headers = jwt.get_unverified_header(token)
    kid = headers["kid"]
    for key in JWKS["keys"]:
        if key["kid"] == kid:
            return key
    raise Exception("Public key not found.")

def verify_token(request):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")
    key = get_public_key(token)
    decoded = jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience="411p65nnq24h8oerja7ncmuphs",
        issuer=COGNITO_ISSUER,
        options={"verify_at_hash": False}
    )
    return decoded

@app.route('/health', methods=['GET'])
def health_check():
    return {'status': 'ok'}, 200

@app.route("/api/stocks", methods=["GET"])
def get_stocks():
    try:
        print("Fetching stocks...")
        verify_token(request)

        symbols = get_symbols_from_ssm()
        print(f"symbols {symbols}")

        result = {}
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=5)

        headers = {"Content-Type": "application/json"}

        for symbol in symbols:
            try:
                url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
                params = {
                    "token": TIINGO_API_KEY,
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "resampleFreq": "daily"
                }

                response = requests.get(url, headers=headers, params=params)
                if response.status_code != 200:
                    print(f"Tiingo error for {symbol}: {response.text}")
                    continue

                data = response.json()
                if isinstance(data, list) and data:
                    close_price = round(data[-1]["close"], 2)
                    result[symbol] = close_price
                else:
                    print(f"No data found for {symbol}")

            except Exception as inner_e:
                print(f"Error fetching data for {symbol}: {inner_e}")

        if not result:
            return jsonify({"error": "No stock data found"}), 404

        return jsonify(result)

    except Exception as e:
        print("Error in get_stocks:", str(e))
        return jsonify({"error": "Error in get_stocks:", "message": str(e)}), 401

@app.route("/api/searchstock", methods=["GET"])
def search_stock():
    symbol = request.args.get("symbol", "").upper()
    print("Searching stock:", symbol)
    try:
        verify_token(request)

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=5)

        url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
        headers = { "Content-Type": "application/json" }
        params = {
            "token": TIINGO_API_KEY,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "resampleFreq": "daily"
        }

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print("Tiingo API Error:", response.text)
            return jsonify({"error": "Failed to retrieve data"}), 500

        data = response.json()
        if not isinstance(data, list) or not data:
            return jsonify({"error": "Symbol not found"}), 404

        last_close = data[-1]["close"]
        prev_close = data[0]["close"]
        change = round(((last_close - prev_close) / prev_close) * 100, 2)

        return jsonify({
            "symbol": symbol,
            "price": round(last_close, 2),
            "change": change
        })

    except Exception as e:
        print("Error in search_stock:", str(e))
        return jsonify({"error": "Error in search_stock", "message": str(e)}), 401


@app.route("/api/stocks/history")
def get_price_history():
    symbol = request.args.get("symbol", "").upper()
    try:
        verify_token(request)

        headers = {
            "Content-Type": "application/json"
        }
        url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
        params = {
            "token": TIINGO_API_KEY,
            "startDate": "2024-12-01",
            "resampleFreq": "daily"
        }

        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        if not isinstance(data, list) or not data:
            return jsonify({"error": "No data returned or symbol not found"}), 404

        history = [
            {"date": item["date"][:10], "price": round(item["close"], 2)}
            for item in data
        ]
        return jsonify(history)

    except Exception as e:
        print("Error in get_price_history:", str(e))
        return jsonify({"error": "Error in get_price_history:", "message": str(e)}), 401


@app.route("/api/portfolio", methods=["GET", "POST"])
def portfolio():
    try:
        decoded = verify_token(request)
        user_email = decoded["email"]

        if request.method == "POST":
            symbol = request.json.get("symbol", "").upper()
            if not symbol:
                return jsonify({"error": "Invalid symbol"}), 400

            portfolio_table.put_item(Item={"email": user_email, "symbol": symbol})
            return jsonify({"message": f"{symbol} added to portfolio"})

        # GET method
        response = portfolio_table.query(
            KeyConditionExpression=Key("email").eq(user_email)
        )
        symbols = [item["symbol"] for item in response.get("Items", [])]
        return jsonify(symbols)

    except Exception as e:
        print("Error in portfolio:", str(e))
        return jsonify({"error": "Error in portfolio:", "message": str(e)}), 401

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
