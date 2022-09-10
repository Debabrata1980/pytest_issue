#!/usr/bin/python3.6
import urllib3
import json
http = urllib3.PoolManager()


def lambda_handler(event, context):
    url = "https://hp.webhook.office.com/webhookb2/8321c250-a240-4984-9f22-2544d5c515d0@ca7981a2-785a-463d-b82a-3db87dfc3ce6/IncomingWebhook/130e40700f5b477593761e250bb7edff/069b3fb9-b989-42bd-90a6-3bf5b05ec565"
    msg = {
        "text": event['Records'][0]['Sns']['Message']
    }
    encoded_msg = json.dumps(msg).encode('utf-8')
    resp = http.request('POST', url, body=encoded_msg)
    print({
        "message": event['Records'][0]['Sns']['Message'],
        "status_code": resp.status,
        "response": resp.data
    })
