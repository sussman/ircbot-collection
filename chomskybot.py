#!/usr/bin/env python
#
# IRC Bot to give responses as "Pinky", based on "Pinky and the Brain".
#
# Code originally based on example bot and irc-bot class from
# Joel Rosdahl <joel@rosdahl.net>, author of included python-irclib.
#


"""An IRC bot that just gives Noam Chomsky quotes when addressed.
"""
import os
import sys, string, random, time
from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower
import botcommon
import logging
import quote_scrape

class ChomskyBot(SingleServerIRCBot):
  def __init__(self, quotes, channel, nickname, server, port):
    SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
    self.quotes = quotes
    self.channel = channel
    self.nickname = nickname
    self.queue = botcommon.OutputManager(self.connection)
    self.queue.start()
    self.start()

  def on_welcome(self, c, e):
    c.join(self.channel)

  def on_pubmsg(self, c, e):
    from_nick = nm_to_n(e.source())
    a = string.split(e.arguments()[0], ":", 1)
    if len(a) > 1 \
      and irc_lower(a[0]) == irc_lower(self.nickname):
      self.do_command(e, string.strip(a[1]), from_nick)
    return

  def do_command(self, e, cmd, from_private):
    """This is the function called whenever someone sends a public or
    private message addressed to the bot. (e.g. "bot: blah").  Parse
    the CMD, execute it, then reply either to public channel or via
    /msg, based on how the command was received.  E is the original
    event, and FROM_PRIVATE is the nick that sent the message."""
    text = random.choice(self.quotes)
    self.queue.send(text, self.channel)


def main():
  logging.basicConfig(level=logging.DEBUG)
  args = sys.argv[1:]
  if len(args) != 4:
    sys.exit('usage: <script> server port channel nickname')
    return

  server, port, channel, nickname = args
  quotes = quote_scrape.ScrapeQuotes(2476)

  try:
    bot = ChomskyBot(quotes, channel, nickname, server, int(port))
    bot.start()
  except KeyboardInterrupt:
    print "Shutting down."

if __name__ == "__main__":
  main()
