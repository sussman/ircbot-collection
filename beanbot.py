#!/usr/bin/env python
#
# Simple IRC Bot to announce messages
#
# Code originally based on example bot and irc-bot class from
# Joel Rosdahl <joel@rosdahl.net>, author of included python-irclib.
#


"""An IRC bot to announce messages on a channel.

This is an example bot that uses the SingleServerIRCBot class from
ircbot.py.  The bot enters a channel and relays messages fed to it
via some means (currently UDP).

"""

import sys, string, random, time, os, fcntl
from ircbot import SingleServerIRCBot
import irclib
from irclib import nm_to_n, nm_to_h, irc_lower, parse_channel_modes
from botcommon import OutputManager
from threading import Thread

svn_url = \
"$URL$"
svn_url = svn_url[svn_url.find(' ')+1:svn_url.rfind('/')+1]

class Bot(SingleServerIRCBot):
  def __init__(self, channel, nickname, nickpass, ircaddr, udpaddr,
      debug=False):
    SingleServerIRCBot.__init__(self, [ircaddr], nickname, nickname, 5)
    self.channel = channel
    # self.nickname is the nickname we _want_. The nickname we actually
    # have at any particular time is c.get_nickname().
    self.nickname = nickname
    self.nickpass = nickpass
    self.debug = debug
    self.queue = OutputManager(self.connection, .9)
    self.queue.start()
    self.inputthread = UDPInput(self, udpaddr)
    self.inputthread.start()
    try:
      self.start()
    except KeyboardInterrupt:
      self.connection.quit("Ctrl-C at console")
      print "Quit IRC."
    except Exception, e:
      self.connection.quit("%s: %s" % (e.__class__.__name__, e.args))
      raise


  _uninteresting_events = {
    'all_raw_messages': None,
    'yourhost': None,
    'created': None,
    'myinfo': None,
    'featurelist': None,
    'luserclient': None,
    'luserop': None,
    'luserchannels': None,
    'luserme': None,
    'n_local': None,
    'n_global': None,
    'luserconns': None,
    'motdstart': None,
    'motd': None,
    'endofmotd': None,
    'topic': None,
    'topicinfo': None,
    'ping': None,
    }
  def _dispatcher(self, c, e):
    if self.debug:
      eventtype = e.eventtype()
      if eventtype not in self._uninteresting_events:
        source = e.source()
        if source is not None:
          source = nm_to_n(source)
        else:
          source = ''
        print "E: %s (%s->%s) %s" % (eventtype, source, e.target(),
            e.arguments())
    SingleServerIRCBot._dispatcher(self, c, e)

  def on_nicknameinuse(self, c, e):
    c.nick(c.get_nickname() + "_")

  def on_join(self, c, e):
    nick = nm_to_n(e.source())
    if nick == c.get_nickname():
      chan = e.target()
      self.connection.mode(self.channel, '')

  def on_channelmodeis(self, c, e):
    c._handle_event(
        irclib.Event("mode", e.source(), e.arguments()[0], [e.arguments()[1]]))

  def on_quit(self, c, e):
    source = nm_to_n(e.source())
    if source == self.nickname:
      # Our desired nick just quit - take the nick back
      c.nick(self.nickname)

  def on_welcome(self, c, e):
    c.join(self.channel)
    if self.nickpass and c.get_nickname() != self.nickname:
      # Reclaim our desired nickname
      c.privmsg('nickserv', 'ghost %s %s' % (self.nickname, self.nickpass))

  def on_privnotice(self, c, e):
    source = e.source()
    if source and irc_lower(nm_to_n(source)) == 'nickserv':
      if e.arguments()[0].find('IDENTIFY') >= 0:
        # Received request to identify
        if self.nickpass and self.nickname == c.get_nickname():
          self.queue.send('identify %s' % self.nickpass, 'nickserv')

  def on_privmsg(self, c, e):
    self.do_command(e, e.arguments()[0])

  def on_pubmsg(self, c, e):
    a = string.split(e.arguments()[0], ":", 1)
    if len(a) > 1 and irc_lower(a[0]) == irc_lower(c.get_nickname()):
      self.do_command(e, string.strip(a[1]))

  def say_public(self, text):
    "Print TEXT into public channel, for all to see."
    self.queue.send(text, self.channel)

  def say_private(self, nick, text):
    "Send private message of TEXT to NICK."
    self.queue.send(text,nick)

  def reply(self, e, text):
    "Send TEXT to public channel or as private msg, in reply to event E."
    if e.eventtype() == "pubmsg":
      self.say_public("%s: %s" % (nm_to_n(e.source()), text))
    else:
      self.say_private(nm_to_n(e.source()), text)

  def cmd_help(self, args, e):
    cmds = [i[4:] for i in dir(self) if i.startswith('cmd_')]
    self.reply(e, "Valid commands: '%s'" % "', '".join(cmds))

  #def cmd_renick(self, args, e):
  #  if len(args) != 1:
  #    self.reply(e, "Usage: renick <nick>")
  #    return
  #  self.connection.nick(args[0])

  def cmd_about(self, args, e):
    self.reply(e, "I am a bot written in Python "
        "using the python-irclib library")
    self.reply(e, "My source code is available at %s" % svn_url)

  def do_command(self, e, cmd):
    """This is the function called whenever someone sends a public or
    private message addressed to the bot. (e.g. "bot: blah").  Parse
    the CMD, execute it, then reply either to public channel or via
    /msg, based on how the command was received.  E is the original
    event, and FROM_PRIVATE is the nick that sent the message."""

    cmds = cmd.strip().split(" ")

    try:
      cmd_handler = getattr(self, "cmd_" + cmds[0])
    except AttributeError:
      cmd_handler = None

    if cmd_handler:
      cmd_handler(cmds[1:], e)
      return

    self.reply(e, "I don't understand '%s'."%(cmd))


botname = 'beanbot'

def usage(exitcode=1):
  print "Usage: %s.py [-d] [<config-file>]" % botname
  sys.exit(exitcode)

def parse_host_port(hostport, default_port=None):
  lis = hostport.split(":", 1)
  host = lis[0]
  if len(lis) == 2:
    try:
      port = int(lis[1])
    except ValueError:
      print "Error: Erroneous port."
      sys.exit(1)
  else:
    if default_port is None:
      print "Error: Port required in %s." % hostport
      sys.exit(1)
    port = default_port
  return host, port

def main():
  import getopt

  try:
    opts, args = getopt.gnu_getopt(sys.argv, 'd', ('debug',))
  except getopt.GetoptError:
    usage()

  debug = False
  for opt, val in opts:
    if opt in ('-d', '--debug'):
      debug = True

  if len(args) not in (1, 2):
    usage()

  if len(args) > 1:
    configfile = args[1]
  else:
    configfile = '%s.conf' % botname

  import ConfigParser
  c = ConfigParser.ConfigParser()
  c.read(configfile)
  cfgsect = botname
  ircaddr = parse_host_port(c.get(cfgsect, 'host'), 6667)
  channel = c.get(cfgsect, 'channel')
  nickname = c.get(cfgsect, 'nickname')
  try:
    nickpass = c.get(cfgsect, 'nickpass')
  except ConfigParser.NoOptionError:
    nickpass = None
  udpaddr = parse_host_port(c.get(cfgsect, 'udp-addr'))

  Bot(channel, nickname, nickpass, ircaddr, udpaddr, debug)


class UDPInput(Thread):
  def __init__(self, bot, addr):
    Thread.__init__(self)
    self.setDaemon(1)
    self.bot = bot
    from socket import socket, AF_INET, SOCK_DGRAM
    self.socket = socket(AF_INET, SOCK_DGRAM)
    self.socket.bind(addr)

  def run(self):
    while 1:
      data, addr = self.socket.recvfrom(1024)
      self.bot.say_public(data)

if __name__ == "__main__":
  #try:
  main()
  #except KeyboardInterrupt:
  #  print "Caught Ctrl-C during initialization."
