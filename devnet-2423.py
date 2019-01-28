# -*- coding: utf-8 -*-
print """
 _____    _             _   _                  _    ____ ___
|_   _|__| |_ _ __ __ _| |_(_) ___  _ __      / \  |  _ \_ _|
  | |/ _ \ __| '__/ _` | __| |/ _ \| '_ \    / _ \ | |_) | |
  | |  __/ |_| | | (_| | |_| | (_) | | | |  / ___ \|  __/| |
  |_|\___|\__|_|  \__,_|\__|_|\___/|_| |_| /_/   \_\_|  |___|

  ===========================================================
 ____  _______     ___   _ _____ _____   ____  _  _  ____  _____
|  _ \| ____\ \   / / \ | | ____|_   _| |___ \| || ||___ \|___ /
| | | |  _|  \ \ / /|  \| |  _|   | |     __) | || |_ __) | |_ \\
| |_| | |___  \ V / | |\  | |___  | |    / __/|__   _/ __/ ___) |
|____/|_____|  \_/  |_| \_|_____| |_|   |_____|  |_||_____|____/

Tim Garner <tigarner@cisco.com>
Remi Philippe <rephilip@cisco.com>

https://github.com/tetration-exchange/devnet-2423-2019/
"""

import json
import os, sys
import time
from tetpyclient import RestClient
from requests.packages.urllib3 import disable_warnings

API_ENDPOINT = "https://vesx-2.insbu.net"
CRED_FILE = "./api_credentials.json"
APP_ID = "5c4a5bf4755f02642425eee6"
FILTER_ID = "5c4a5c30755f02642425eeee"


# Might be useful to connect somewhere, we'll put all the connect logic here
def connect():
    # Check credentials file exists
    if os.path.exists(CRED_FILE) == False:
        sys.exit("Error! Credentials file is not present")
    disable_warnings()

    # Class Constructor
    rc = RestClient(API_ENDPOINT, credentials_file=CRED_FILE, verify=False)
    return rc


# I hate implementing try catch everywhere, will create a wrapper function
# this function only implements some basic verifications
def query(method, endpoint, payload=""):
    try:
        if method == "POST":
            resp = rc.post(endpoint, json_body=json.dumps(payload))
        elif method == "GET":
            resp = rc.get(endpoint)

        if resp.status_code != 200:
            raise Exception("Status Code - " + str(resp.status_code) +
                            "\nError - " + resp.text + "\n")
    except Exception as e:
        print e
        #sys.exit(1)

    if resp.status_code == 200:
        try:
            return resp.json()
        except ValueError:
            return True


def get_sensors():
    sensors = {}
    # DEVNET Code Start, tag=sensors
    all_sensors = query("GET", "/sensors")
    for s in all_sensors['results']:
        # I don't care about the Tetration hosts for now, let's ignore them
        if not any(d.get('vrf', None) == 'Tetration' for d in s['interfaces']):
            interfaces = filter(
                lambda i: i['family_type'] == 'IPV4' and i['ip'] != '127.0.0.1',
                s['interfaces'])
            sensors[s['uuid']] = {
                "hostname": s['host_name'],
                "uuid": s['uuid'],
                "interfaces": list(map(lambda x: {"ip": x['ip'], "type": x['family_type'], "vrf": x['vrf'], "mac": x['mac']}, interfaces)),
                "inactive": int(time.time()) - s['last_config_fetch_at'] > 1805
            }
    # DEVNET Code End
    return sensors


def get_filter_members(filter_id):
    filter_query = query("GET", "/filters/inventories/" + filter_id)
    filter_members = query(
        "POST", "/inventory/search", payload={'filter': filter_query['query']})
    results = {
        "name":
        filter_query['name'],
        "results":
        filter(lambda f: f["address_type"] == "IPV4",
               filter_members["results"])
    }
    return results


def get_application(app_id):
    retval = {}
    # DEVNET Code Start, tag=application
    # let's get the app details...
    details = query("GET", "/applications/" + app_id + "/details")

    # ...and the scope details...
    scope = query("GET", "/app_scopes/" + details['app_scope_id'])

    # what are my external dependencies?
    d = details.get('inventory_filters')
    if d == None:
        d = []
    # this can also be written as details.get('inventory_filters', [])

    # who is part of my application?
    c = details.get('clusters')
    if c == None:
        c = []
    # this can also be written as details.get('clusters', [])

    # make it pretty!
    retval = {
        "scope": {k: v for k, v in scope.iteritems() if k == "id" or k == "name" or k == "parent_app_scope_id"},
        "name": details['name'],
        "id": app_id,
        "external": list(map(lambda x: {"id": x['id'], "name": x['name']}, d)),
        "clusters": list(map(lambda x: {"id": x['id'], "name": x['name'], "external": x['external'], "nodes": x['nodes']}, c)),
        "policies": details['default_policies']
    }
    # DEVNET Code End
    return retval


def mark_as_inactive(ip):
    query(
        "POST",
        "/inventory/tags/Default",
        payload={
            "ip": ip,
            "attributes": {
                "inactive": "true"
            }
        })


def get_inactive_sensors(sensors):
    return filter(lambda s: s['inactive'], sensors.values())


# establish a global connection
rc = connect()

# step 1 - get the sensor details
sensors = get_sensors()
print "All sensors: "
for sensor in sensors.values():
    print " ", sensor["hostname"]

# step 2 - loop through the sensors that are inactive and mark
# each interface address as inactive
sensors = get_inactive_sensors(sensors)
print "\nInactive sensors: "
for sensor in sensors:
    print " ", sensor["hostname"]
    for interface in sensor["interfaces"]:
        print "   marking interface inactive: {: <16} ✅".format(
            interface['ip'])
        mark_as_inactive(interface["ip"])

# step 3 - get the application policy
app = get_application(APP_ID)

# step 4 - loop through the application policy entries
print "\n\nThe application", app['name'], "has the following policies:"
for policy in app['policies']:
    print "{:5}  {:20} --> {:15}".format(policy['action'], policy['consumer_filter_name'], policy[ 'provider_filter_name'])

# step 5 - get the ips that match the filter (policy entry) "Inactive Sensors"
filter_members = get_filter_members(FILTER_ID)

