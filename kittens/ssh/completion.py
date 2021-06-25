#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPLv3 Copyright: 2021, Kovid Goyal <kovid at kovidgoyal.net>

import os
import re
import subprocess
from typing import Callable, Dict, Iterable, Iterator, Sequence, Tuple

from kitty.complete import Completions, debug
from kitty.types import run_once

debug


def lines_from_file(path: str) -> Iterator[str]:
    try:
        f = open(os.path.expanduser(path))
    except OSError:
        pass
    else:
        yield from f


def lines_from_command(*cmd: str) -> Iterator[str]:
    try:
        output = subprocess.check_output(cmd).decode('utf-8')
    except Exception:
        return
    yield from output.splitlines()


def parts_yielder(lines: Iterable[str], pfilter: Callable[[str], Iterator[str]]) -> Iterator[str]:
    for line in lines:
        yield from pfilter(line)


def hosts_from_config_lines(line: str) -> Iterator[str]:
    parts = line.strip().split()
    if len(parts) > 1 and parts[0] == 'Host':
        yield parts[1]


def hosts_from_known_hosts(line: str) -> Iterator[str]:
    parts = line.strip().split()
    if parts:
        yield re.sub(r':\d+$', '', parts[0])


def hosts_from_hosts(line: str) -> Iterator[str]:
    line = line.strip()
    if not line.startswith('#'):
        parts = line.split()
        if parts:
            yield parts[0]
        if len(parts) > 1:
            yield parts[1]
        if len(parts) > 2:
            yield parts[2]


def iter_known_hosts() -> Iterator[str]:
    yield from parts_yielder(lines_from_file('~/.ssh/config'), hosts_from_config_lines)
    yield from parts_yielder(lines_from_file('~/.ssh/known_hosts'), hosts_from_known_hosts)
    yield from parts_yielder(lines_from_file('/etc/ssh/ssh_known_hosts'), hosts_from_known_hosts)
    yield from parts_yielder(lines_from_file('/etc/hosts'), hosts_from_hosts)
    yield from parts_yielder(lines_from_command('getent', 'hosts'), hosts_from_hosts)


@run_once
def known_hosts() -> Tuple[str, ...]:
    return tuple(sorted(filter(lambda x: '*' not in x and '[' not in x, set(iter_known_hosts()))))


@run_once
def ssh_options() -> Dict[str, str]:
    stderr = subprocess.Popen(['ssh'], stderr=subprocess.PIPE).stderr
    assert stderr is not None
    raw = stderr.read().decode('utf-8')
    ans: Dict[str, str] = {}
    pos = 0
    while True:
        pos = raw.find('[', pos)
        if pos < 0:
            break
        num = 1
        epos = pos
        while num > 0:
            epos += 1
            if raw[epos] not in '[]':
                continue
            num += 1 if raw[epos] == '[' else -1
        q = raw[pos+1:epos]
        pos = epos
        if len(q) < 2 or q[0] != '-':
            continue
        if ' ' in q:
            opt, desc = q.split(' ', 1)
            ans[opt[1:]] = desc
        else:
            ans.update(dict.fromkeys(q[1:], ''))
    return ans


# option help {{{
@run_once
def option_help_map() -> Dict[str, str]:
    ans: Dict[str, str] = {}
    lines = '''
-4  -- force ssh to use IPv4 addresses only
-6  -- force ssh to use IPv6 addresses only
-a  -- disable forwarding of authentication agent connection
-A  -- enable forwarding of the authentication agent connection
-B  -- bind to specified interface before attempting to connect
-b  -- specify interface to transmit on
-C  -- compress data
-c  -- select encryption cipher
-D  -- specify a dynamic port forwarding
-E  -- append log output to file instead of stderr
-e  -- set escape character
-f  -- go to background
-F  -- specify alternate config file
-g  -- allow remote hosts to connect to local forwarded ports
-G  -- output configuration and exit
-i  -- select identity file
-I  -- specify smartcard device
-J  -- connect via a jump host
-k  -- disable forwarding of GSSAPI credentials
-K  -- enable GSSAPI-based authentication and forwarding
-L  -- specify local port forwarding
-l  -- specify login name
-M  -- master mode for connection sharing
-m  -- specify mac algorithms
-N  -- don't execute a remote command
-n  -- redirect stdin from /dev/null
-O  -- control an active connection multiplexing master process
-o  -- specify extra options
-p  -- specify port on remote host
-P  -- use non privileged port
-Q  -- query parameters
-q  -- quiet operation
-R  -- specify remote port forwarding
-s  -- invoke subsystem
-S  -- specify location of control socket for connection sharing
-T  -- disable pseudo-tty allocation
-t  -- force pseudo-tty allocation
-V  -- show version number
-v  -- verbose mode (multiple increase verbosity, up to 3)
-W  -- forward standard input and output to host
-w  -- request tunnel device forwarding
-x  -- disable X11 forwarding
-X  -- enable (untrusted) X11 forwarding
-Y  -- enable trusted X11 forwarding
-y  -- send log info via syslog instead of stderr
'''.splitlines()
    for line in lines:
        line = line.strip()
        if line:
            parts = line.split(maxsplit=2)
            ans[parts[0]] = parts[2]
    return ans
# }}}


def complete_arg(ans: Completions, option_flag: str, prefix: str = '') -> None:
    pass


def complete_destination(ans: Completions, prefix: str = '') -> None:
    result = {k: '' for k in known_hosts() if k.startswith(prefix)}
    ans.match_groups['remote host name'] = result


def complete_option(ans: Completions, prefix: str = '-') -> None:
    hm = option_help_map()
    if len(prefix) <= 1:
        result = {k: v for k, v in hm.items() if k.startswith(prefix)}
        ans.match_groups['option'] = result
    else:
        ans.match_groups['option'] = {prefix: ''}


def complete(ans: Completions, words: Sequence[str], new_word: bool) -> None:
    options = ssh_options()
    expecting_arg = False
    types = ['' for i in range(len(words))]
    for i, word in enumerate(words):
        if expecting_arg:
            types[i] = 'arg'
            expecting_arg = False
            continue
        if word.startswith('-'):
            types[i] = 'option'
            if len(word) == 2 and options.get(word[1]):
                expecting_arg = True
            continue
        types[i] = 'destination'
        break
    if new_word:
        if words:
            if expecting_arg:
                return complete_arg(ans, words[-1])
        return complete_destination(ans)
    if words:
        if types[-1] == 'arg' and len(words) > 1:
            return complete_arg(ans, words[-2], words[-1])
        if types[-1] == 'destination':
            return complete_destination(ans, words[-1])
        if types[-1] == 'option':
            return complete_option(ans, words[-1])