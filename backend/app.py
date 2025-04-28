from flask import Flask, request, jsonify
from jose import jwt
import requests
from flask_cors import CORS
import datetime as dt
from dateutil.relativedelta import relativedelta
import yfinance as yf
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
portfolio_table = dynamodb.Table('UserPortfolios')

app = Flask(__name__)
CORS(app)

end = dt.datetime.now()
start = end - relativedelta(months=3)

COGNITO_REGION = "us-east-1"
USER_POOL_ID = "us-east-1_zxEXADgC5"
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"
JWKS = requests.get(JWKS_URL).json()

PORTFOLIOS = {}


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
    
@app.route("/api/stocks")
def get_stocks():
    try:
        print("get_stocks")
        verify_token(request)
        symbols = ["AAPL", "GOOGL", "TSLA", "MSFT", "AMZN", "NVDA"]
        #data = yf.download(tickers=" ".join(symbols), interval='1wk', end=end, start=start)
        data = yf.download(tickers=" ".join(symbols), period="1d", interval="1h", group_by='ticker')
        result = {}
        for symbol in symbols:
            if symbol in data:
                latest = data[symbol]['Close'].dropna().iloc[-1]
                result[symbol] = round(latest, 2)
        return jsonify(result)
    except Exception as e:
        print(str(e))
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401

@app.route("/api/searchstock", methods=["GET"])
def search_stock():
    symbol = request.args.get("symbol", "").upper()
    print("symbol",symbol)
    try:
        verify_token(request)
        stock = yf.Ticker(symbol)
        info = stock.history(period="1d", interval="1m")
        if info.empty:
            return jsonify({"error": "Symbol not found"}), 404
        current_price = round(info['Close'].dropna().iloc[-1], 2)
        prev_close = round(stock.history(period="2d")['Close'].iloc[0], 2)
        change = round(((current_price - prev_close) / prev_close) * 100, 2)
        return jsonify({"symbol": symbol, "price": current_price, "change": change})
    except Exception as e:
        print(str(e))
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401

@app.route("/api/stocks/history")
def get_price_history():
    symbol = request.args.get("symbol", "").upper()
    try:
        verify_token(request)
        stock = yf.Ticker(symbol)
        hist = stock.history(period="1mo")
        if hist.empty:
            return jsonify({"error": "Symbol not found"}), 404
        history = [
            {"date": idx.strftime("%Y-%m-%d"), "price": round(row["Close"], 2)}
            for idx, row in hist.iterrows()
        ]
        return jsonify(history)
    except Exception as e:
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
        return jsonify({"error": "Unauthorized", "message": str(e)}), 401


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
