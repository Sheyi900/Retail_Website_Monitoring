from __future__ import print_function
import pymysql
import json
from datetime import datetime
import boto3

region_name = "ap-south-1"
secret_name = "aurora_secret"
session = boto3.session.Session()
client = session.client(service_name='secretsmanager',region_name=region_name)
try:
    get_secret_value_response = client.get_secret_value(SecretId=secret_name)
except ClientError as e:
    print(e)
if 'SecretString' in get_secret_value_response:
    secret_str = get_secret_value_response['SecretString']
else:
    secret_str = base64.b64decode(get_secret_value_response['SecretBinary'])
secret = json.loads(secret_str)
hostname = str(secret["host"])
username = str(secret["username"])
pwd = str(secret["password"])
        
#lambda trigger event to post to SNS and Aurora MySQL
def lambda_handler(event, context):
    print(event)
    try:
      
        #Create SNS client using the topic arn 
        client = boto3.client('sns')
        topic_arn = 'arn:aws:sns:ap-south-1:338401225294:website-alarm'
        
        out=client.publish(TopicArn=topic_arn, 
        Message='Investigate sudden surge in orders. Order Count: {} @ {}'.format(event['order_count'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        Subject='Mywebsite Order Rate Alarm')
        
        print(out)
        
        #Connect to Aurora Mysql to write alarm data
        conn = pymysql.connect(host=hostname,db="logs",user=username, password=pwd, connect_timeout=10)
        with conn.cursor() as cur:
            cur.execute('insert into logs.logs_history values("{}",{})'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'),event["order_count"]))
        conn.commit()

        print('Successfully delivered alarm message')
    except Exception:
        print("Either Aurora insert or SNS notification failed")
