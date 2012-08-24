#!/usr/bin/env python

import os
import sys
import re
import hashlib
import shutil
from subprocess import Popen, PIPE
import shlex

ORIGINAL = 'original'
PATCHED = 'patched'

target = "/System/Library/Extensions/IOAHCIFamily.kext/Contents/PlugIns/IOAHCIBlockStorage.kext/Contents/MacOS/IOAHCIBlockStorage"
backup = "%s.original" % target

md5_version = {
        "25a29cbdbb89329a6ce846c9b05af5f0": ["10.6.8"],
        "155b426c856c854e54936339fbc88d72": ["10.7"],
        "00bd8e1943e09f2bd12468882aad0bbb": ["10.7.1"],
        "38100e96270dcb63d355ea8195364bf5": ["10.7.2"],
        "d2c20ed8211bf5b96c4610450f56c1c3": ["10.7.3"],
        "48e392b3ca7267e1fd3dd50a20396937": ["10.7.4"],
        "ff7a9115779fa5923950cbdc6ffb273d": ["10.8"],
        }
md5_patch = {
        "25a29cbdbb89329a6ce846c9b05af5f0": "d76b57daf4d4c2ff5b52bc7b4b2dcfc1",
        "155b426c856c854e54936339fbc88d72": "945944136009c9228fffb513ab5bf734",
        "00bd8e1943e09f2bd12468882aad0bbb": "155b426c856c854e54936339fbc88d72",
        "38100e96270dcb63d355ea8195364bf5": "5762b2fbb259101c361e5414c349ffa1",
        "d2c20ed8211bf5b96c4610450f56c1c3": "15901d7c6fd99f5dd9c5ca493de6109b",
        "48e392b3ca7267e1fd3dd50a20396937": "a2f64369e775c76be4ec03ce5172a294",
        "ff7a9115779fa5923950cbdc6ffb273d": "4d265ac3f471b0ef0578d5dbb1eafadb",
        }
md5_patch_r = dict((v,k) for k,v in md5_patch.items())

def md5(filename):
    h = hashlib.md5()
    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), ''): 
            h.update(chunk)
    return h.hexdigest()

def backquote(command):
    return Popen(shlex.split(command), stdout=PIPE).communicate()[0]

def check_rootness():
    if os.geteuid() != 0:
        print >> sys.stderr, "you must be root"
        sys.exit(1)

def clear_kext_cache():
    print "clearing kext cache...",
    backquote("kextcache -system-prelinked-kernel")
    backquote("kextcache -system-caches")
    print "done"

class UnknownFile(Exception):
    def __init__(self, md5=None):
        self.md5 = md5

class NoBackup(Exception):
    pass

def target_status():
    h = md5(target)
    try:
        return (ORIGINAL, md5_version[h])
    except KeyError:
        pass
    try:
        return (PATCHED, md5_version[md5_patch_r[h]])
    except KeyError:
        pass
    raise UnknownFile(h)

def backup_status():
    if not os.path.exists(backup):
        raise NoBackup
    h = md5(backup)
    try:
        return (ORIGINAL, md5_version[h])
    except KeyError:
        pass
    try:
        return (PATCHED, md5_version[md5_patch_r[h]])
    except KeyError:
        pass
    raise UnknownFile(h)

def apply_patch():
    search_re = "(\x52\x6F\x74\x61\x74\x69\x6F\x6E\x61\x6C\x00{1,20})[^\x00]{9}(\x00{1,20}[^\x00])"
    replace_re = "\\1\x00\x00\x00\x00\x00\x00\x00\x00\x00\\2"
    with open(target, 'rb') as f:
        source_data = f.read()
    patched_data = re.sub(search_re, replace_re, source_data)
    with open(target, 'wb') as out:
        out.write(patched_data)

def perform_backup():
    shutil.copyfile(target, backup)

def do_backup():
    check_rootness()
    try:
        s, t = target_status()
        if s == PATCHED:
            print "already patched, won't backup"
            sys.exit(1)
        else:
            try:
                _, v = backup_status()
            except NoBackup:
                print "backing up...",
                perform_backup()
                print "done"
            else:
                if v == t:
                    print "backup found"
                else:
                    print "backing up...",
                    perform_backup()
                    print "done"
    except UnknownFile as e:
        print "unknown file, won't backup (md5=%s)" % e.md5
        sys.exit(1)

def do_restore():
    check_rootness()
    print "restoring...",
    backup_status()
    shutil.copyfile(backup, target)
    print "done"
    clear_kext_cache()

def do_apply():
    check_rootness()
    do_backup()
    try:
        s, v = target_status()
        if s == PATCHED:
            print "already patched"
            sys.exit()
    except UnknownFile as e:
        print "unknown file: won't patch (md5=%s)" % e.md5
        sys.exit(1)
    
    print "patching...",
    apply_patch()
    
    try:
        s, v = target_status()
        if s != PATCHED:
            print "no change made"
        else:
            print "done"
            clear_kext_cache()
    except UnknownFile as e:
        print "failed (md5=%s), " % e.md5,
        do_restore()

def do_status():
    try:
        print "target:",
        s, v = target_status()
        print s+',', ' or '.join(v)
    except UnknownFile as e:
        print "unknown (md5=%s)" % e.md5
    try:
        print "backup:",
        s, v = backup_status()
        print s+',', ' or '.join(v)
    except NoBackup:
        print "none"
    except UnknownFile as e:
        print "unknown (md5=%s)" % e.md5

def do_diff():
    try:
        backup_status()
    except NoBackup:
        print "no backup"
    else:
        command = "bash -c 'diff <(xxd \"%s\") <(xxd \"%s\")'" % (backup, target)
        print os.system(command)

commands = {
        'status': do_status,
        'backup': do_backup,
        'apply': do_apply,
        'restore': do_restore,
        'diff': do_diff,
        }

try:
    function = commands[sys.argv[1]]
    function()
except IndexError:
    print >> sys.stderr, "no command provided"
    print >> sys.stderr, "list of commands: %s" % ', '.join(commands.keys())
    sys.exit(1)
except KeyError:
    print >> sys.stderr, "unknown command"
    sys.exit(1)


