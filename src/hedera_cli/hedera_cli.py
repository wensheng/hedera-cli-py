import os
import sys
import cmd
import math

from colorama import init, Fore, Back, Style
from dotenv import load_dotenv
from hedera import (
    Hbar,
    Client,
    PrivateKey,
    AccountId,
    AccountCreateTransaction,
    AccountDeleteTransaction,
    AccountBalanceQuery,
    TransferTransaction,
    TransactionId,
    TopicCreateTransaction,
    TopicId,
    TopicMessageSubmitTransaction,
    FileId,
    FileInfoQuery,
    FileCreateTransaction,
    FileAppendTransaction,
    FileContentsQuery,
    )
from jnius import autoclass
from hedera_cli._version import version
from hedera_cli.price import get_Hbar_price
if sys.platform == "win32":
    from msvcrt import getch
else:
    from getch import getch


#List = autoclass('java.util.List')
ArrayList = autoclass('java.util.ArrayList')


FILE_CREATE_SIZE = 5000  # don't know exactly the size, 5000 works, 6000 doesn't
CHUNK_SIZE = 1024

NODE_LIST = ArrayList()

# Don't know how to get a list of nodes, so hard-code it here
# for i in (4, 6, 8):
#    NODE_LIST.add(AccountId.fromString("0.0." + str(i)))

# TODO: only List of 1 works, but which node?
NODE_LIST.add(AccountId.fromString("0.0.4"))


def getc():
    c = getch()
    if hasattr(c, 'decode'):
        return c.decode()
    return c


def getPrivateKey():
    passwd = ''
    while True:
        c = getc()
        if c == '\r' or c == '\n':
            break
        print('*', end='', flush=True)
        passwd += c
    print()

    return passwd

current_price = get_Hbar_price()


class HederaCli(cmd.Cmd):
    use_rawinput = False  # if True, colorama prompt will not work on Windows
    intro = """
# =============================================================================
#""" + Fore.WHITE + Back.BLUE + "  __   __            __                     " + Style.RESET_ALL + """
#""" + Fore.WHITE + Back.BLUE + " |  | |  |          |  |                    " + Style.RESET_ALL + """
#""" + Fore.WHITE + Back.BLUE + " |  |_|  | ____  ___|  | ____ __ __ _____   " + Style.RESET_ALL + """
#""" + Fore.WHITE + Back.BLUE + " |   _   |/ __ \/  _`  |/ __ \  '__/  _  `| " + Style.RESET_ALL + """
#""" + Fore.WHITE + Back.BLUE + " |  | |  |  ___/  (_|  |  ___/  | |  (_|  | " + Style.RESET_ALL + """
#""" + Fore.WHITE + Back.BLUE + " \__| |__/\____|\___,__|\____|__|  \___,__| " + Style.RESET_ALL + """
#""" + Fore.WHITE + Back.BLUE + "                                            " + Style.RESET_ALL + """
# :: hedera-cli :: v{}
# current Hbar price: {}
#
# github.com/wensheng/hedera-cli-py
# =============================================================================
Type help or ? to list commands.\n""".format(version, current_price)

    def __init__(self, *args, **kwargs):
        init()  # colorama
        super().__init__(*args, **kwargs)
        if "HEDERA_OPERATOR_ID" in os.environ:
            self.operator_id = AccountId.fromString(os.environ["HEDERA_OPERATOR_ID"])
        else:
            self.operator_id = None
        if "HEDERA_OPERATOR_KEY" in os.environ:
            self.operator_key = PrivateKey.fromString(os.environ["HEDERA_OPERATOR_KEY"])
        else:
            self.operator_key = ""
        self.network = os.environ.get("HEDERA_NETWORK", "testnet")
        self.setup_network(self.network)
        if self.operator_id and self.operator_key:
            self.client.setOperator(self.operator_id, self.operator_key)
        self.hbar_price = current_price
        self.set_prompt()

    def emptyline(self):
        "If this is not here, last command will be repeated"
        pass

    def set_prompt(self):
        if self.operator_id:
            self.prompt = Fore.YELLOW + '{}@['.format(self.operator_id.toString()) + Fore.GREEN + self.network + Fore.YELLOW + '] > ' + Style.RESET_ALL
        else:
            self.prompt = Fore.YELLOW + 'null@[' + Fore.GREEN + self.network + Fore.YELLOW + '] > ' + Style.RESET_ALL

    def err_return(self, msg):
        print(Fore.RED + msg)
        self.set_prompt()
        return

    def do_exit(self, arg):
        'exit Hedera cli'
        exit()

    def do_setup(self, arg):
        'set operator id and key'
        # these doesn't work on Windows
        # acc_id = input(Fore.YELLOW + "Operator Account ID (0.0.xxxx): " + Style.RESET_ALL)
        # acc_key = input(Fore.YELLOW + "Private Key: " + Style.RESET_ALL)
        print(Fore.YELLOW + "Operator Account ID (0.0.xxxx): " + Style.RESET_ALL, end='')
        acc_id = input()
        print(Fore.YELLOW + "Private Key: " + Style.RESET_ALL, end='', flush=True)
        acc_key = getPrivateKey()
        try:
            self.operator_id = AccountId.fromString(acc_id)
            self.operator_key = PrivateKey.fromString(acc_key)
            self.client.setOperator(self.operator_id, self.operator_key)
            print(Fore.GREEN + "operator is set up")
        except Exception:
            print(Fore.RED + "Invalid operator id or key")
        self.set_prompt()

    def setup_network(self, name):
        self.network = name
        if name == "mainnet":
            self.client = Client.forMainnet()
        elif name == "previewnet":
            self.client = Client.forPreviewnet()
        else:
            self.client = Client.forTestnet()

    def do_network(self, arg):
        'Switch network: available mainnet, testnet, previewnet'
        if arg == self.network:
            return self.err_return("no change")

        if arg in ("mainnet", "testnet", "previewnet"):
            self.setup_network(arg)
            self.operator_id = None
            print(Fore.GREEN + "you switched to {}, you must do `setup` again!".format(arg))
        else:
            print(Fore.RED + "invalid network")
        self.set_prompt()

    def do_keygen(self, arg):
        'Generate a pair of private and public keys'
        prikey = PrivateKey.generate()
        print(Fore.YELLOW + "Private Key: " + Fore.GREEN + prikey.toString())
        print(Fore.YELLOW + "Public Key: " + Fore.GREEN + prikey.getPublicKey().toString())
        self.set_prompt()

    def do_topic(self, arg):
        """HCS Topic: create send
Create Topic:
    topic create [memo]
Send message:
    topic send topic_id message [[messages]]"""
        args = arg.split()
        if not args or args[0] not in ('create', 'send'):
            return self.err_return("invalid topic command")

        if args[0] == "create":
            txn = TopicCreateTransaction()
            if len(args) > 1:
                memo = " ".join(args[1:])
                txn.setTopicMemo(memo)
            try:
                receipt = txn.execute(self.client).getReceipt(self.client)
                print("New topic created: ", receipt.topicId.toString())
            except Exception as e:
                print(e)
        else:
            if len(args) < 3:
                print(Fore.RED + "need topicId and message")
            else:
                try:
                    topicId = TopicId.fromString(args[1])
                    txn = (TopicMessageSubmitTransaction()
                           .setTopicId(topicId)
                           .setMessage(" ".join(args[2:])))
                    receipt = txn.execute(self.client).getReceipt(self.client)
                    print("message sent, sequence #: ", receipt.topicSequenceNumber)
                except Exception as e:
                    print(e)
        self.set_prompt()

    def do_account(self, arg):
        """account: create | balance | delete | info
Create account:
    account create
account balance:
    account balance [accountid]"""
        args = arg.split()
        if not args or args[0] not in ('create', 'balance', 'delete', 'info'):
            return self.err_return("invalid account command")

        if args[0] == "balance":
            try:
                if len(args) > 1:
                    accountId = AccountId.fromString(args[1])
                else:
                    accountId = self.operator_id
                balance = AccountBalanceQuery().setAccountId(accountId).execute(self.client)
                print("Hbar balance for {}: {}".format(accountId.toString(), balance.hbars.toString()))
                tokens = balance.tokens
                for tokenId in tokens.keySet().toArray():
                    print("Token {} = {}".format(tokenId.toString(), tokens[tokenId]))
            except Exception as e:
                print(e)
        elif args[0] == "create":
            initHbars = int(input("Set initial Hbars > "))
            prikey = PrivateKey.generate()
            print(Fore.YELLOW + "New Private Key: " + Fore.GREEN + prikey.toString())
            txn = (AccountCreateTransaction()
                   .setKey(prikey.getPublicKey())
                   .setInitialBalance(Hbar(initHbars))
                   .execute(self.client))
            receipt = txn.getReceipt(self.client)
            print(Fore.YELLOW + "New AccountId: " + Fore.GREEN + receipt.accountId.toString())
        elif args[0] == "delete":
            if len(args) != 2:
                print(Fore.RED + "need accountId")
            else:
                accountId = AccountId.fromString(args[1])
                prikey = PrivateKey.fromString(input("Enter this account's private key > "))
                txn = (AccountDeleteTransaction()
                       .setAccountId(accountId)
                       .setTransferAccountId(self.operator_id)
                       .setTransactionId(TransactionId.generate(accountId))
                       .freezeWith(self.client)
                       .sign(prikey)
                       .execute(self.client))
                txn.getReceipt(self.client)
                print(Fore.YELLOW + "account deleted!" + Fore.GREEN + txn.transactionId.toString())

        self.set_prompt()

    def do_send(self, arg):
        """send Hbars to another account:
send 0.0.12345 10
(send 10 hbars to account 0.0.12345)"""
        try:
            accountId = AccountId.fromString(input("Receipient account id: > "))
            hbars = input("amount of Hbars(minimum is 0.00000001): > ")
            amount = Hbar.fromTinybars(int(float(hbars) * 100_000_000))
            txn = (TransferTransaction()
                   .addHbarTransfer(self.operator_id, amount.negated())
                   .addHbarTransfer(accountId, amount)
                   .execute(self.client))
            print(Fore.YELLOW + "Hbar sent!" + Fore.GREEN + txn.transactionId.toString())
        except Exception as e:
            print(e)

        self.set_prompt()

    def get_local_file_content(self, filepath, cur_size=0):
        if not os.path.isfile(filepath):
            self.err_return("file {} does not exist".format(filepath))
            return None, 0
        filesize = os.path.getsize(filepath)
        if (filesize + cur_size) > 1024 * 1000:
            self.err_return("file is too large, the maximum file size is 1024 kB")
            return None, 0

        with open(filepath) as fh:
            return fh.read(), filesize

    def get_content_from_input(self):
        print("Enter your file content line by line, enter EOF to finish:\n") 
        lines = []
        while True:
            line = input()
            if line.strip() == "EOF":
                break
            lines.append(line)
        contents = '\n'.join(lines)
        filesize = len(contents)
        return contents, filesize

    def do_file(self, arg):
        """Hedera File Service: create | contents | append | delete
        file create [file_path]
        file info fileId
        file contents fileId
        file append fileId [file_path]
        file delete fileId
        """
        args = arg.split()
        if not args or args[0] not in ('create', 'contents', 'info', 'append', 'delete'):
            return self.err_return("invalid file command")

        if args[0] == "create":
            if len(args) > 1:
                contents, filesize = self.get_local_file_content(args[1])
                if not contents:
                    return
            else:
                contents, filesize = self.get_content_from_input()
                if filesize == 0:
                    return self.err_return("no content")

            # calculate price
            # single sig only
            # use 0.039 + $0.011 per 1kB
            cost = 0.039 + 0.011 * math.ceil(filesize / 1000.0)
            self.hbar_price = get_Hbar_price()
            cost_in_hbar = cost / self.hbar_price 
            answer = input("It will cost about {:.5f} hbars to create this file, is this OK? type yes or no: ".format(cost_in_hbar))
            if answer.lower() == "yes":
                first_chunk = contents if filesize <= FILE_CREATE_SIZE else contents[:FILE_CREATE_SIZE]
                try:
                    txn = (FileCreateTransaction()
                           .setKeys(self.operator_key.getPublicKey())
                           .setContents(first_chunk)
                           .setMaxTransactionFee(Hbar(1))
                           .execute(self.client))
                    receipt = txn.getReceipt(self.client)
                    fileId = receipt.fileId

                    if filesize > FILE_CREATE_SIZE:
                        num_chunks = math.ceil((filesize - FILE_CREATE_SIZE) / CHUNK_SIZE)
                        max_cost = math.ceil(cost_in_hbar)
                        txn = (FileAppendTransaction()
                               .setNodeAccountIds(NODE_LIST)
                               .setFileId(fileId)
                               .setContents(contents[FILE_CREATE_SIZE:])
                               .setMaxChunks(num_chunks)
                               .setMaxTransactionFee(Hbar(max_cost))
                               .freezeWith(self.client)
                               .execute(self.client))
                        receipt = txn.getReceipt(self.client)

                    print("File created.  FileId =", fileId.toString())

                except Exception as e:
                    print(e)

            else:
                print("canceled")

        elif args[0] == "append":
            if len(args) < 2:
                return self.err_return("fileId is needed")
            
            try:
                fileId = FileId.fromString(args[1])
                info = FileInfoQuery().setFileId(fileId).execute(self.client)
                print("filesize before appending is ", info.size)

                if len(args) > 2:
                    contents, filesize = self.get_local_file_content(args[2], info.size)
                    if not contents:
                        return
                else:
                    contents, filesize = self.get_content_from_input()
                    if filesize == 0:
                        return self.err_return("no content")

                cost = 0.039 + 0.011 * math.ceil(filesize / 1000.0)
                self.hbar_price = get_Hbar_price()
                cost_in_hbar = cost / self.hbar_price
                max_cost = math.ceil(cost_in_hbar + 0.5)  # 0.5 is margin 
                answer = input("It will cost about {:.5f} hbars to append to this file, is this OK? type yes or no: ".format(cost_in_hbar))
                if answer.lower() == "yes":
                    num_chunks = math.ceil(filesize / CHUNK_SIZE)
                    txn = (FileAppendTransaction()
                           .setNodeAccountIds(NODE_LIST)
                           .setFileId(fileId)
                           .setContents(contents)
                           .setMaxChunks(num_chunks)
                           .setMaxTransactionFee(Hbar(max_cost))
                           .freezeWith(self.client)
                           .execute(self.client))
                    receipt = txn.getReceipt(self.client)
                    print("File appended")
                else:
                    print("canceled")

            except Exception as e:
                print(e)

        elif args[0] == "info":
            if len(args) < 2:
                return self.err_return("fileId is needed")
            
            try:
                fileId = FileId.fromString(args[1])
                info = FileInfoQuery().setFileId(fileId).execute(self.client)
                print("file memo:", info.fileMemo)
                print("file size:", info.size)
                print("expires:", info.expirationTime.toString())
            except Exception as e:
                print(e)

        elif args[0] == "contents":
            if len(args) < 2:
                return self.err_return("fileId is needed")
            
            try:
                fileId = FileId.fromString(args[1])
                resp = FileContentsQuery().setFileId(fileId).execute(self.client)
                contents = resp.toStringUtf8()
                with open(args[1], 'w') as fh:
                    fh.write(contents)
                print()
                print(Fore.GREEN + "file is saved as {}.  Here is a preview:".format(args[1]))
                print(Style.RESET_ALL)
                print(contents[:1024])
                print()
            except Exception as e:
                print(e)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        dotenv = sys.argv[1]
    else:
        dotenv = ".env"
    load_dotenv(dotenv)
    HederaCli().cmdloop()
