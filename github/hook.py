# trac-post-commit-hook
# ----------------------------------------------------------------------------
# Copyright (c) 2004 Stephen Hansen 
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software. 
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
# ----------------------------------------------------------------------------
#
# It searches commit messages for text in the form of:
#   command #1
#   command #1, #2
#   command #1 & #2 
#   command #1 and #2
#
# Instead of the short-hand syntax "#1", "ticket:1" can be used as well, e.g.:
#   command ticket:1
#   command ticket:1, ticket:2
#   command ticket:1 & ticket:2 
#   command ticket:1 and ticket:2
#
# In addition, the ':' character can be omitted and issue or bug can be used
# instead of ticket.
#
# You can have more then one command in a message. The following commands
# are supported. There is more then one spelling for each command, to make
# this as user-friendly as possible.
#
#   close, closed, closes, fix, fixed, fixes
#     The specified issue numbers are closed with the contents of this
#     commit message being added to it. 
#   references, refs, ref, addresses, re, see 
#     The specified issue numbers are left in their current status, but 
#     the contents of this commit message are added to their notes. 
#
# A fairly complicated example of what you can do is with a commit message
# of:
#
#    Changed blah and foo to do this or that. Fixes #10 and #12, and refs #12.
#
# This will close #10 and #12, and add a note to #12.

import re
import os
import sys
from datetime import datetime

from trac.env import open_environment

# TODO: move grouped_changelog_entries to model.py
from trac.util.text import to_unicode
from trac.util.datefmt import utc

from agilo.ticket.model import AgiloTicket, AgiloTicketModelManager
from agilo.utils import Key, Status
from agilo.utils.errors import *
from agilo.utils.config import AgiloConfig

ticket_prefix = '(?:#|(?:ticket|issue|bug)[: ]?)'
ticket_reference = ticket_prefix + '[0-9]+'
ticket_command = (r'(?P<action>[A-Za-z]*).?'
                   '(?P<ticket>%s(?:(?:[, &]*|[ ]?and[ ]?)%s)*)' %
                   (ticket_reference, ticket_reference))
     
command_re = re.compile(ticket_command)
ticket_re = re.compile(ticket_prefix + '([0-9]+)')

class CommitHook:
    _supported_cmds = {'close':      '_cmdClose',
                       'closed':     '_cmdClose',
                       'closes':     '_cmdClose',
                       'fix':        '_cmdClose',
                       'fixed':      '_cmdClose',
                       'fixes':      '_cmdClose',
                       'addresses':  '_cmdRefs',
                       're':         '_cmdRefs',
                       'references': '_cmdRefs',
                       'refs':       '_cmdRefs',
                       'ref':       '_cmdRefs',
                       'see':        '_cmdRefs'}


    def __init__(self, env):
        self.env = env
        self.tm = AgiloTicketModelManager(self.env)

    def process(self, commit, status, jsondata):
        self.closestatus = status
        
        msg = commit['message']
        self.env.log.debug("Processing a Commit: %s", msg)
        note = "Changeset: [/changeset/%(repo)s/commit/%(id)s %(repo)s/%(id)s]" % { 'repo': jsondata['repository']['name'], 'id': commit['id']}
        self.msg = "%s \n %s" % (msg, note)
        self.author = commit['author']['name']
        
        cmd_groups = command_re.findall(self.msg)
        self.env.log.debug("Function Handlers: %s" % cmd_groups)

        tickets = {}
        for cmd, tkts in cmd_groups:
            funcname = self.__class__._supported_cmds.get(cmd.lower(), '')
            self.env.log.debug("Function Handler: %s" % funcname)
            if funcname:
                for tkt_id in ticket_re.findall(tkts):
                    func = getattr(self, funcname)
                    tickets.setdefault(int(tkt_id), []).append(func)

        for t_id, cmds in tickets.iteritems():
            ticket = self.tm.get(tkt_id=t_id)
            for cmd in cmds:
                cmd(ticket)

            self.tm.save(ticket, author=self.author, comment=self.msg)
            from trac.ticket.notification import TicketNotifyEmail
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=False, modtime=ticket.time_changed)				


    def _cmdClose(self, ticket):
        """
        Closes a ticket and applies all the defined rules
        """
        if isinstance(ticket, AgiloTicket):
            if ticket.is_writeable_field(Key.REMAINING_TIME):
                owner = ticket[Key.OWNER]
                ticket[Key.STATUS] = Status.CLOSED
                ticket[Key.RESOLUTION] = Status.RES_FIXED
                ticket[Key.REMAINING_TIME] = '0'
            else:
                # Check if all the linked items are closed than close it
                close = True
                for linked in ticket.get_outgoing():
                    if linked[Key.STATUS] != Status.CLOSED:
                        close = False
                        break
                if close:
                    ticket[Key.STATUS] = Status.CLOSED
                    ticket[Key.RESOLUTION] = Status.RES_FIXED
                else:
                    self.env.log.info("The ticket(#%d) of type: '%s' has still "\
                            "some open dependencies... can't close it!" % \
                            (ticket.get_id(), ticket.get_type()))
                    # Return the method

    def _cmdRefs(self, ticket):
        pass
