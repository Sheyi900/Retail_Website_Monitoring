import json
import base64
import boto3
import pymysql
from datetime import datetime, timedelta
import decimal
import os

REGION = "us-east-1"
HOST = "web-alerts-instance-1.cf86mawyg7zw.us-east-2.rds.amazonaws.com"
USER = "admin"
PASSWORD = os.environ['RDS_PASSWORD']
DB_NAME = "website-monitoring-records"
SNS_TOPIC_ARN = "arn:aws:sns:us-east-2:598396538898:website-monitoring-alert"


sns_client = boto3.client('sns', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table('website-monitoring-records')


conn = pymysql.connect(host=HOST, user=USER, passwd=PASSWORD, db=DB_NAME, connect_timeout=5)

def check_invoice_frequency(customer_id, current_time):
    twenty_seconds_ago = current_time - timedelta(seconds=20)
    response = table.scan(
        FilterExpression="CustomerID = :cid and OrderDate >= :ts",
        ExpressionAttributeValues={
            ":cid": decimal.Decimal(customer_id),
            ":ts": twenty_seconds_ago.isoformat()
        }
    )
    unique_invoices = {item['OrderID'].split("-")[0] for item in response['Items']}
    return len(unique_invoices)

def check_last_alert_time(customer_id):
    five_minutes_ago = datetime.now() - timedelta(minutes=2)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM logs_history WHERE CustomerID = %s AND alarm_creation_time >= %s", (customer_id, five_minutes_ago.strftime('%Y-%m-%d %H:%M:%S')))
        result = cur.fetchone()
        if result and result[0] > 0:
            return True
        else:
            return False
def lambda_handler(event, context):
    output = []
    current_time = datetime.now()
    for record in event['records']:
        decoded_data = base64.b64decode(record['data']).decode('utf-8')
        payload = json.loads(decoded_data)
        print(payload)
        

        item = {
            'CustomerID': decimal.Decimal(payload['Customer']),
            'OrderID': payload['InvoiceNo'] + "-" + payload['StockCode'],
            'OrderDate': current_time.isoformat(),
            'Quantity': decimal.Decimal(payload['Quantity']),
            'UnitPrice': decimal.Decimal(payload['UnitPrice']),
            'Description': payload['Description'],
            'Country': payload['Country'].rstrip()
        }
        table.put_item(Item=item)
        print(f"Inserted into DynamoDB: {item}")

        # Check for unique invoices in the last 20 seconds
        num_unique_invoices = check_invoice_frequency(payload['Customer'], current_time)
        if num_unique_invoices > 5 and not check_last_alert_time(payload['Customer']):
            message = f"High invoice frequency detected for Customer {payload['Customer']}. Number of unique invoices: {num_unique_invoices}"
            sns_client.publish(TopicArn=SNS_TOPIC_ARN, Message=message, Subject='High Invoice Alert')
            print(f"SNS Notification sent: {message}")

            with conn.cursor() as cur:
                cur.execute('INSERT INTO logs_history (alarm_creation_time, CustomerID, Number_of_invoice) VALUES (%s, %s, %s)', 
                            (current_time.strftime('%Y-%m-%d %H:%M:%S'), payload['Customer'], num_unique_invoices))
                conn.commit()
                print("Inserted into Aurora MySQL")

        output_record = {
            'recordId': record['recordId'],
            'result': 'Ok',
            'data': record['data']  
        }
        output.append(output_record)

    return {'records': output}
