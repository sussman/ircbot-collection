#!/usr/bin/env python
#
# IRC Bot to moderate a game of "Werewolf".
#
#    by Ben Collins-Sussman <sussman@red-bean.com>
#       http://www.red-bean.com/sussman
#
# Werewolf is a traditional party game, sometimes known as 'Mafia',
# with dozens of variants.  This bot is following Andrew Plotkin's rules:
# http://www.eblong.com/zarf/werewolf.html
#
# Code originally based on example bot and irc-bot class from
# Joel Rosdahl <joel@rosdahl.net>, author of included python-irclib.
#


"""An IRC bot to moderate a game of "Werewolf".

This is an example bot that uses the SingleServerIRCBot class from
ircbot.py.  The bot enters a channel and listens for commands in
private messages and channel traffic.  Commands in channel messages
are given by prefixing the text by the bot name followed by a colon.

The known commands are:

    die -- Let the bot cease to exist.

    start game -- start a new werewolf game.

    end game -- quit the current werewolf game.

    stats -- print information about living/dead people.
    
"""

import sys, string, random, time
from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower

#---------------------------------------------------------------------
# General texts for narrating the game.  Change these global strings
# however you wish, without having to muck with the core logic!


# Printed when a game first starts:

new_game_texts = \
["This is a game of paranoia and psychological intrigue.",

 "Everyone in this group appears to be a common villager, but three of\
 you are 'special'.  Two people are actually evil werewolves, seeking\
 to kill everyone while concealing their identity.",
 
 "And one of you is also a 'seer'; you have the ability to learn\
 whether a specific person is or is not a werewolf.",
 
 "As a community, your group objective is to weed out the werewolves\
 and lynch them both, before you're all killed in your sleep."]

# Printed when informing players of their initial roles:

wolf_intro_text = \
"You are a WEREWOLF.  You want to kill everyone while they sleep. \
Whatever happens, keep your identity secret.  Act natural!"

seer_intro_text = \
"You're a villager, but also a SEER.  Later on, you'll get chances to \
learn whether someone is or isn't a werewolf.  Keep your identity \
secret, or the werewolves may kill you!"

villager_intro_text = \
"You're an ordinary villager."


# Printed when night begins:

night_game_texts = \
["Darkness falls:  it is NIGHT.",
 "The whole village sleeps peacefully...",
 "Everyone relax and wait for morning... I'll tell you when night is over."]

# Printed when wolves and villager get nighttime instructions:

night_seer_texts = \
["In your dreams, you have the ability to see whether a certain person\
  is or is not a werewolf.",

 "You must use this power now: please type 'see <nickname>' (as a\
 private message to me) to learn about one living player's true\
 identity."]

night_werewolf_texts = \
["As the villagers sleep, you must now decide who you want to kill.",
 "Please type 'kill <nickname>' (as a private message to me)."]


# Printed when day begins.

# Printed when the wolves kill somebody (night ends).

# Printed when a lynching happens.

# Printed when the wolves win.

# Printed when the villagers win.


#---------------------------------------------------------------------
# Actual code.
#
# WolfBot subclasses a basic 'bot' class, which subclasses a basic
# IRC-client class, which uses the python-irc library.  Thanks to Joel
# Rosdahl for the great framework!


class WolfBot(SingleServerIRCBot):
  def __init__(self, channel, nickname, server, port=6667):
    SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
    self.channel = channel
    self.game_in_progress = 0
    self._reset_gamedata()
    self.start()

    
  def on_nicknameinuse(self, c, e):
    c.nick(c.get_nickname() + "_")

      
  def on_welcome(self, c, e):
    c.join(self.channel)


  def on_privmsg(self, c, e):
    from_nick = nm_to_n(e.source())
    self.do_command(e, e.arguments()[0], from_nick)


  def on_pubmsg(self, c, e):
    a = string.split(e.arguments()[0], ":", 1)
    if len(a) > 1 \
           and irc_lower(a[0]) == irc_lower(self.connection.get_nickname()):
      self.do_command(e, string.strip(a[1]))
    return


  def _reset_gamedata(self):
    self.time = None
    self.round = 1
    self.live_players = []
    self.dead_players = []
    self.wolves = []
    self.villagers = []
    self.seer = None
    self.seer_target = None
    self.wolf_target = None
    self.villager_votes = {}


  def say_public(self, text):
    "Print TEXT into public channel, for all to see."

    self.connection.privmsg(self.channel, text)


  def say_private(self, nick, text):
    "Send private message of TEXT to NICK."

    self.connection.privmsg(nick, text)


  def reply(self, text, to_private=None):
    "Send TEXT to either public channel or TO_PRIVATE nick (if defined)."

    if to_private is not None:
      self.say_private(to_private, text)
    else:
      self.say_public(text)
    

  def start_game(self):
    "Initialize a werewolf game -- assign roles and notify all players."

    if self.game_in_progress:
      self.say_public(\
        "A game is already in progress.  Use 'end game' to end it.")

    else:
      chname, chobj = self.channels.items()[0]
      users = chobj.users()
      users.remove(self._nickname)

      if len(users) < 5:
        self.say_public("Sorry, you need at least 5 players in the channel.")

      else:

        self._reset_gamedata()
        
        # Everyone starts out alive.
        self.live_players = users[:]
        
        # Randomly select two wolves and a seer.  Everyone else is a villager.
        self.say_public("Please wait, assigning roles...")
        self.wolves.append(users.pop(random.randrange(len(users))))
        self.wolves.append(users.pop(random.randrange(len(users))))
        self.seer = users.pop(random.randrange(len(users)))
        for user in users:
          self.villagers.append(user)

        # Private message each user, tell them their role.
        self.say_private(self.seer, seer_intro_text)
        for wolf in self.wolves:
          self.say_private(wolf, wolf_intro_text)
        for villager in self.villagers:
          self.say_private(villager, villager_intro_text)
        
        self.say_public("A new game has begun!")
        for text in new_game_texts:
          self.say_public(text)
        self.game_in_progress = 1

        # Start game with a night cycle.
        time.sleep(10)
        self.night()



  def end_game(self):
    "Quit a game in progress."

    if not self.game_in_progress:
      self.say_public(\
               "No game is in progress.  Use 'start game' to begin a game.")
    else:
      self.say_public("The game has ended.")
      self.game_in_progress = 0



  def check_game_over(self):
    "End the game if either villagers or werewolves have won."

    # TODO:  if both wolves are dead,
    #        or if len(self.wolves) == len(self.villagers)
    self.end_game()



  def check_night_done(self):
    "Check if nighttime is over.  Return 1 if night is done, 0 otherwise."

    # Is the seer done seeing?
    if self.seer not in self.live_players:
      seer_done = 1
    else:
      if self.seer_target is None:
        seer_done = 0
      else:
        seer_done = 1

    # Are the wolves done killing?  The target is only set when
    # both wolves agree on somebody.
    if self.wolf_target is None:
      wolves_done = 0
    else:
      wolves_done = 1

    if wolves_done and seer_done:
      return 1
    else:
      return 0
        
        

  def night(self):
    "Execute a NIGHT episode of gameplay."

    self.time = "night"

    # Give instructions to all the different players.
    for text in night_game_texts:
      self.say_public(text)
    for text in night_seer_texts:
      self.say_private(self.seer, text)
    for text in night_werewolf_texts:
      for wolf in self.wolves:
        self.say_private(wolf, text)

    # Now wait for our command-parser to receive private commands
    # from the wolves and seer.
    

  def day(self):
    "Execute a DAY episode of gameplay."

    self.time = "day"

    ### TODO:  write this.
    print "It's now daytime."
    ### describe who's dead.  kill someone.
    self.seer_target = None
    serf.wolf_target = None
    


  def see(self, from_private, who):
    "Allow a seer to 'see' somebody."

    if self.time != "night":
      self.reply("Are you a seer?  In any case, it's not nighttime.",\
                 from_private)
    else:
      if from_private != self.seer:
        self.reply("Huh?", from_private)
      else:
        if who not in self.live_players:          
          self.reply("That player either doesn't exist, or is dead.",\
                     from_private)
        else:
          if self.seer_target is not None:
            self.reply("You've already had your vision for tonight.",\
                       from_private)
          else:
            self.seer_target = who
            if who in self.wolves:
              self.reply("You're sure that player is a werewolf!",\
                         from_private)
            else:
              self.reply("You're sure that player is a normal villager.",\
                         from_private)
              if self.check_night_done():
                self.day()



  def do_command(self, e, cmd, from_private=None):
    "Parse CMD, execute it, replying either publically or privately."

    cmds = cmd.split(" ")
    numcmds = len(cmds)

    # This is our main parser of incoming commands.
    if cmd == "die":
      self.say_public("Ciao!")
      self.die()

    elif cmd == "start game":
      self.start_game()
          
    elif cmd == "end game":
      self.end_game()
                
    elif cmd == "stats":
      # reply either to public channel, or to person who /msg'd
      chname, chobj = self.channels.items()[0]
      self.reply("There are " + `len(chobj.users())` + \
                 " players in this channel.", from_private)
      self.reply("Game currently in round " + `self.round` + ".", from_private)

    elif cmds[0] == "see":
      if numcmds == 2:
        self.see(from_private, cmds[1])
      else:
        self.reply("See who?", from_private)

    else:
      # unknown command:  respond appropriately.
      
      # reply either to public channel, or to person who /msg'd
      if self.time is None:
        self.reply("I don't understand.", from_private)
      elif self.time == "night":
        self.reply("SSSHH!  It's night, everyone's asleep!", from_private)
      elif self.time == "day":
        self.reply("Hm?  Get back to lynching.", from_private)


def main():
  
  if len(sys.argv) != 4:
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
