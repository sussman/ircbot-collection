#!/usr/bin/env python
#
# IRC Bot to moderate a game of "Werewolf".
#
#    By Ben Collins-Sussman <sussman@red-bean.com>
#
# Werewolf rules:  http://www.eblong.com/zarf/werewolf.html
#
# Originally based on example bot and irc-bot class from
# Joel Rosdahl <joel@rosdahl.net>, author of included python-irclib.
#


"""An IRC bot to moderate a game of "Werewolf".

This is an example bot that uses the SingleServerIRCBot class from
ircbot.py.  The bot enters a channel and listens for commands in
private messages and channel traffic.  Commands in channel messages
are given by prefixing the text by the bot name followed by a colon.
It also responds to DCC CHAT invitations and echos data sent in such
sessions.

The known commands are:

    die -- Let the bot cease to exist.

    start game -- start a new werewolf game.

    end game -- quit the current werewolf game.

    stats -- print information about living/dead people.
    
"""

import sys, string
from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower

class WolfBot(SingleServerIRCBot):
  def __init__(self, channel, nickname, server, port=6667):
    SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
    self.channel = channel
    self.game_in_progress = 0
    self.live_players = []
    self.dead_players = []
    self.roledict = {}
    self.start()
    
  def on_nicknameinuse(self, c, e):
    c.nick(c.get_nickname() + "_")
      
  def on_welcome(self, c, e):
    c.join(self.channel)

  def on_privmsg(self, c, e):
    self.do_command(e, e.arguments()[0])

  def on_pubmsg(self, c, e):
    a = string.split(e.arguments()[0], ":", 1)
    if len(a) > 1 and irc_lower(a[0]) == irc_lower(self.connection.get_nickname()):
      self.do_command(e, string.strip(a[1]))
    return

  def start_game(self, e):
    nick = nm_to_n(e.source())
    c = self.connection
    if self.game_in_progress:
      c.notice(nick, "A game is already in progress.  Use 'quit game' to end it.")
    else:

      # Build a dictionary that assigns each player to a role.
      chname, chobj = self.channels.items()[0]
      users = chobj.users()
      for user in users:
        pass

      # Private message each user

      c.notice(nick, "The game has started.")
      self.game_in_progress = 1

  def end_game(self, e):
    nick = nm_to_n(e.source())
    c = self.connection
    if not self.game_in_progress:
      c.notice(nick, "No game is in progress.  Use 'start game' to begin a game.")
    else:
      c.notice(nick, "The game has ended.")
      self.game_in_progress = 0

  def do_command(self, e, cmd):
    nick = nm_to_n(e.source())
    c = self.connection
    
    if cmd == "die":
      c.notice(nick, "Ciao!")
      self.die()

    elif cmd == "start game":
      self.start_game(e)
          
    elif cmd == "end game":
      self.end_game(e)
                
    elif cmd == "stats":
      chname, chobj = self.channels.items()[0]
      users = chobj.users()
      
      c.notice(nick, "There are " + `len(users)` + " players in this channel.")
      c.notice(nick, "Living players : " + string.join(self.live_players, ","))
      c.notice(nick, "Dead players : " + string.join(self.dead_players, ","))

    else:
      c.notice(nick, "I don't understand.")



def main():
  
  if len(sys.argv) != 4:
    print "argv is ", sys.argv
    print "len is ", len(sys.argv)
    print "Usage: wolfbot.py <server[:port]> <channel> <nickname>"
    sys.exit(1)

  s = string.split(sys.argv[1], ":", 1)
  server = s[0]
  if len(s) == 2:
    try:
      port = int(s[1])
    except ValueError:
      print "Error: Erroneous port."
      sys.exit(1)
  else:
    port = 6667
  channel = sys.argv[2]
  nickname = sys.argv[3]

  bot = WolfBot(channel, nickname, server, port)
  bot.start()

if __name__ == "__main__":
  main()
