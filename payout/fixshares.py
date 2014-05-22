import MySQLdb as mdb
import json
from datetime import datetime
from time import time, sleep

# THIS SCRIPT CAN BE USED TO UPDATE THE DATABASE, ADDING THE 
# TOTAL_PAID_SHAREVALUE TO THE OLD UNPAID SHARES OF A USER

TOTAL_PAID_SHAREVALUE=0.10910962
USER_ADDRESS='ADDRESS FROM DATABASE'

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
    with open("payoutfix.log", "a") as f:
        f.write(line + "\n")
        f.flush()    
    
class Share:
    def __init__(self, rowid, user, vtcpaid):
        self.rowid = rowid
        self.user = user
        self.vtcpaid = vtcpaid

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
    cursor.execute("select id, user, vtcvalue from stats_shares where user=%s AND vtcpaid=0 AND DATE(foundtime) < '2014-05-09' order by foundtime asc" ,USER_ADDRESS)
    rows = cursor.fetchall()
    #conn.close()
    if rows is None: return
    
    paid_rows = []
    total_vtc_amount = 0
    print "SUM TO MARK AS PAID: %f" % TOTAL_PAID_SHAREVALUE
    for rowid, user, vtcvalue in rows:
       	vtcpaid = False
        total_vtc_amount += vtcvalue
        if total_vtc_amount <= TOTAL_PAID_SHAREVALUE:
            if user in USER_ADDRESS:          	  
                  vtcpaid = True

        if not (vtcpaid): continue
	
	app_log("Marking rowid= %i, user=%s vtcvalue =%f as paid" % (rowid,user,vtcvalue))
        paid_rows.append(Share(rowid, user, vtcpaid))

    update_count = 0
     
    for share in paid_rows:
        cursor.execute("update stats_shares set vtcpaid=1 where id=%s", (share.rowid,))
        update_count += 1

    app_log("Marked %s shares with total value %f as partially paid." % TOTAL_PAID_SHAREVALUE, update_count)
    conn.commit()
    conn.close()
    
update_shares()
