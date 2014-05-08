import redis
import MySQLdb as mdb
import json
from datetime import datetime
from pyjsonrpc import HttpClient
from time import sleep, time
from threading import Thread

class ShareLogger(Thread):
    def __init__(self, config, debug=False):
        Thread.__init__(self)
        self.config = config
        self.debug = debug
        self.last_check = 0
        self.numshares = 0
        self.infocache = dict()
        self.wallets = config["wallets"]

    def run(self):
        print "%s Share processing thread started..." % datetime.now()
        self.conn = mdb.connect(
            self.config["dbhost"], 
            self.config["dbuser"], 
            self.config["dbpass"], 
            self.config["dbname"],
            connect_timeout=5
        )
        self.cursor = self.conn.cursor()
        rd = redis.StrictRedis(self.config["redishost"], 
                               self.config["redisport"])
        sharelist = self.config["redislist"]
        raw_share = None
        try:
            while True:
                numshares = rd.llen(sharelist) 
                if numshares > 0:
                    for _ in xrange(numshares):
                        raw_share = rd.rpop(sharelist)
                        self.log_share(json.loads(raw_share))
                sleep(4)
        except KeyboardInterrupt:
            print "Interrupted. Shutting down."
            exit(0)

    def walletcmd(self, wallet, method, *params):
        return HttpClient(**wallet).call(method, *params)

    def get_info(self, wallet):
        if not wallet in self.infocache or self.last_check == 0 or time() - self.last_check > 15:
            info = self.walletcmd(self.wallets[wallet], "getinfo")
            self.infocache[wallet] = dict(height=info["blocks"], 
                                          difficulty=info["difficulty"], 
                                          balance=info["balance"])
            self.last_check = time()
        return self.infocache[wallet]

    def get_block_reward_vtc(self):
        return float(50 >> (self.infocache["vtc"]["height"]//840000))
    
    def get_block_reward_mon(self):
        height = self.infocache["mon"]["height"]
        subsidy = 0
        if height < 999:
            subsidy = 100000000 << (height + 1)//200
        elif height < 1468416:
            subsidy = int(25 * pow(0.97044562, (height + 1)//10080) * 100000000)
        return subsidy/1e8
    
    def get_value(self, share_diff, net_diff, coin):
        # since the block height is cached for 15 seconds, the worst case
        # scenario is that we pay double for shares for 15 seconds
        if coin == "vtc":
            block_reward = self.get_block_reward_vtc()
        elif coin == "mon":
            block_reward = self.get_block_reward_mon()
        else:
            block_reward = 0 # unimplemented coin
        share_value = round((float(block_reward) * share_diff)/net_diff, 12)
        
        # cap share value at 0.5% of block reward, hack
        if share_value > block_reward * 0.005:
            share_value = round(block_reward * 0.005, 12)
        return share_value


    def log_share(self, share):
        vtcinfo = self.get_info("vtc")
        moninfo = self.get_info("mon")
        if not self.cursor: 
            raise Exception("Sharelogger not started or database error")
        if share["valid"]:
            sharediff = round(share["diff"], 8)
            vtc_value = self.get_value(sharediff, vtcinfo["difficulty"], "vtc")
            mon_value = self.get_value(sharediff, moninfo["difficulty"], "mon")
        else:
            vtc_value, mon_value = 0, 0
        self.numshares += 1
        if self.debug:
            print "%s share# %d, %s" % (datetime.now(), self.numshares, share)

        
        # register user's share
        # some of these values (e.g. difficulties) are stored for debugging and
        # statistics purposes only
        self.cursor.execute("""
        insert into 
        stats_shares(foundtime, user, auxuser, vtcvalue, monvalue, 
                     sharediff, vtcdiff, mondiff, valid) 
        values(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (datetime.fromtimestamp(share["time"]), 
         share["sub"],
         share["aux"],
         vtc_value,
         mon_value, 
         round(share["diff"], 8), 
         vtcinfo["difficulty"],
         moninfo["difficulty"], 
         share["valid"]
        ))
        self.conn.commit()

