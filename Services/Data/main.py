from fastapi import FastAPI
import psycopg2 as pg
from datetime import datetime
import requests
import json
from pathlib import Path

#app = FastAPI()

#@app.get("/")
#def root():
#    return {"Server": "Ready"}

def db_connection(func):
    def with_connection(*args, **kwargs):
        settings = {}
        with open("Services\Data\settings.json", "r") as f:
            settings = json.load(f)

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

def get_api_response(url):
    headers = {'User-Agent': 'data_analysis_project-Chaotic#1161',}
    response = requests.get(f"https://prices.runescape.wiki/api/v1/osrs/{url}", headers=headers)
    return json.loads(response.text)

def get_mapping():
    result = get_api_response("mapping")
    items = []
    errors = []

    for item in result: # Item Id, Members?, Trade limit, High Alch, Name
        if not "limit" in item:
            item["limit"] = 0
        if not "highalch" in item:
            item["highalch"] = 0

        try:
            items.append((item["id"], item["members"], item["limit"], item["highalch"], item["name"]))
        except KeyError:
            error = (item["id"], item["name"])
            errors.append(error)

    # Remove bad data from known ids
    settings = {}
    with open("Services\Data\settings.json") as f:
        settings = json.load(f)

    for item in range(len(items), 0, -1): # Iterate backwards so deleting doesnt desync whole list
        if items[item-1][0] in settings["dirty_ids"]:
            del items[item]

    # Add logging that dumps the errors list to aggregator

    return items

@db_connection
def update_mapping(**kwargs):
    items = get_mapping()
    cur = kwargs.pop("cursor")

    # Creates string of all values to be inserted from list of tuples,
    values_string = ",".join(cur.mogrify("(%s, %s, %s, %s, %s)", x).decode("utf-8") for x in items)

    cur.execute("INSERT INTO mapping (ItemId, Members, Limit, HighAlch, Name) VALUES " + values_string)

def get_item_thumbnail(item_id): # Consider switching to just referencing the runelite host instead of selfhosting it, mostly did it for stability
    dir_path = Path(__file__).parents[0]
    img_path = dir_path / "Thumbnails" / f"{str(item_id)}.png"

    if not Path.exists(img_path):
        url = f"https://static.runelite.net/cache/item/icon/{item_id}.png"
        response = requests.get(url)
        
        if response.status_code == 200:
            with open(img_path, "wb") as f:
                f.write(response.content)

        return img_path

    return img_path

@db_connection
def store_5min(**kwargs):
    result = get_api_response("5m")

    # Convert timestamp to usable format
    timestamp = result["timestamp"]
    timestamp = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    
    items = result["data"]

    cur = kwargs.pop("cursor")

    # store data