from flask import Flask, request, jsonify
from jose import jwt
import requests
from flask_cors import CORS
import os
from polygon import RESTClient
from datetime import datetime, timedelta
import boto3
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

POLYGON_API_KEY = "c_Nc9wSU9dr4DshD0xegTNpliM4y7L1c"
polygon_client = RESTClient(POLYGON_API_KEY)
POLYGON_BASE_URL = "https://api.polygon.io"

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

        symbols = ["AAPL", "GOOGL", "TSLA", "MSFT", "AMZN", "NVDA"]

        result = {}

        for symbol in symbols:
            try:
                # Fetch the previous close
                previous_closes = list(polygon_client.list_aggs(
                    ticker=symbol,
                    multiplier=1,
                    timespan="day",
                    from_="2024-04-26",  # you can dynamically calculate "yesterday" if needed
                    to="2024-04-26",
                    limit=1
                ))

                if previous_closes:
                    close_price = previous_closes[0].close
                    result[symbol] = round(close_price, 2)
                else:
                    print(f"No data found for {symbol}")

            except Exception as inner_e:
                print(f"Error fetching data for {symbol}: {inner_e}")

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
        
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=5)
        
        url = f"{POLYGON_BASE_URL}/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}?limit=5&apiKey={POLYGON_API_KEY}"
        response = requests.get(url)
        data = response.json()

        if response.status_code != 200 or "results" not in data:
            print(f"Polygon error: {data}")
            return jsonify({"error": "Symbol not found"}), 404

        last_price = data["results"][-1]["c"]
        return jsonify({"symbol": symbol, "price": round(last_price, 2)})

    except Exception as e:
        print("Error in search_stock:", str(e))
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401

@app.route("/api/stocks/history", methods=["GET"])
def get_price_history():
    symbol = request.args.get("symbol", "").upper()
    try:
        verify_token(request)

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)

        url = f"{POLYGON_BASE_URL}/v2/aggs/ticker/{symbol}/range/1/day/{start_date}/{end_date}?limit=30&apiKey={POLYGON_API_KEY}"

        # Retry logic with exponential backoff
        for attempt in range(5):
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if "results" in data and data["results"]:
                    history = [
                        {
                            "date": datetime.utcfromtimestamp(item["t"] / 1000).strftime("%Y-%m-%d"),
                            "price": round(item["c"], 2)
                        }
                        for item in data["results"]
                    ]
                    return jsonify(history)
                else:
                    return jsonify({"error": "Symbol not found"}), 404
            elif response.status_code == 429:
                wait = 2 ** attempt
                print(f"Rate limited. Retrying in {wait} seconds...")
                time.sleep(wait)
            else:
                break

        return jsonify({"error": "Failed to fetch price history", "details": response.text}), 500

    except Exception as e:
        print("Error in get_price_history:", str(e))
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

        # GET method
        response = portfolio_table.query(
            KeyConditionExpression=Key("email").eq(user_email)
        )
        symbols = [item["symbol"] for item in response.get("Items", [])]
        return jsonify(symbols)

    except Exception as e:
        print("Error in portfolio:", str(e))
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
