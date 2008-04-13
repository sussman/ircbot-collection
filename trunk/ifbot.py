#!/usr/bin/env python
#
# A python IRC bot that plays interactive fiction into a channel.
# This is currently a hack; the python code speaks to a 'dumbfrotz'
# stdio-only z-machine (C program) over a pipe.
#
# To try it out,
#   1. build the dumb-frotz binary via "cc -o dumb-frotz *.c".
#   2. install the 'pexpect' module from
#      http://pexpect.sourceforge.net/pexpect-2.3.tar.gz, and then do the
#      usual 'sudo python ./setup.py install'
#   3. Set the frotz_binary and story_file global vars below.
#
# Code originally based on example bot and irc-bot class from
# Joel Rosdahl <joel@rosdahl.net>, author of included python-irclib.
#

"""An IRC bot to spew a text adventure into a channel.
"""

import sys, string, random, time
from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower
import botcommon

# This is not a standard python module; see instructions above.
import pexpect

# Hackity hack hack hack:  need to make this less fragile!
prompts = ["\n>", "\n> >","to begin]", "\n\*\*\*MORE\*\*\*"]

# Set these to something sensible
frotz_binary = "./dumb-frotz/dumb-frotz"
story_file = "/Users/sussman/projects/public_html/if/shortlist-games/zork1.z3"


#---------------------------------------------------------------------
# Actual code.
#
# This bot subclasses a basic 'bot' class, which subclasses a basic
# IRC-client class, which uses the python-irc library.  Thanks to Joel
# Rosdahl for the great framework!


class IFBot(SingleServerIRCBot):
  def __init__(self, channel, nickname, server, port):
    self.child = pexpect.spawn(frotz_binary + " " + story_file)
    SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
    self.channel = channel
    self.nickname = nickname
    self.queue = botcommon.OutputManager(self.connection)
    self.queue.start()
    self.start()

  def on_nicknameinuse(self, c, e):
    self.nickname = c.get_nickname() + "_"
    c.nick(self.nickname)

  def on_welcome(self, c, e):
    c.join(self.channel)
    self.child.expect(prompts)
    for line in self.child.before.splitlines():
      self.reply(line)
    print self.child.before

  def on_privmsg(self, c, e):
    from_nick = nm_to_n(e.source())
    self.do_command(e, e.arguments()[0], from_nick)

  def on_pubmsg(self, c, e):
    from_nick = nm_to_n(e.source())
    a = string.split(e.arguments()[0], ":", 1)
    if len(a) > 1 \
      and irc_lower(a[0]) == irc_lower(self.nickname):
      self.do_command(e, string.strip(a[1]), from_nick)
    return

  def say_public(self, text):
    "Print TEXT into public channel, for all to see."
    self.queue.send(text, self.channel)

  def say_private(self, nick, text):
    "Send private message of TEXT to NICK."
    self.queue.send(text,nick)

  def reply(self, text, to_private=None):
    "Send TEXT to either public channel or TO_PRIVATE nick (if defined)."

    if to_private is not None:
      self.say_private(to_private, text)
    else:
      self.say_public(text)

  def do_command(self, e, cmd, from_private):
    """This is the function called whenever someone sends a public or
    private message addressed to the bot. (e.g. "bot: blah").  Parse
    the CMD, execute it, then reply either to public channel or via
    /msg, based on how the command was received.  E is the original
    event, and FROM_PRIVATE is the nick that sent the message."""

    if e.eventtype() != "pubmsg":
      target = from_private.strip()
      self.reply("Sorry, I don't do private conversations.  :-)", target)
    else:
      self.child.sendline(cmd)
      self.child.expect(prompts)
      for line in self.child.before.splitlines():
        self.reply(line)
      print self.child.before


if __name__ == "__main__":
  try:
    botcommon.trivial_bot_main(IFBot)
  except KeyboardInterrupt:
    print "Shutting down."

