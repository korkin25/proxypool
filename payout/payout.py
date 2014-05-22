import MySQLdb as mdb
from pyjsonrpc import HttpClient
from urllib2 import HTTPError
from datetime import datetime
from time import time, sleep
from itertools import islice
import json
from sharelogger_plx import ShareLoggerPLX
from threading import Thread
import argparse

# sets how often to run the payouts, in seconds
PAYOUT_INTERVAL = 300 

# Enhanced logging?
verboseLog = False

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


class Share:
    def __init__(self, rowid, user, auxuser, plxuser, vtcpaid, monpaid, plxpaid):
        self.rowid = rowid
        self.user = user
        self.auxuser = auxuser
	self.plxuser = plxuser
        self.vtcpaid = vtcpaid
        self.monpaid = monpaid
	self.plxpaid = plxpaid

def check_numerical(field):
    try:
        float(config[field])
    except ValueError:
        raise ValueError("The field %s: %s does not seem to be a numerical type!" % (field, config[field]))

# sanity checks for configuration file
if config["fee"] > 100 or config["fee"] < 0:
    raise ValueError("The set %s doesn't make any sense." % (config["fee"]))

for field in ["fee", "vtc_min_tx", "mon_min_tx", "minbalance", "redisport"]:
    check_numerical(field)
    if config["vtc_min_tx"] < 0:
        raise ValueError("The field %s: %s doesn't make any sense." % (field, config[field]))

class Wallet:
    def __init__(self, wallet_name, config):
        self.config = config
        self.walletcfg = config["wallets"][wallet_name]
        self.wallet_name = wallet_name
    
    def walletcmd(self, method, *params):
        return HttpClient(**self.walletcfg).call(method, *params)

    def get_balance(self, account=None):
        """returns the current available wallet balance in coins, not satoshis"""
        if account:
            return self.walletcmd("getbalance", account)
        # exclude the fee account balance from the total balance
        return self.walletcmd("getbalance") - self.walletcmd("getbalance", config["feeaccount"])
    
    def sendmany(self, tx_dict):
        """sends coins based on the input list of (address, amount) tuples and 
        returns a transaction hash"""
        if not tx_dict:
            return None
        return self.walletcmd("sendmany", config["account"], tx_dict)
    
    def depositfee(self, amount):
        return self.walletcmd("move", config["account"], config["feeaccount"], amount)
    
    def withdrawfee(self, amount):
        return self.walletcmd("move", config["feeaccount"], config["account"], amount)

def app_log(message):
    line = "%s %s" % (datetime.now(), message)
    print line
    with open("payout.log", "a") as f:
        f.write(line + "\n")
        f.flush()
        
def store_tx(today, txhash, payout_tx, coin):
    if not txhash or not payout_tx: return None
    conn = mdb.connect( 
        config["dbhost"], 
        config["dbuser"], 
        config["dbpass"], 
        config["dbname"]
    )
    
    cursor = conn.cursor()
    cursor.execute("""insert into 
    stats_transactions(date_sent, txhash, amount, coin) values(%s, %s, %s, %s)""",
    (today, txhash, round(sum(payout_tx.values()), 8), coin))

    cursor.execute("select id from stats_transactions where txhash=%s", (txhash,))
    (txid, ) = cursor.fetchone()

    app_log("Saving %s per user transaction information" % coin)
    # log all the individual user payments for statistics
    for user, amount in payout_tx.iteritems():
        cursor.execute("""
        insert into 
        stats_usertransactions(user, tx_id, amount, coin)
        values(%s, %s, %s, %s)
        """, (user, txid, amount, coin))
    
    cursor.execute("select id from stats_transactions where txhash=%s", (txhash,))
    (txid, ) = cursor.fetchone()
    
    conn.commit()
    conn.close()
    
    return txid

def pay_shares():
    """fetches a list of shares and pays as many as the wallet balance will allow"""
    conn = mdb.connect( 
        config["dbhost"], 
        config["dbuser"], 
        config["dbpass"], 
        config["dbname"]
    )

    fee = config["fee"]/100.0
    
    cursor = conn.cursor()
    
    app_log("Fetching shares from database...")
    cursor.execute("""
        select id, user, auxuser, plxuser,
        (case when (monpaid = 0) then monvalue else 0 end), 
        (case when (vtcpaid = 0) then vtcvalue else 0 end),
	(case when (plxpaid = 0) then plxvalue else 0 end)
        from stats_shares
        where vtcpaid = 0 or monpaid = 0 or plxpaid = 0
        order by foundtime desc""")
    rows = cursor.fetchall()
    conn.close()
    if rows is None:
        if verboseLog: app_log("No rows found needing payment")
        return
    
    mon_wallet = Wallet("mon", config) 
    mon_balance = mon_wallet.get_balance() - config["minbalance"]
    vtc_wallet = Wallet("vtc", config)
    vtc_balance = vtc_wallet.get_balance() - config["minbalance"]
    plx_wallet = Wallet("plx", config)
    plx_balance = plx_wallet.get_balance() - config["minbalance"]
    
    app_log("Available balances %.8f MON, %.8f VTC, %.8f PLX" % (mon_balance if mon_balance > 0 else 0,
                                                       vtc_balance if vtc_balance > 0 else 0,
						       plx_balance if plx_balance > 0 else 0))
    app_log("Shares backlog %s" % len(rows))

    total_mon_amount, total_vtc_amount,total_plx_amount = 0, 0, 0
    mon_payout_tx = dict()
    vtc_payout_tx = dict()
    plx_payout_tx = dict()    
    paid_rows = []
    unable_to_pay_vtc = False
    unable_to_pay_mon = False
    unable_to_pay_plx = False
    
    # TODO: at some point most of this needs to be refactored
    # into reusable methods instead of duplicating code for vtc / mon

    for rowid, user, auxuser, plxuser, monvalue, vtcvalue, plxvalue in rows:
        
	# some of this might be redundant, included to ensure the code works with modified mysql tables
	plxuser='none'
	for pairs in config['addresspairs']:
	    if pairs['vtc']==user:
	        plxuser = pairs['plx']
		break
		
	if plxvalue is None:    
	    plxvalue=0.0
	    
	# We don't want to initiate transactions to people with no set PLX address..   
	if plxuser=='none':
	    plxvalue=0.0
		
	if total_mon_amount > mon_balance and total_vtc_amount > vtc_balance and total_plx_amount > plx_balance:
            break

        if unable_to_pay_vtc and unable_to_pay_mon and unable_to_pay_plx:
            break

        monpaid, vtcpaid, plxpaid = False, False, False
        if total_mon_amount <= mon_balance and not unable_to_pay_mon:
            # If we can't afford to pay this user, then don't pay any others (save up)
            if monvalue + total_mon_amount > mon_balance:
                app_log("MON: Unable to pay user {0} due to insufficient funds. VtcValue: {1}, PendingVtc: {2}, Available Balance: {3}".format(auxuser, monvalue, total_mon_amount, mon_balance))
                unable_to_pay_mon = True
            else:
                if auxuser in mon_payout_tx:
                    mon_payout_tx[auxuser] += monvalue
                    total_mon_amount += monvalue
                    monpaid = True
                else:
                    mon_payout_tx[auxuser] = monvalue
                    total_mon_amount += monvalue
                    monpaid = True

        if total_vtc_amount <= vtc_balance and not unable_to_pay_vtc:
            # if we can't afford to pay this user, then don't pay any others (save up)
            if vtcvalue + total_vtc_amount > vtc_balance:
                app_log("VTC: Unable to pay user {0} due to insufficient funds. VtcValue: {1}, PendingVtc: {2}, Available Balance: {3}".format(user, vtcvalue, total_vtc_amount, vtc_balance))
                unable_to_pay_vtc = True
            else:
                if user in vtc_payout_tx:
                    vtc_payout_tx[user] += vtcvalue
                    total_vtc_amount += vtcvalue
                    vtcpaid = True
                else:
                    vtc_payout_tx[user] = vtcvalue
                    total_vtc_amount += vtcvalue
                    vtcpaid = True
		    
        if total_plx_amount <= plx_balance and not unable_to_pay_plx:
            # if we can't afford to pay this user, then don't pay any others (save up)
            if plxvalue + total_plx_amount > plx_balance:
                app_log("PLX: Unable to pay user {0} due to insufficient funds. plxValue: {1}, Pendingplx: {2}, Available Balance: {3}".format(plxuser, plxvalue, total_plx_amount, plx_balance))
                unable_to_pay_plx = True
            else:
                if plxuser in plx_payout_tx:
                    plx_payout_tx[plxuser] += plxvalue
                    total_plx_amount += plxvalue
                    plxpaid = True
                else:
                    plx_payout_tx[plxuser] = plxvalue
                    total_plx_amount += plxvalue
                    plxpaid = True

        if not (monpaid or vtcpaid or plxpaid):
            if verboseLog: app_log("No valid payments found: {0} | {1} | {2} | {3:.8f} | {4:.8f} | {5:.8f}".format(user, auxuser, plxuser, vtcvalue, monvalue, plxvalue))
            continue
        if monpaid:
            if verboseLog: app_log("Adding MON payment for {0} of {1:.8f}".format(auxuser, monvalue))
        if vtcpaid:
            if verboseLog: app_log("Adding VTC payment for {0} of {1:.8f}".format(user, vtcvalue))
        if plxpaid:
            if verboseLog: app_log("Adding PLX payment for {0} of {1:.8f}".format(plxuser, plxvalue))
        
	paid_rows.append(Share(rowid, user, auxuser, plxuser, vtcpaid, monpaid, plxpaid))

    # clean up floating point inaccuracies by rounding to full coin units
    for user in vtc_payout_tx.keys():
        vtc_payout_tx[user] = round(vtc_payout_tx[user], 8)
    for auxuser in mon_payout_tx.keys():
        mon_payout_tx[auxuser] = round(mon_payout_tx[auxuser], 8)
    for plxuser in plx_payout_tx.keys():
        plx_payout_tx[plxuser] = round(plx_payout_tx[plxuser], 8)

    # FIXME: redistribute the coins that were from a users too small payout?
    mon_fee_amount, vtc_fee_amount,plx_fee_amount= 0, 0, 0

    unmark_addresses = dict()
    
    # calculate vtc fees and remove any payouts that are below mintx
    for address in vtc_payout_tx.keys():
        if vtc_payout_tx[address] * (1 - fee) >= config["vtc_min_tx"]:
            this_fee = (vtc_payout_tx[address] * fee)
            vtc_fee_amount += this_fee
            vtc_payout_tx[address] -= this_fee
            vtc_payout_tx[address] = round(vtc_payout_tx[address], 8)
            if verboseLog: app_log("Sending payment to {0} of {1}".format(address, vtc_payout_tx[address]))
        else:
            unmark_addresses[address] = True
            if verboseLog: app_log("Payment to {0} of {1} doesn't meet minimum".format(address, vtc_payout_tx[address]))
            del vtc_payout_tx[address]

    # calculate mon fees and remove any payouts that are below mintx
    for address in mon_payout_tx.keys():
        if mon_payout_tx[address] * (1 - fee) >= config["mon_min_tx"]:
            this_fee = (mon_payout_tx[address] * fee)
            mon_fee_amount += this_fee
            mon_payout_tx[address] -= this_fee
            mon_payout_tx[address] = round(mon_payout_tx[address], 8)
            if verboseLog: app_log("Sending payment to {0} of {1}".format(address, mon_payout_tx[address]))
        else:
            unmark_addresses[address] = True
            if verboseLog: app_log("Payment to {0} of {1} doesn't meet minimum".format(address, mon_payout_tx[address]))
            del mon_payout_tx[address]
    
    # calculate plx fees and remove any payouts that are below mintx
    for address in plx_payout_tx.keys():
        if plx_payout_tx[address] * (1 - fee) >= config["plx_min_tx"]:
            this_fee = (plx_payout_tx[address] * fee)
            plx_fee_amount += this_fee
            plx_payout_tx[address] -= this_fee
            plx_payout_tx[address] = round(plx_payout_tx[address], 8)
            if verboseLog: app_log("Sending payment to {0} of {1}".format(address, plx_payout_tx[address]))
        else:
            unmark_addresses[address] = True
            if verboseLog: app_log("Payment to {0} of {1} doesn't meet minimum".format(address, plx_payout_tx[address]))
            del plx_payout_tx[address]  
	             
    for i in reversed(xrange(len(paid_rows))):
        share = paid_rows[i]
        if share.user in unmark_addresses:
            share.vtcpaid = False
        if share.auxuser in unmark_addresses:
            share.monpaid = False
        if share.plxuser in unmark_addresses:
            share.plxpaid = False	    
        if not (share.vtcpaid or share.monpaid or share.plxpaid):
            del paid_rows[i]
    
    if not vtc_payout_tx and not mon_payout_tx and not plx_payout_tx: 
        app_log("No user has a share balance that meets the minimum transaction requirement.")
        return None, None, None, None, None, None
    
    app_log("Shares queued for payment: %d" % len(paid_rows))
    
    app_log("Fees this run: %.8f MON, %.8f VTC, %.8f PLX" % (mon_fee_amount, vtc_fee_amount, plx_fee_amount))

    if mon_fee_amount > 0:
        if not mon_wallet.depositfee(mon_fee_amount):
            app_log("fee deposit of %.8f MON failed!" % mon_fee_amount)
    
    if vtc_fee_amount > 0:
        if not vtc_wallet.depositfee(vtc_fee_amount):
            app_log("fee deposit of %.8f VTC failed!" % vtc_fee_amount)

    if plx_fee_amount > 0:
        if not plx_wallet.depositfee(plx_fee_amount):
            app_log("fee deposit of %.8f PLX failed!" % plx_fee_amount)
	       
    vtc_fee_balance = vtc_wallet.get_balance(config["feeaccount"])
    if vtc_fee_balance > 10.0:
        if not config["vtcfeeaddress"] in vtc_payout_tx: 
            vtc_payout_tx[config["vtcfeeaddress"]] = vtc_fee_balance
        else:
            vtc_payout_tx[config["vtcfeeaddress"]] += vtc_fee_balance
        
        # for practical reasons tx fees will be paid in the same transactions
        # as user payouts, so make sure we move the required amount from the 
        # fees account to the account used for paying shares
        vtc_wallet.withdrawfee(vtc_fee_balance)
    
    mon_fee_balance = mon_wallet.get_balance(config["feeaccount"])
    if mon_fee_balance > 10.0:
        if not config["monfeeaddress"] in mon_payout_tx: 
            mon_payout_tx[config["monfeeaddress"]] = mon_fee_balance
        else:
            mon_payout_tx[config["monfeeaddress"]] += mon_fee_balance
        
        mon_wallet.withdrawfee(mon_fee_balance)
	
    plx_fee_balance = plx_wallet.get_balance(config["feeaccount"])
    if plx_fee_balance > 50.0:
        if not config["plxfeeaddress"] in plx_payout_tx: 
            plx_payout_tx[config["plxfeeaddress"]] = plx_fee_balance
        else:
            plx_payout_tx[config["plxfeeaddress"]] += plx_fee_balance
        
        plx_wallet.withdrawfee(plx_fee_balance)  
	 
    assert(len(paid_rows) > 0)
    
    vtc_txhash = None
    try:
        vtc_txhash = vtc_wallet.sendmany(vtc_payout_tx,"p2pool")
    except HTTPError as e:
        app_log("vertcoind unknown error during sendmany call!")
        for i in reversed(xrange(len(paid_rows))):
            paid_rows[i].vtcpaid = False
    
    mon_txhash = None
    try:  
        mon_txhash = mon_wallet.sendmany(mon_payout_tx,"")
    except HTTPError as e:
        app_log("monocled unknown error during sendmany call!")
        for i in reversed(xrange(len(paid_rows))):
            paid_rows[i].monpaid = False

    plx_txhash = None
    try:  
        plx_txhash = plx_wallet.sendmany(plx_payout_tx,"")
    except HTTPError as e:
        app_log("parallaxcoind unknown error during sendmany call!")
        for i in reversed(xrange(len(paid_rows))):
            paid_rows[i].plxpaid = False
            if (not paid_rows[i].vtcpaid) and (not paid_rows[i].monpaid):
                del paid_rows[i]

    if (not vtc_txhash) and (not mon_txhash) and (not plx_txhash):
        return None, None, None, None

    today = datetime.utcnow()

    # add the new transactions to the database
    vtc_txid = store_tx(today, vtc_txhash, vtc_payout_tx, "vtc")
    mon_txid = store_tx(today, mon_txhash, mon_payout_tx, "mon")
    plx_txid = store_tx(today, plx_txhash, plx_payout_tx, "plx")
    
    app_log("Marking shares paid...")

    conn = mdb.connect( 
        config["dbhost"], 
        config["dbuser"], 
        config["dbpass"], 
        config["dbname"]
    )
    
    cursor = conn.cursor()
    update_count, deleted_count = 0, 0
    
    for share in paid_rows:
        # both share denominations have been paid during this run
        if share.vtcpaid and share.monpaid and share.plxpaid:
            if deleted_count % 2000 == 0 and deleted_count > 0: 
                conn.commit()
            
            # save paid shares
            cursor.execute("""
                insert into 
                stats_paidshares(foundtime, user, auxuser, 
                                 plxuser,sharediff, 
                                 monvalue, vtcvalue,plxvalue, 
                                 vtcdiff, mondiff,plxdiff, 
                                 vtctx_id, montx_id,plxtx_id) 
                select foundtime, user, auxuser, plxuser, sharediff, 
                monvalue, vtcvalue, plxvalue, vtcdiff, mondiff, plxdiff, 
                %s, %s, %s from stats_shares where id = %s
            """, (vtc_txid, mon_txid, plx_txid, share.rowid))
            
            # remove them from unpaid shares
            cursor.execute("delete from stats_shares where id=%s", (share.rowid,))
            deleted_count += 1

        # only the monocle value has been paid for this share
        elif share.monpaid:
            if update_count % 2000 == 0 and update_count > 0: 
                conn.commit()
            cursor.execute(
                "update stats_shares set monpaid=1 where id=%s", (share.rowid,))
            update_count += 1

        # only the vertcoin value has been paid for this share
        elif share.vtcpaid:
            if update_count % 2000 == 0 and update_count > 0: 
                conn.commit()
            cursor.execute(
                "update stats_shares set vtcpaid=1 where id=%s", (share.rowid,))
            update_count += 1
	    
        # only the parallaxcoin value has been paid for this share
        elif share.plxpaid:
            if update_count % 2000 == 0 and update_count > 0: 
                conn.commit()
            cursor.execute(
                "update stats_shares set plxpaid=1 where id=%s", (share.rowid,))
            update_count += 1
	    
    app_log("Deleted %d paid shares." % deleted_count)
    app_log("Marked %s shares as partially paid." % update_count)
    conn.commit()
    conn.close()
    return vtc_txhash, vtc_payout_tx, mon_txhash, mon_payout_tx, plx_txhash, plx_payout_tx

def run_sharepayout():
    app_log("Payment processing thread started...")
    while True:
        start = time()
        vtc_txhash, vtc_tx, mon_txhash, mon_tx, plx_txhash, plx_tx = pay_shares()
        if (not vtc_txhash or not vtc_tx) and (not mon_txhash or not mon_tx) and (not plx_txhash or not plx_tx):
            app_log("All transactions failed.")
            app_log("Retrying in 5 minutes.")
            sleep(PAYOUT_INTERVAL)
            continue
        if vtc_txhash:
            app_log("Completed vtc transaction %s:" % vtc_txhash)
            for address,amount in vtc_tx.iteritems():
                app_log("%s %.8f VTC" % (address, amount))
        if mon_txhash:
            app_log("Completed mon transaction %s:" % mon_txhash)
            for address,amount in mon_tx.iteritems():
                app_log("%s %.8f MON" % (address, amount))
        if plx_txhash:
            app_log("Completed plx transaction %s:" % plx_txhash)
            for address,amount in plx_tx.iteritems():
                app_log("%s %.8f PLX" % (address, amount))		
        app_log("Parsed and sent in %.4f seconds. Next run in 5 minutes." % (time() - start))
        sleep(PAYOUT_INTERVAL)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="processing and payout of shares")
    parser.add_argument(
        '--debug',
        help='enable debugging (print out of sharelogging)',
        action='store_const', const=True, default=False, dest='debug')
    args = parser.parse_args()

    logger = ShareLogger(config, debug=args.debug)
    t = Thread(target=run_sharepayout)
    try:
        logger.daemon = True
        t.daemon = True
        logger.start()
        t.start()
        while logger.is_alive() and t.is_alive():
            logger.join(1)
            t.join(1)
    except KeyboardInterrupt:
        print "Shutting down.."
        exit(0)
