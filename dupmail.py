#!/usr/bin/env python3

import mailbox
import email.header
import email.iterators
import email.utils
import hashlib
import itertools
import re
import sys
import argparse

def print_result(*args, **kwargs):
    print(*args, **kwargs)
    
def print_info(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

class Email:
    def __init__(self, id, data):
        self.id = id
        self.data = data
    
    def fails(self):
        count = 0
        for value in self.data.values():
            if isinstance(value,int):
                if value == 0:
                    count += 1
            else:
                if len(value) == 0:
                    count += 1
        return count
    
    def __str__(self):
        return "|" + "|".join([str(self.data[key]) for key in sorted(self.data)]) + "|"
    
    def hash(self):
        return hashlib.sha256(str(self).encode()).hexdigest()

class EmailParser:
    key_method_prefix = "process_"
    
    @staticmethod
    def parse(eml, keys, id):
        parser = EmailParser(eml, keys)
        email = Email(id, parser.data())
        return email
    
    @classmethod
    def valid_keys(cls):
        prefix = cls.key_method_prefix
        return [m[len(prefix):] for m in dir(cls) if m.startswith(prefix)]
    
    def __init__(self, eml, keys):
        self._eml = eml
        self._data = {}
        for key in keys:
            self._data[key] = self.process(key)
    
    def data(self):
        return self._data
    
    def process(self, key):
        func = getattr(self, EmailParser.key_method_prefix+key)
        return func()
    
    def process_from(self):
        return self.parse_emails(self._eml.get_all("from", []))
    
    def process_to(self):
        emails = self._eml.get_all("to", []) + \
                 self._eml.get_all("cc", []) + \
                 self._eml.get_all("bcc", [])
        return self.parse_emails(emails)
    
    def process_subject(self):
        return self.parse_string_flat(self._eml.get("subject", ""))
    
    def process_date(self):
        return self.parse_date(self._eml.get("date", ""))
    
    def process_body_size(self):
        size = 0
        for line in self.body():
            size = size + len(line)
        return size
    
    def process_body_lines(self):
        lines = 0
        for line in self.body():
            lines += 1
        return lines
    
    def process_body_hash(self):
        hashx = hashlib.sha256()
        [hashx.update(line.encode) for line in self.body()]
        return hashx.hexdigest()
    
    def parse_string(self, header, encoding="utf-8"):
        if type(header) is str:
            return header
        elif type(header) is bytes:
            try:
                return header.decode(encoding)
            except:
                if encoding != "utf-8":
                    return self.parse_string(header, "utf-8")
                else:
                    return ""
        elif type(header) is email.header.Header:
            value, header_encoding = email.header.decode_header(header)[0]
            return self.parse_string(value, header_encoding)
        else:
            print_info("invalid string type: %s %s"%(header, header.__classs__))
            return ""
    
    def parse_string_flat(self, header):
        value = self.parse_string(header)
        return re.sub("\s\s+", " ", value.strip().lower())
    
    def parse_emails(self, headers):
        addresses = set()
        for header in headers:
            (_, addr) = email.utils.parseaddr(self.parse_string_flat(header))
            if len(addr) > 0:
                addresses.add(addr.lower())
        return " ".join(sorted(addresses))
    
    def parse_date(self, header):
        try:
            return email.utils.parsedate_to_datetime(header).strftime("%Y-%m-%d")
        except:
            return ""
    
    def body(self):
        for line in email.iterators.body_line_iterator(self._eml):
            l = re.sub("\s", "", line)
            if len(l) > 0:
                yield l

class EmailDups:
    def __init__(self, path, keys, fail_at):
        self.mbox = mailbox.Maildir(path)
        self.keys = keys
        self.fail_at = fail_at
        self.dups = {}
    
    def calculate(self):
        dups = {}
        print_info("calculating maildir size")
        total = len(self.mbox)
        i = 0
        for id, eml in self.mbox.iteritems():
            i += 1
            print_info("processing %d/%d emails"%(i, total), end="\r")
            emlhash = EmailParser.parse(eml, keys, id)
            fails = emlhash.fails()
            if fails >= self.fail_at:
                print_info("skipping email %s with %d fails"%(id, fails))
                continue
            xhash = emlhash.hash()
            if not xhash in dups:
                dups[xhash] = []
            dups[xhash].append(emlhash)
        
        for key in list(dups.keys()):
            if len(dups[key]) <= 1:
                dups.pop(key, None)
        
        self.dups = dups
        print_info("")
    
    def count(self):
        count = 0
        for dup in self.dups.values():
            count = count + len(dup)-1
        return count

parser = argparse.ArgumentParser(description="find duplicate emails",
                                 formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-f", "--fail-at", default=2, type=int,
                    help="skip emails if unable to parse at least FAIL_AT fields")
parser.add_argument("-k", "--keys", nargs=1, default="from,to,date,subject,body_lines",
                    help="comma separated list of field names used to identify duplicates")
parser.add_argument("path", help="maildir path")
args = parser.parse_args()

keys = args.keys.split(",")
if not keys:
    parser.error("invalid number of KEYS")

for key in keys:
    if key not in EmailParser.valid_keys():
        parser.error("invalid KEY: %s"%(key))

emaildups = EmailDups(args.path, keys, args.fail_at)
emaildups.calculate()
print("%d dupmails found"%(emaildups.count()))
