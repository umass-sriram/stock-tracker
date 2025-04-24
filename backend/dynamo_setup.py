import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

TABLE_NAME = "UserPortfolios"

def create_table():
    try:
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "email", "KeyType": "HASH"},   # Partition key
                {"AttributeName": "symbol", "KeyType": "RANGE"},  # Sort key
            ],
            AttributeDefinitions=[
                {"AttributeName": "email", "AttributeType": "S"},
                {"AttributeName": "symbol", "AttributeType": "S"},
            ],
            ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        )
        table.wait_until_exists()
        print(f"✅ Table '{TABLE_NAME}' created and ready.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"⚠️ Table '{TABLE_NAME}' already exists.")
        else:
            raise

def insert_test_data(email, symbol):
    table = dynamodb.Table(TABLE_NAME)
    table.put_item(Item={"email": email, "symbol": symbol})
    print(f"✅ Inserted {symbol} for {email}")

def query_portfolio(email):
    table = dynamodb.Table(TABLE_NAME)
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("email").eq(email)
    )
    items = response.get("Items", [])
    print(f"🧾 Portfolio for {email}: {[item['symbol'] for item in items]}")

if __name__ == "__main__":
    create_table()
    test_email = "user@example.com"
    insert_test_data(test_email, "AAPL")
    insert_test_data(test_email, "TSLA")
    query_portfolio(test_email)
