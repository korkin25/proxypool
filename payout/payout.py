import MySQLdb as mdb
from pyjsonrpc import HttpClient
from datetime import datetime
from time import time, sleep
from itertools import islice
import json
from sharelogger import ShareLogger
from threading import Thread
import argparse

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
        select id, user, auxuser, 
        (case when (monpaid = 0) then monvalue else 0 end), 
        (case when (vtcpaid = 0) then vtcvalue else 0 end)
        from stats_shares order by foundtime desc""")
    rows = cursor.fetchall()
    conn.close()
    if rows is None: return
    
    mon_wallet = Wallet("mon", config) 
    mon_balance = mon_wallet.get_balance()- config["minbalance"]
    vtc_wallet = Wallet("vtc", config)
    vtc_balance = vtc_wallet.get_balance() - config["minbalance"]


    total_mon_amount, total_vtc_amount = 0, 0
    app_log("Available balances %.8f MON, %.8f VTC" % (mon_balance if mon_balance > 0 else 0, 
                                                       vtc_balance if vtc_balance > 0 else 0))
    app_log("Shares backlog %s" % len(rows))

    mon_payout_tx = dict()
    vtc_payout_tx = dict()
    paid_rows = []

    # maps n addresses to sets of row ids
    paid_rows_map = dict()

    for rowid, user, auxuser, monvalue, vtcvalue in rows:
        if total_mon_amount > mon_balance and total_vtc_amount > vtc_balance:
            break

        if total_mon_amount <= mon_balance:
            if auxuser in mon_payout_tx:
                # cap payouts at slightly above min_tx (before fees)
                if mon_payout_tx[auxuser] <= config["mon_min_tx"] + 0.01:
                    mon_payout_tx[auxuser] += monvalue
                    total_mon_amount += monvalue
            else:
                mon_payout_tx[auxuser] = monvalue
                total_mon_amount += monvalue

        if total_vtc_amount <= vtc_balance:
            if user in vtc_payout_tx:
                if vtc_payout_tx[user] <= config["vtc_min_tx"] + 0.01:
                    vtc_payout_tx[user] += vtcvalue
                    total_vtc_amount += vtcvalue
            else:
                vtc_payout_tx[user] = vtcvalue
                total_vtc_amount += vtcvalue
        
        # one vertcoin address, multiple monocle addresses
        if user in paid_rows_map and not auxuser in paid_rows_map:
            paid_rows_idx = paid_rows_map[user]
            paid_rows_map[auxuser] = paid_rows_idx
        # one monocle addresses, multiple vertcoin addresses
        elif not user in paid_rows_map and auxuser in paid_rows_map:
            paid_rows_idx = paid_rows_map[auxuser]
            paid_rows_map[user] = paid_rows_idx
        else:
            paid_rows.append([dict(monpaid=True, vtcpaid=True)])
            paid_rows_idx = len(paid_rows) - 1
            paid_rows_map[auxuser] = paid_rows_idx
            paid_rows_map[user] = paid_rows_idx

        paid_rows[paid_rows_idx].append(rowid)

    # clean up floating point inaccuracies by rounding to full coin units
    for user in vtc_payout_tx.keys():
        vtc_payout_tx[user] = round(vtc_payout_tx[user], 8)
    for auxuser in mon_payout_tx.keys():
        mon_payout_tx[auxuser] = round(mon_payout_tx[auxuser], 8)


    # FIXME: redistribute the coins that were from a users too small payout?
    mon_fee_amount, vtc_fee_amount = 0, 0

    # calculate vtc fees and remove any payouts that are below mintx
    for address in vtc_payout_tx.keys():
        if vtc_payout_tx[address] * (1 - fee) >= config["vtc_min_tx"]:
            this_fee = (vtc_payout_tx[address] * fee)
            vtc_fee_amount += this_fee
            vtc_payout_tx[address] -= this_fee
            vtc_payout_tx[address] = round(vtc_payout_tx[address], 8)
        else:
            del vtc_payout_tx[address]
            idx = paid_rows_map[address]
            del paid_rows_map[address]
            paid_rows[idx][0]["vtcpaid"] = False

    # calculate mon fees and remove any payouts that are below mintx
    for address in mon_payout_tx.keys():
        if mon_payout_tx[address] * (1 - fee) >= config["mon_min_tx"]:
            this_fee = (mon_payout_tx[address] * fee)
            mon_fee_amount += this_fee
            mon_payout_tx[address] -= this_fee
            mon_payout_tx[address] = round(mon_payout_tx[address], 8)
        else:
            del mon_payout_tx[address]
            idx = paid_rows_map[address]
            del paid_rows_map[address]
            paid_rows[idx][0]["monpaid"] = False
        
            # neither balance will be paid
            if not paid_rows[idx][0]["vtcpaid"]:
                paid_rows[idx] = paid_rows[idx][:1]
    
    if not vtc_payout_tx and not mon_payout_tx: 
        app_log("No user has a share balance that meets the minimum transaction requirement.")
        return None,None,None,None
    
    app_log("Shares queued for payment: %d" % sum(len(x)-1 for x in paid_rows))
    
    app_log("Fees this run: %.8f MON, %.8f VTC" % (mon_fee_amount, vtc_fee_amount))

    if mon_fee_amount > 0:
        if not mon_wallet.depositfee(mon_fee_amount):
            app_log("fee deposit of %.8f MON failed!" % mon_fee_amount)
    
    if vtc_fee_amount > 0:
        if not vtc_wallet.depositfee(vtc_fee_amount):
            app_log("fee deposit of %.8f VTC failed!" % vtc_fee_amount)

    
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
    if  mon_fee_balance > 10.0:
        if not config["monfeeaddress"] in mon_payout_tx: 
            mon_payout_tx[config["monfeeaddress"]] = mon_fee_balance
        else:
            mon_payout_tx[config["monfeeaddress"]] += mon_fee_balance
        
        mon_wallet.withdrawfee(mon_fee_balance)
    
    assert(len(paid_rows) > 0)
    vtc_txhash = vtc_wallet.sendmany(vtc_payout_tx)
    mon_txhash = mon_wallet.sendmany(mon_payout_tx)
    if not vtc_txhash and not mon_txhash: return None, None

    today = datetime.utcnow()

    # add the new transactions to the database
    vtc_txid = store_tx(today, vtc_txhash, vtc_payout_tx, "vtc")
    mon_txid = store_tx(today, mon_txhash, mon_payout_tx, "mon")

    app_log("Removing paid shares...")

    conn = mdb.connect( 
        config["dbhost"], 
        config["dbuser"], 
        config["dbpass"], 
        config["dbname"]
    )
    
    cursor = conn.cursor()
    update_count, deleted_count = 0,0
    
    for idx in set(paid_rows_map.values()):
        # both share denominations have been paid during this run
        if paid_rows[idx][0]["monpaid"] and paid_rows[idx][0]["vtcpaid"]:
            for rowid in islice(paid_rows[idx], 1, None):
                if deleted_count % 2000 == 0 and deleted_count > 0: 
                    conn.commit()
                
                # save paid shares
                cursor.execute("""
                    insert into 
                    stats_paidshares(foundtime, user, auxuser, 
                                     sharediff, 
                                     monvalue, vtcvalue, 
                                     vtcdiff, mondiff, 
                                     vtctx_id, montx_id) 
                    select foundtime, user, auxuser, sharediff, 
                    monvalue, vtcvalue, vtcdiff, mondiff, 
                    %s, %s from stats_shares where id = %s
                """, (vtc_txid, mon_txid, rowid))
                
                # remove them from unpaid shares
                cursor.execute("delete from stats_shares where id=%s", (rowid,))
                deleted_count += 1

        # only the monocle value has been paid for this share
        elif paid_rows[idx][0]["monpaid"]:
            for rowid in islice(paid_rows[idx], 1, None):
                if update_count % 2000 == 0 and update_count > 0: 
                    conn.commit()
                cursor.execute(
                    "update stats_shares set monpaid=1 where id=%s", (rowid,))
                update_count += 1

        # only the vertcoin value has been paid for this share
        elif paid_rows[idx][0]["vtcpaid"]:
            for rowid in islice(paid_rows[idx], 1, None):
                if update_count % 2000 == 0 and update_count > 0: 
                    conn.commit()
                cursor.execute(
                    "update stats_shares set vtcpaid=1 where id=%s", (rowid,))
                update_count += 1

    app_log("Deleted %s paid shares." % deleted_count)
    conn.commit()
    conn.close()
    return vtc_txhash, vtc_payout_tx, mon_txhash, mon_payout_tx

def run_sharepayout():
    app_log("Payment processing thread started...")
    while True:
        start = time()
        vtc_txhash, vtc_tx, mon_txhash, mon_tx = pay_shares()
        if (not vtc_txhash or not vtc_tx) and (not mon_txhash or not mon_tx):
            app_log("All transactions failed.")
            app_log("Retrying in 5 minutes.")
            sleep(300)
            continue
        if vtc_txhash:
            app_log("Completed vtc transaction %s:" % vtc_txhash)
            for address,amount in vtc_tx.iteritems():
                app_log("%s %.8f VTC" % (address, amount))
        if mon_txhash:
            app_log("Completed mon transaction %s:" % mon_txhash)
            for address,amount in mon_tx.iteritems():
                app_log("%s %.8f MON" % (address, amount))
        app_log("Parsed and sent in %.4f seconds. Next run in 5 minutes." % (time() - start))
        sleep(300)

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