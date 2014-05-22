import MySQLdb as mdb
import json
from datetime import datetime
from time import time, sleep

# THIS SCRIPT WILL UPDATE ALL OLD SHARES OF A USER WITH THE DESIRED PLX ADDRESS

USER_ADDRESS='VTC ADDRESS FROM DATABASE'
PLX_ADDRESS='PLX ADDRESS TO ADD'

try:
    with open("sharelogger.conf", "r") as f:
        config = json.loads(f.read())
except IOError:
    print "Config Error: file '%s' was not found in the given path!" % config
    exit(1)
except ValueError as e:
    print "Config error: %s" % e
    print "Make sure you didn't miss a comma, added an extra comma or quote/doublequote somewhere"
    exit(1)
    
def app_log(message):
    line = "%s %s" % (datetime.now(), message)
    print line
    with open("plx_addressfix.log", "a") as f:
        f.write(line + "\n")
        f.flush()    
    
class Share:
    def __init__(self, rowid, user, plxuser):
        self.rowid = rowid
        self.user = user
        self.plxuser = plxuser

def update_shares():
    """fetches a list of shares and pays as many as the wallet balance will allow"""
    conn = mdb.connect( 
        config["dbhost"], 
        config["dbuser"], 
        config["dbpass"], 
        config["dbname"]
    )
    
    cursor = conn.cursor()
    
    app_log("Fetching shares from database...")
    cursor.execute("select id, user, plxpaid, plxuser from stats_shares where user=%s order by foundtime asc" ,USER_ADDRESS)
    rows = cursor.fetchall()
    #conn.close()
    if rows is None: return
    
    paid_rows = []

    for rowid, user, plxpaid, plxuser in rows:
	app_log("Updating rowid= %i, user=%s with plxuser =%s" % (rowid,user,PLX_ADDRESS))
        paid_rows.append(Share(rowid, user, PLX_ADDRESS))

    update_count = 0
     
    for share in paid_rows:
        cursor.execute("update stats_shares set plxuser=%s where id=%s", (share.plxuser,share.rowid,))
	update_count += 1

    app_log("Updated %s entries with plx addresses." % update_count)
    conn.commit() 
    conn.close()
    
update_shares()
