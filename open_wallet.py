# тут мы вставляем все импорты
import requests
import logging
import sys
import os
from multiprocessing.pool import ThreadPool as Pool
import threading

import mnemonic
import bip32utils
import gen_eth

from datetime import datetime
import time


from Bip39Gen import Bip39Gen

from telegram.ext import Updater, CallbackContext, CommandHandler, JobQueue
from telegram import Update, Bot, KeyboardButton, ReplyKeyboardMarkup
# import sqlite3 # ? mb sqlAlchemy? peewee?
from peewee import *


db = SqliteDatabase('server.db')


class User(Model):
    telegram_id = TextField(unique=True)
    chat_id = TextField()
    user_name = TextField()
    rights = TextField()

    class Meta:
        database = db  # This model uses the "test.db" database.


class UserSettings(Model):
    user = ForeignKeyField(User, unique=True, backref='user_settings')
    wet_update = BooleanField()
    msg_update = BooleanField()

    class Meta:
        database = db


class Logging(Model):
    level = TextField()
    message = TextField()
    date_time = DateTimeField(default=datetime.now)

    class Meta:
        database = db


class Discovered(Model):
    coin = TextField()
    balance = TextField()
    address = TextField()
    mnemonic_phrase = TextField()
    etc = TextField()
    date_time = DateTimeField(default=datetime.now)

    class Meta:
        database = db


def add_admin():
    admin = User(telegram_id=Settings.tg_chat_id,
                 chat_id=Settings.tg_chat_id,
                 user_name=Settings.tg_admin,
                 rights="Admin")
    admin.save()
    us = UserSettings(user=admin, wet_update=True, msg_update=True)
    us.save()


if not ['discovered', 'logging', 'user', 'usersettings'] in [db.get_tables()]:
    db.create_tables([User, UserSettings, Logging, Discovered])
    add_admin()


# {#database}

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


class Settings:
    # проверка по публичному ключу контрактов, на которых могут висеть коины
    save_empty = "n"
    total_count = 0
    wet = []
    wet_count = 0
    wet_update_list = ["Wet BTC updater started", "wet check run btc 2"]
    dry_count = 0

    dry_eth = 0
    wet_eth_count = 0
    wet_eth = ["Wet Etc updater started", "wet check run etc 2"]

    Received_count = 0
    mode = 12 # сколько слов в мнемонике будем использовать
    # threads = 10 # тут ставим число проксей, сколько у нас есть
    threads = 1 # 1 если проксей нет и PP выдаёт только False, т.е. юзается только родной IP
    pool = None
    pool_state = {}
    msg = ["Server Restart", "Msg updater started"]

    tg_admin = "u_tg_name"
    tg_token = 'u:bot_token'
    tg_chat_id = u_tg_id #int

    logger = logging.getLogger('logger')
    logger.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt='[%(asctime)s: %(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.debug("debug info")


proxypay_list = [{"name": "proxy.house_x10",
                  "login": "uLogin:uPassword",
                  "method": "http",
                  "ip": [
                      "U.i.p.address:3000",
                      "U.i.p.address:3000",
                      "U.i.p.address:3000",
                      "U.i.p.address:3000",
                      "U.i.p.address:3000",
                      "U.i.p.address:3000",
                      "U.i.p.address:3000",
                      "U.i.p.address:3000",
                      "U.i.p.address:3000",
                      "U.i.p.address:3000"
                  ]
                  }]


class ProxyPay:
    """Этот метод предназначен для платных проксей"""
    lenth = 0

    def __init__(self):
        super(ProxyPay, self).__init__()

        self.proxy = []
        self.proxy_eth = []
        for proxy_res in proxypay_list:
            for ip in proxy_res['ip']:
                px = {'https': f'{proxy_res["method"]}://{proxy_res["login"]}@{ip}',
                      'http': f'{proxy_res["method"]}://{proxy_res["login"]}@{ip}'}
                self.proxy.append(px)
                self.proxy_eth.append(px)
        self.lenth = len(self.proxy)
        SS.logger.info("Proxy Dealer started")

    def get_proxy(self):
        """Отдаёт адрес проеси в формате requests для битков
            если закоментить и ретёрнуть False то пойдёт без прокси"""
        # if len(self.proxy)!=0:
        #     proxy = self.proxy.pop(0)
        #     SS.logger.debug("Proxy sended", extra=proxy)
        #     return proxy
        # else:
        #     SS.logger.debug("Proxy out")
        SS.logger.debug("Proxy btc sended FALSE")
        return False

    def get_proxy_eth(self):
        """Отдаёт адрес проеси в формате requests для эфира
            если закоментить и ретёрнуть False то пойдёт без прокси"""
        # if len(self.proxy_eth) != 0:
        #     proxy = self.proxy.pop(0)
        #     SS.logger.debug("Proxy eth sended", extra=proxy)
        #     return proxy
        # else:
        #     SS.logger.debug("Proxy eth out")
        #     return False
        SS.logger.debug("Proxy eth sended FALSE")
        return False

def getInternet():
    """Функция проверки связи с интернетом BOOL"""
    try:
        try:
            requests.get('https://www.google.com')
        except requests.ConnectTimeout:
            requests.get('http://1.1.1.1')
        SS.logger.info("Test internet passed")
        return True
    except requests.ConnectionError:
        SS.logger.debug('no internet')
        time.sleep(1)
        return False


def makeDir(path: str):
    if not os.path.exists(path):
        SS.logger.debug(f'created path: {path}')
        os.makedirs(path)


def seed(mnemonic_words):
    mobj = mnemonic.Mnemonic("english")
    seed = mobj.to_seed(mnemonic_words)
    return seed


def convertbits(data, frombits=8, tobits=5, pad=True):
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def bech32_polymod(values):
    """Internal function that computes the Bech32 checksum."""
    generator = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ value
        for i in range(5):
            chk ^= generator[i] if ((top >> i) & 1) else 0
    return chk


def bech32_create_checksum(data, hrp='bc'):
    """Compute the checksum values given HRP and data."""
    values = bech32_hrp_expand(hrp) + data
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_hrp_expand(hrp):
    """Expand the HRP into values for checksum computation."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def bip39_adr_btc(seed):
    # https://bitcointalk.org/index.php?topic=4992632.0   #bech32
    bip32_root_key_obj = bip32utils.BIP32Key.fromEntropy(seed)
    bip32_child_key_obj = bip32_root_key_obj.ChildKey(
        44 + bip32utils.BIP32_HARDEN
    ).ChildKey(
        0 + bip32utils.BIP32_HARDEN
    ).ChildKey(
        0 + bip32utils.BIP32_HARDEN
    ).ChildKey(0).ChildKey(0)
    P2PKH = bip32_child_key_obj.Address()  # 1ver
    P2SH = bip32_child_key_obj.P2WPKHoP2SHAddress()  # 2 ver

    vbytes = convertbits(bip32_child_key_obj.Identifier())
    vbytes.insert(0, 0)
    check_sum = bech32_create_checksum(vbytes)
    sublime = vbytes+check_sum
    char5translate = "".join([CHARSET[i] for i in sublime])
    P2WPKH = "bc1"+char5translate
    # P2WPKH = "" # Bech32

    return {"P2PKH": P2PKH, "P2SH": P2SH, "Bech32": P2WPKH}


def get_mnemonic():
    # mode 12 (или 15, 18, 21)
    mnemonic_words = Bip39Gen(bip39wordlist=dictionary,
                              mode=Settings.mode).mnemonic
    return mnemonic_words


def eth_thread(name, proxy):
    SS.msg.append(f"ETH thread:{name}\naddress: {proxy}\nStarted")
    # создаём атрибут в обьекте для хранения статуса API
    # ESS.__setattr__(name,{})# пока что не нуже ввиду медленности API
    # __getattribute__
    # генерируем пул потоков по количетву API
    api_status = {"get_ethplorer_io": 0,
                  "get_blockchair_com": 0,
                  "get_blockcypher_com": 0
                  }

    while True:
        if ESS.eth_pool_switch:
            SS.pool_state.update({name:"run"})
            mnemonic_words = get_mnemonic()
            # SS.logger.debug(f"mnemonic_words: {mnemonic_words}")
            # dict {private_key   public_key   address}
            mw_ac = gen_eth.mnemonic_to_eth(mnemonic_words)
            # SS.logger.debug(f"mw_ac: {mw_ac}")
            # address ="0x6016dca5eb73590fa875fcf32bdb74905a4323bd"
            address = mw_ac["address"]
            # SS.logger.debug(f"address: {address}")
            while True:
                dt_now = int(datetime.now().timestamp())
                if api_status["get_ethplorer_io"] < dt_now:
                    ret = get_ethplorer_io(address, proxy)
                    dt_now = int(datetime.now().timestamp())
                    api_status["get_ethplorer_io"] = dt_now+180
                    SS.pool_state.update({name:"run"})
                    break

                elif api_status["get_blockchair_com"] < dt_now:
                    ret = get_blockchair_com(address, proxy)
                    dt_now = int(datetime.now().timestamp())
                    api_status["get_blockchair_com"] = dt_now+60
                    SS.pool_state.update({name:"run"})

                    break

                elif api_status["get_blockcypher_com"] < dt_now:
                    ret = get_blockchair_com(address, proxy)
                    dt_now = int(datetime.now().timestamp())
                    api_status["get_blockcypher_com"] = dt_now+30
                    SS.pool_state.update({name:"run"})

                    break
                SS.pool_state.update({name:"sleep"})
                time.sleep(1)

            if ret["end"] == True:
                data = ret["data"]
                if data is not None:
                    if data["active"] == True or data["balance"] == True or data["etc"] is not None:
                        SS.wet_eth.append({mnemonic_words: data})
                        etc = f"active:{data['active_data'] if data.get('active_data') is not None else '' }; \netc: {etc if etc is not None else '' }"
                        disc = Discovered(
                            coin="ETH", balance=data["balance_data"], address=data["address"], mnemonic_phrase=mnemonic_words, etc=etc)
                        SS.wet_eth_count += 1
                    SS.dry_eth += 1
                    # print("data",data)

            else:
                if ret["err"] is not None:
                    SS.msg.append(f"Error\nthread:{name}\naddress: {address}\n{ret['err']}\n{mnemonic_words}")
                if ret["exception"]:
                    SS.msg.append(f"Exception!\nthread:{name}\naddress: {address}\n{ret['exception']}\n{mnemonic_words}")

            # print(SS.wet_eth_count,SS.wet_eth,SS.dry_eth)

        else:
            SS.pool_state.update({name:"sleep"})
            time.sleep(5)


def btc_thread(name, proxy):
    SS.msg.append(f"BTC thread:{name}\naddress: {proxy}\nStarted")
    while True:
        if ESS.eth_pool_switch:
            btc_addr_dict = {}
            SS.pool_state.update({name:"run"})
            for _ in range(0, 30):
                mnemonic_words = get_mnemonic()
                # с помощь этого зерна можно получать кошельки
                seed64 = seed(mnemonic_words)
                # dict 3 адреса P2PKH P2SH Bech32
                btc_addr = bip39_adr_btc(seed64)
                btc_addr_dict[btc_addr["P2PKH"]] = mnemonic_words
                btc_addr_dict[btc_addr["P2SH"]] = mnemonic_words
                btc_addr_dict[btc_addr["Bech32"]] = mnemonic_words
            # btc_addr_dict["1A8JiWcwvpY7tAopUkSnGuEYHmzGYfZPiq"]="Test"
            # btc_addr_dict={"1A8JiWcwvpY7tAopUkSnGuEYHmzGYfZPiq":"Test"}
            # addr_line = "1A8JiWcwvpY7tAopUkSnGuEYHmzGYfZPiq"
            addr_line = "|".join([i for i in btc_addr_dict])
            ret = getBalance_blockchain_info(addr_line, proxy)
            if ret["end"] == True:
                if ret["data"] is not None:
                    result = ret["data"]
                    for end_addres in result:
                        adr_dt = result[end_addres]
                        if adr_dt["final_balance"] != 0 or adr_dt["n_tx"] != 0 or adr_dt["total_received"] != 0:
                            mw = btc_addr_dict[end_addres]
                            disc = Discovered(
                                coin="BTC", balance=adr_dt["final_balance"], address=end_addres, mnemonic_phrase=mw, etc="")
                            SS.wet.append({mw: adr_dt})
                            SS.wet_count += 1
                        SS.dry_count += 1

            else:
                if ret["err"] is not None:
                    SS.msg.append(f"Error\nthread:{name}\naddress: {addr_line}\n{ret['err']}")
                if ret["exception"]:
                    SS.msg.append(f"Exception!\nthread:{name}\naddress: {addr_line}\n{ret['exception']}")
                    if ret["exception"] == "RAID":
                        SS.msg.append(f"thread {name} sleep as hour: RAID")
                        SS.logger.info(f"thread {name} sleep as hour: RAID")
                        time.sleep(3600)
            # print(SS.dry_count,SS.wet,SS.wet_count)
            SS.pool_state.update({name:"sleep"})
            time.sleep(20)
        else:
            SS.pool_state.update({name:"sleep"})

            time.sleep(5)


def start_pars():
    # SS.pool = Pool(1)
    SS.pool = Pool(SS.threads*2+2)
    SS.pool.apply_async(TeleBot, ())
    for i in range(0, SS.threads):
        proxy = PP.get_proxy()
        print("start thread")
        SS.pool.apply_async(btc_thread, (f"BTC_{i}", proxy,))
        time.sleep(0.5)
        print("start thread etc")

        SS.pool.apply_async(eth_thread, (f"ETH_{i}", PP.get_proxy_eth(),))
        time.sleep(0.5)
        #     TB = TeleBot() блокирует

        # SS.pool.apply_async(reset_pool_state,())
        # print("pool dir",dir(SS.pool))

    SS.pool.close()
    SS.pool.join()


class EthSiteSettings:
    eth_pool_switch = True
    #Eth_1 = {}

    # {"поток1":
    #     {"сайт1":{"status":True,
    #             "requests":int}
    #      "сайт2":{"status":False,
    #             "requests":int}
    #     }

    # }

    thread_status = {}
    """{
        "number_thread1":True,
        "number_thread2":True,
        "number_thread3":False,
        }"""

    def __setattr__(self, name, value):
        self.__dict__[name] = value


class TeleBot():
    admin = Settings.tg_admin
    user_chat_ids = {}

    updater = Updater(
        token=Settings.tg_token, use_context=True)
    dispatcher = updater.dispatcher
    jq = updater.job_queue
    bot = dispatcher.bot

    # logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',level=logging.INFO)

    def __init__(self):
        print("DB")
        print("TELEBOT")
        # self.dispatcher = self.updater.self.dispatcher
        # self.bot =self.dispatcher.bot

        self.admin_chat_id = None
        self.wet_update_checker = None
        self.msg_update_checker = None
        try:
            self.sets()
        except Exception as e:
            print("sets e", e)
            SS.logger.warning('Protocol problem: %s', 'self.sets()', extra=e)

        start_handler = CommandHandler('start', self.start)
        self.dispatcher.add_handler(start_handler)

        get_wet_handler = CommandHandler('wet', self.get_wet)
        self.dispatcher.add_handler(get_wet_handler)

        get_dry_handler = CommandHandler('dry', self.get_dry)
        self.dispatcher.add_handler(get_dry_handler)

        get_thread = CommandHandler('thread', self.get_thread_alive)
        self.dispatcher.add_handler(get_thread)

        get_wet_update = CommandHandler('wet_update', self.wet_update)
        self.dispatcher.add_handler(get_wet_update)

        get_msg_update = CommandHandler('msg_update', self.msg_update)
        self.dispatcher.add_handler(get_msg_update)

        kgb = [
            [KeyboardButton('/dry'), KeyboardButton('/wet')],
            [KeyboardButton('/restart(unwork)')],
            [KeyboardButton('/start'), KeyboardButton('/thread')],
            ]
        self.kb = ReplyKeyboardMarkup(kgb, resize_keyboard=True)

        job_second = self.jq.run_repeating(
            self.run_one_on_second, interval=1, first=15)
        job_hour = self.jq.run_repeating(
            self.run_one_on_hour, interval=3600, first=10)
        job_day = self.jq.run_repeating(
            self.run_one_on_day, interval=3600*24, first=10)

        self.updater.start_polling()

    def sets(self):
        self.dt_msg_updte = 0

        us = User.filter(user_name=Settings.tg_admin, rights="Admin")
        if us:
            admin = us.first()
            set_admin = UserSettings.get(user=admin)
            if admin is not None:
                self.admin_chat_id = admin.chat_id
                self.wet_update_checker = set_admin.wet_update
                self.msg_update_checker = set_admin.msg_update
                SS.logger.debug(f"msg_update_checker: {self.msg_update_checker}")
            else:
                print("no en")

    def run_one_on_hour(self, context: CallbackContext):
        # SS.logger.debug(f"Run job_hour")
        # Раз в час
        self.message_me(self.admin_chat_id, f"dry:{SS.dry_count}\nwet:{SS.wet_count}\n\netc dry:{SS.dry_eth}\netc wet:{SS.wet_eth_count}")

    def run_one_on_day(self, context: CallbackContext):
        # SS.logger.debug(f"Run day")
        pass

    def run_one_on_second(self, context: CallbackContext):
        # SS.logger.debug(f"Run job_sec {self.wet_update_checker}")

        if self.wet_update_checker:
            if len(SS.wet) != 0:
                self.message_me(self.admin_chat_id, SS.wet.pop(0))
            if len(SS.wet_eth) != 0:
                self.message_me(self.admin_chat_id, SS.wet_eth.pop(0))

        if self.msg_update_checker and len(SS.msg) != 0:
            text_msg = ""
            while len(SS.msg) != 0:
                text_msg = text_msg+" \n"+str(SS.msg.pop(0))

            self.message_me(self.admin_chat_id, text_msg)

        if self.msg_update_checker and len(SS.msg) != 0:
            text_msg = ""
            while len(SS.msg) != 0:
                text_msg = text_msg+" \n"+str(SS.msg.pop(0))
            SS.logger.debug(f"text message: {text_msg}")
            self.message_me(self.admin_chat_id, text_msg)

    def start(self, update: Update, context: CallbackContext):
        # context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a bot, please talk to me!")

        # self.update = update
        # self.context= context
        # # print(context)
        # # print(dir(update))
        # # print(update._effective_user.username)
        user = update._effective_user
        user_name = update._effective_user.username
        # user_id = user.id
        # print(user_name,user_id,update.effective_chat.id)
        if user_name != self.admin:
            self.msg_NER(update, context)

        else:

            # self.user_chat_ids[user_name]=update.effective_chat.id

            #     user = User.get(chat_id=self.admin_chat_id)
            #     us = UserSettings.get(user=user)
            #     us.wet_update = self.wet_update_cheher
            #     us.save()

            #     DataBase().request_builder({"method":"UPDATE",
            #                             "table":"users",
            #                             "where":{"user_name":self.admin},
            #                             "data":{"chat_id":update.effective_chat.id,
            #                                   "tg_id":user.id,
            #                                   "wet_update":True,
            #                                   "msg_update":True}})
            #     print(self.user_chat_ids)
            self.message(context, update.effective_chat.id)

    def message(self, context: CallbackContext, chat_id):
        context.bot.sendMessage(
            chat_id=chat_id, text="Старт прошёл успешно", reply_markup=self.kb)

    def get_wet(self, update: Update, context: CallbackContext):
        if update._effective_user.username == self.admin:
            try:
                context.bot.sendMessage(chat_id=self.admin_chat_id, text=f"BTC:{SS.wet_count}\ndata:{SS.wet}")
                time.sleep(0.3)
                context.bot.sendMessage(chat_id=self.admin_chat_id, text=f"ETH:{SS.wet_eth_count}\ndata:{SS.wet_eth}")

            except:
                self.get_wet(update, context)

    def get_dry(self, update: Update, context: CallbackContext):
        if update._effective_user.username == self.admin:
            try:
                context.bot.sendMessage(chat_id=self.admin_chat_id, text=f"btc:{SS.dry_count}\neth:{SS.dry_eth}")

            except:
                self.get_dry(update, context)

    def get_thread_alive(self, update: Update, context: CallbackContext):
        if update._effective_user.username == self.admin:
            text = "".join([f'{i} {SS.pool_state[i]}\n' for i in SS.pool_state])
            # for i in SS.pool_state:
            try:
                context.bot.sendMessage(chat_id=self.admin_chat_id, text=f"{text}")
            except:
                self.get_dry(update, context)

    def message_me(self, chat_id, text):
        self.bot.sendMessage(chat_id=chat_id, text=f"{text}")

    def wet_update(self, update: Update, context: CallbackContext):
        if update._effective_user.username == self.admin:
            if self.wet_update_cheher == False:
                self.wet_update_cheher = True

                context.bot.sendMessage(chat_id=self.admin_chat_id, text=f"Обновление включены")
            else:
                self.wet_update_cheher = False
                context.bot.sendMessage(chat_id=self.admin_chat_id, text=f"Обновление выключены")
            user = User.get(chat_id=self.admin_chat_id)
            us = UserSettings.get(user=user)
            us.wet_update = self.wet_update_cheher
            us.save()

        else:
            self.msg_NER(update, context)

    def msg_update(self, update: Update, context: CallbackContext):
        if update._effective_user.username == self.admin:
            if self.msg_update_cheher == False:
                self.msg_update_cheher = True
                context.bot.sendMessage(chat_id=self.admin_chat_id, text=f"Обновление сообщений включены")
            else:
                self.msg_update_cheher = False
                context.bot.sendMessage(chat_id=self.admin_chat_id, text=f"Обновление сообщений выключены")
            user = User.get(chat_id=self.admin_chat_id)
            us = UserSettings.get(user=user)
            us.msg_update = self.msg_update_cheher
            us.save()

    def msg_NER(self, update: Update, context: CallbackContext):
        # Not Enough Rights
        context.bot.sendMessage(chat_id=update.effective_chat.id, text=f"Not Enough Rights")


"""===================== ETH ======================"""


def get_ethplorer_io(address, proxy):
    # ETH
    url = f"https://api.ethplorer.io/getAddressInfo/{address}?apiKey=freekey&showETHTotals=false"
    json_return = {"end": None,  # bool
                   "data": None,  # dict
                   "exception": None,  # string
                   "err": None  # string
                   }
    for qwe in range(0, 3):
        try:
            response = requests.get(url, proxies=proxy)
            status = response.status_code
            if status != 200:
                if qwe < 2:
                    time.sleep(180)
                    continue
                else:
                    json_return["end"] = False
                    json_return["err"] = f"{status} : {response.text}"
                    SS.logger.debug(f"{status} : {response.text}")
                    return json_return
            t = response.json()
            info = {"address": None,  # string
                    "active": False,  # bool
                    "balance": False,  # bool
                    "active_data": None,  # string
                    "balance_data": None,  # int or real
                    "etc": None
                    }
            if t.get("ETH"):
                info["address"] = t["address"]
                etc = []
                if t["ETH"]["totalIn"] != 0 or t["ETH"]["totalOut"] != 0 or t.get("token_info") or t.get("tokens"):
                    print('!ACTIVE')
                    info["active"] = True
                    info["active_data"] = f"""totalIn: {t["ETH"]["totalIn"]} \ntotalOut: {t["ETH"]["totalOut"]}"""

                if t.get("token_info"):
                    etc.append(t["token_info"])
                if t.get("tokens"):
                    etc.append(t["tokens"])

                if etc:
                    info["etc"] = etc

                if t["ETH"]["balance"] != 0:
                    print(t["ETH"]["balance"])
                    info["balance"] = True
                    info["balance_data"] = t["ETH"]["balance"]
                else:
                    pass
                    # print("empty")
                json_return["data"] = info
            json_return["end"] = True
            return json_return
        except Exception as exception:

            if qwe < 2:
                time.sleep(180)
                pass
            else:
                SS.logger.exception(
                    str(exception.__class__)+str(exception.args))
                # print(exception.__class__)
                json_return["end"] = False
                json_return["exception"] = str(
                    exception.__class__)+str(exception.args)
                return json_return


def get_blockcypher_com(address, proxy):
    url = f"https://api.blockcypher.com/v1/eth/main/addrs/{address}/balance"
    json_return = {"end": None,  # bool
                   "data": None,  # dict
                   "exception": None,  # string
                   "err": None  # string
                   }
    for qwe in range(0, 3):
        try:
            response = requests.get(url, proxies=proxy)
            status = response.status_code
            if status != 200:
                if qwe < 2:
                    time.sleep(30)
                    continue
                else:
                    json_return["end"] = False
                    json_return["err"] = f"{status} : {response.text}"
                    SS.logger.debug(f"{status} : {response.text}")
                    return json_return
            t = response.json()
            info = {"address": None,  # string
                    "active": False,  # bool
                    "balance": False,  # bool
                    "active_data": None,  # string
                    "balance_data": None,  # int or real
                    "etc": None
                    }
            if t.get("address"):
                info["address"] = t["address"]
                if t["final_n_tx"] != 0:
                    print('ACTIVE!')
                    info["active"] = True
                    info["active_data"] = f"""final_n_tx: {t["final_n_tx"]}"""

                if t["balance"] != 0:
                    print(t["balance"])
                    info["balance"] = True
                    info["balance_data"] = t["balance"]
                else:
                    print("empty")
                json_return["data"] = info
            json_return["end"] = True
            return json_return
        except Exception as exception:
            if qwe < 2:
                time.sleep(30)
                pass
            else:
                SS.logger.exception(
                    str(exception.__class__)+str(exception.args))
                # print(exception.__class__)
                json_return["end"] = False
                json_return["exception"] = str(
                    exception.__class__)+str(exception.args)
                return json_return


def get_blockchair_com(address, proxy):
    address = address.lower()
    url = f"https://api.blockchair.com/ethereum/dashboards/address/{address}"
    json_return = {"end": None,  # bool
                   "data": None,  # dict
                   "exception": None,  # string
                   "err": None  # string
                   }
    for qwe in range(0, 3):

        try:
            response = requests.get(url, proxies=proxy)
            status = response.status_code
            if status != 200:
                if qwe < 2:
                    time.sleep(60)
                    continue
                else:
                    json_return["end"] = False
                    json_return["err"] = f"{status} : {response.text}"
                    SS.logger.debug(f"{status} : {response.text}")
                    return json_return
            t = response.json()

            info = {"address": None,  # string
                    "active": False,  # bool
                    "balance": False,  # bool
                    "active_data": None,  # string
                    "balance_data": None,  # int or real
                    "etc": None
                    }
            if t.get("data"):
                info["address"] = address
                data_adress = t["data"][address]
                if data_adress["address"]["transaction_count"] != 0 or data_adress["address"]["call_count"] != 0:
                    print('ACTIVE!')
                    info["active"] = True
                    info["active_data"] = f"""transaction_count: {data_adress["address"]["transaction_count"]} \ntransaction_count: {data_adress["address"]["transaction_count"]}"""

                if data_adress["address"]["balance"] != "0":
                    print(data_adress["address"]["balance"])
                    info["balance"] = True
                    info["balance_data"] = data_adress["address"]["balance"]
                else:
                    # print("empty")
                    pass
                json_return["data"] = info
            json_return["end"] = True
            return json_return
        except Exception as exception:
            if qwe < 2:
                time.sleep(60)
                pass
            else:
                SS.logger.exception(
                    str(exception.__class__)+str(exception.args))
                # print(exception)
                # print(exception.__class__,exception.args)
                json_return["end"] = False
                json_return["exception"] = str(
                    exception.__class__)+str(exception.args)
                return json_return


"""===================== End ETH ======================"""


"""===================== BTC ======================"""


def getBalance_blockchain_info(addr, proxy):
    json_return = {"end": None,  # bool
                   "data": None,  # dict
                   "exception": None,  # string
                   "err": None  # string
                   }
    for qwe in range(0, 3):
        try:
            url = f'https://blockchain.info/balance?active={addr}'
            response = requests.get(url, proxies=proxy)
            status = response.status_code
            if status != 200:
                json_return["end"] = False
                json_return["err"] = f"{status} : {response.text}"
                SS.logger.debug(f"{status} : {response.text}")
                if status == 504 or 'Cloudflare Ray ID' in response.text or 'Forbidden' in response.text:
                    json_return["end"] = False
                    json_return["err"] = f"{status} : {response.text}"
                    json_return["exception"] = "RAID"
                    SS.logger.debug(f"proxy {proxy} blocked RAID as hour")
                    return json_return
                else:
                    return json_return

            t = response.json()
            json_return["end"] = True
            json_return["data"] = t
            return json_return
            break
        except Exception as exception:
            if qwe < 2:
                time.sleep(10)
                pass
            else:
                SS.logger.exception(
                    str(exception.__class__)+str(exception.args))
                json_return["end"] = False
                json_return["exception"] = str(
                    exception.__class__)+str(exception.args)
                return json_return


"""===================== End BTC ======================"""

if __name__ == '__main__':
    SS = Settings()
    PP = ProxyPay()
    ESS = EthSiteSettings()
    makeDir("results")
    lock = threading.Lock()
    if getInternet() == False:
        raise ConnectionError("Check internet state")
    else:
        dictionary = requests.get(
            'https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt').text.strip().split('\n')
    start_pars()
