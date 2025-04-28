from flask import Flask, request, jsonify
from jose import jwt
import requests
from flask_cors import CORS
import os
import datetime as dt
from dateutil.relativedelta import relativedelta
import boto3
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
portfolio_table = dynamodb.Table('UserPortfolios')

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Constants
COGNITO_REGION = "us-east-1"
USER_POOL_ID = "us-east-1_zxEXADgC5"
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"
JWKS = requests.get(JWKS_URL).json()

TWELVE_DATA_API_KEY = "982cdd7dc9c14e8eaf1f9c61c22cf1f0"
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

# Token verification
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

# New function to get stock prices from Twelve Data
def fetch_latest_prices(symbols):
    prices = {}
    for symbol in symbols:
        params = {
            "symbol": symbol,
            "apikey": TWELVE_DATA_API_KEY
        }
        response = requests.get(f"{TWELVE_DATA_BASE_URL}/price", params=params)
        if response.status_code == 200:
            data = response.json()
            if 'price' in data:
                prices[symbol] = round(float(data['price']), 2)
            else:
                print(f"No price found for {symbol}: {data}")
        else:
            print(f"Failed to fetch price for {symbol}: {response.text}")
    return prices

@app.route("/api/stocks", methods=["GET"])
def get_stocks():
    try:
        print("Fetching stocks...")
        verify_token(request)

        symbols = ["AAPL", "GOOGL", "TSLA", "MSFT", "AMZN", "NVDA"]
        result = fetch_latest_prices(symbols)

        if not result:
            return jsonify({"error": "No stock data found"}), 404

        return jsonify(result)

    except Exception as e:
        print("Error in get_stocks:", str(e))
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401

@app.route("/api/searchstock", methods=["GET"])
def search_stock():
    symbol = request.args.get("symbol", "").upper()
    print("Searching stock:", symbol)
    try:
        verify_token(request)
        price_info = fetch_latest_prices([symbol])
        if symbol not in price_info:
            return jsonify({"error": "Symbol not found"}), 404

        # Dummy percent change since Twelve Data free plan doesn't give previous close easily
        return jsonify({"symbol": symbol, "price": price_info[symbol], "change": 0.0})

    except Exception as e:
        print(str(e))
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401

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

        response = portfolio_table.query(
            KeyConditionExpression=Key("email").eq(user_email)
        )
        symbols = [item["symbol"] for item in response.get("Items", [])]
        return jsonify(symbols)

    except Exception as e:
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
