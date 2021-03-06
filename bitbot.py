#!/usr/bin/env python
#
# BIT!  Tron!  BIT!
#
# Code originally based on example bot and irc-bot class from
# Joel Rosdahl <joel@rosdahl.net>, author of included python-irclib.
#


"""An IRC bot to be BIT.  Go watch the Tron movie.
"""

import sys, string, random, time
from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower
import botcommon

#--------------------------------------------------------------------
# What to say when someone makes a declaration to bitbot.

exclamations = \
[
 "YES",
 "NO",
 "YES",
 "NO",
 "YES",
 "NO",
 "YES YES YES YES YES YES",
 "NO",
 "YES",
 "NO",
 "YES",
 "NO NO NO NO NO NO NO",
]


#--------------------------------------------------------------------
# What to say when someone asks bitbot a question.

ponderings = \
[
 "YES",
 "NO",
 "YES",
 "NO",
 "YES",
 "NO",
 "YES YES YES YES YES YES",
 "NO",
 "YES",
 "NO",
 "YES",
 "NO NO NO NO NO NO NO",
]


#---------------------------------------------------------------------
# Actual code.
#
# This bot subclasses a basic 'bot' class, which subclasses a basic
# IRC-client class, which uses the python-irc library.  Thanks to Joel
# Rosdahl for the great framework!


class BitBot(SingleServerIRCBot):
  def __init__(self, channel, nickname, server, port):
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

  def ponder_something(self):
    "Return a random string indicating what sussman's pondering."
    return random.choice(ponderings)

  def exclaim_something(self):
    "Return a random exclamation string."
    return random.choice(exclamations)

  def do_command(self, e, cmd, from_private):
    """This is the function called whenever someone sends a public or
    private message addressed to the bot. (e.g. "bot: blah").  Parse
    the CMD, execute it, then reply either to public channel or via
    /msg, based on how the command was received.  E is the original
    event, and FROM_PRIVATE is the nick that sent the message."""

    if e.eventtype() == "pubmsg":
      # self.reply() sees 'from_private = None' and sends to public channel.
      target = None
    else:
      # assume that from_private comes from a 'privmsg' event.
      target = from_private.strip()

    # pause before replying, for believable effect:
    time.sleep(random.randrange(4, 12))

    if cmd[-1] == '?':
      self.reply(self.ponder_something(), target)
    else:
      self.reply(self.exclaim_something(), target)


if __name__ == "__main__":
  try:
    botcommon.trivial_bot_main(BitBot)
  except KeyboardInterrupt:
    print "Shutting down."

