from fastapi import FastAPI
import psycopg2 as pg
from datetime import datetime
import requests
import json

app = FastAPI()

@app.get("/")
def root():
    return {"Server": "Ready"}

def db_connection(func):
    def with_connection(*args, **kwargs):
        settings = {}
        with open('settings.json') as json:
            settings = json.load(json)

        conn = pg.connect(
            host=f"{settings['host']}",
            dbname=f"{settings['dbname']}",
            user=f"{settings['user']}",
            password=f"{settings['password']}",
        )
        cur = conn.cursor()

        try:
            ret_func = func(*args, cursor=cur, **kwargs)
        except Exception:
            conn.rollback()
            print("Database Error")
            raise
        else:
            conn.commit()
        finally:
            cur.close()
            conn.close()

        return ret_func

    return with_connection

def api_get(url):
    headers = {'User-Agent': 'data_analysis_project-Chaotic#1161',}
    response = requests.get(f"https://prices.runescape.wiki/api/v1/osrs/{url}", headers=headers)
    return json.loads(response.text)

@db_connection
def update_mapping(**kwargs):
    result = api_get("mapping")
    rows = []
    errors = [] # Connect this to logging after filling

    for x in result: # Item Id, Members?, Trade limit, High Alch, Name
        try:
            rows.append((x["id"], x["members"], str(x["limit"]), x["highalch"], x["name"]))
        except KeyError:
            pass
        try:
            rows.append((x["id"], x["members"], "Unknown", x["highalch"], x["name"]))
        except KeyError:
            pass
        try:
            rows.append((x["id"], x["members"], str(x["limit"]), "None", x["name"]))
        except KeyError:
            pass
        try:
            rows.append((x["id"], x["members"], "Unknown", "None", x["name"]))
        except KeyError:
            error = (x["id"], x["name"])
            errors.append(error)

    cur = kwargs.pop("cursor")
    cur.execute("TRUNCATE TABLE mapping;") # Can/should be refactored to check for new information instead of clearing

    # Remove bad data from known ids
    settings = {}
    with open('settings.json') as json:
        settings = json.load(json)

    for row in range(rows, 0, -1): # Iterate backwards so deleting doesnt desync whole list
        if rows[row][0] in settings["dirty_ids"]:
            del rows[row]

    arguments = ','.join(cur.mogrify("%s,%s,%s,%s,%s)", x).decode('utf-8') for x in rows)

def get_item_thumbnails():
    # https://static.runelite.net/cache/item/icon/{item_id}.png er et nemt sted at snuppe ikoner fra
    # gem dem i seperat db table (lav ny metode til at tjekke efter nye entries og kald den)
    pass

@db_connection
def store_5min(**kwargs):
    result = api_get("5m")

    timestamp = result["timestamp"]
    timestamp = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    items = result["data"]

    cur = kwargs.pop("cursor")

    # store data