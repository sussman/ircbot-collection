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

The main commands are:

    start game -- start a new werewolf game.

    end game -- quit the current werewolf game (you must have started it)

    stats -- print information about state of game-in-progress.
    
"""

import sys, string, random, time
from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower

#---------------------------------------------------------------------
# General texts for narrating the game.  Change these global strings
# however you wish, without having to muck with the core logic!

minUsers=7
defaultPort=6667

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
 "You and the other werewolf should discuss (privately) and choose a victim.",
 "Please type 'kill <nickname>' (as a private message to me)."]


# Printed when day begins.

day_game_texts = \
["Paranoia runs through the village!  Who is a werewolf in disguise?",
 "The villagers *must* decide to lynch one player.",
 "When each player is ready, send me the command:  'lynch <nickname>',",
 "and I will keep track of votes, until the majority agrees."]




#---------------------------------------------------------------------
# Actual code.
#
# WolfBot subclasses a basic 'bot' class, which subclasses a basic
# IRC-client class, which uses the python-irc library.  Thanks to Joel
# Rosdahl for the great framework!


class WolfBot(SingleServerIRCBot):
  def __init__(self, channel, nickname, server, port=defaultPort):
    SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
    self.channel = channel
    self.nickname = nickname
    self.game_in_progress = 0
    self._reset_gamedata()
    self.start()

    
  def on_nicknameinuse(self, c, e):
    c.nick(c.get_nickname() + "_")

  def _renameUser(self, old, new):
    for list in (self.live_players, self.wolves, self.villagers):
      if(old in list):
        list.append(new)
        list.remove(old)
    for map in (self.wolf_votes, self.villager_votes, self.tally):
      map[new]=map[old]
      del map[old]
    if new == self.seer:
      self.seer=new


  def _removeUser(self, nick):
    if(self.live_players): 
      if nick in self.live_players:
        self.say_public("%s left while nobody was looking! I've removed this person from the game.."
          %(nick))
        if(nick in self.live_players):
            self.live_players.remove(nick)
        if(nick in self.wolves):
            self.wolves.remove(nick)
            self.say_public("%s leaves a trail of wiry hairs in his wake..."%(nick))
        if(nick in self.villagers):
            self.villagers.remove(nick)
            self.say_public("%s was a quiet, normal sort of feller. Kept to himself...."%(nick))
        if(nick == self.seer):
            self.say_public("%s was blessed with unusual insight into lycanthropism."%(nick))

        self.check_game_over()


  def on_quit(self, c, e):
    self._removeUser(nm_to_n(e.source()))

  def on_nick(self, c, e):
    self._renameUser(nm_to_n(e.source()), e.target())

      
  def on_welcome(self, c, e):
    c.join(self.channel)


  def on_privmsg(self, c, e):
    from_nick = nm_to_n(e.source())
    self.do_command(e, e.arguments()[0], from_nick)

  
  def on_part(self, c, e):
    self._removeUser(nm_to_n(e.source()))


  def on_pubmsg(self, c, e):
    from_nick = nm_to_n(e.source())
    a = string.split(e.arguments()[0], ":", 1)
    if len(a) > 1 \
           and irc_lower(a[0]) == irc_lower(self.connection.get_nickname()):
      self.do_command(e, string.strip(a[1]), from_nick)
    return


  def _reset_gamedata(self):
    self.time = None
    self.game_starter = None
    self.live_players = []
    self.dead_players = []
    self.wolves = []
    self.villagers = []
    self.seer = None
    self.originalwolf1 = None
    self.originalwolf2 = None
    self.seer_target = None
    self.wolf_target = None
    self.wolf_votes = {}
    self.villager_votes = {}
    self.tally = {}


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
    

  def start_game(self, game_starter):
    "Initialize a werewolf game -- assign roles and notify all players."
    chname, chobj = self.channels.items()[0]

    if self.game_in_progress:
      self.say_public(\
        ("A game has already been started by %s;  that person must end it." %\
         self.game_starter))
    else: 
      users = chobj.users()
      users.remove(self._nickname)

      if len(users) < minUsers:
        self.say_public("Sorry, to start a game, there must be " + \
                        "at least %d players in the channel (excluding me)."%(minUsers))
        self.say_public(("I count only %d players right now." % len(users)))

      else:

        self._reset_gamedata()

        # Remember who started the game.
        self.game_starter = game_starter
        
        # Everyone starts out alive.
        self.live_players = users[:]
        
        # Randomly select two wolves and a seer.  Everyone else is a villager.
        self.say_public("Please wait, assigning roles...")
        self.wolves.append(users.pop(random.randrange(len(users))))
        self.wolves.append(users.pop(random.randrange(len(users))))
        self.originalwolf1 = self.wolves[0]
        self.originalwolf2 = self.wolves[1]
        self.seer = users.pop(random.randrange(len(users)))
        for user in users:
          self.villagers.append(user)

        # Private message each user, tell them their role.
        self.say_private(self.seer, seer_intro_text)
        time.sleep(3)
        for wolf in self.wolves:
          time.sleep(2)
          self.say_private(wolf, wolf_intro_text)
        for villager in self.villagers:
          time.sleep(3)
          self.say_private(villager, villager_intro_text)
        
        self.say_public("A new game has begun!")
        for text in new_game_texts:
          self.say_public(text)
        self.game_in_progress = 1

        time.sleep(10)
        # Start game by putting bot into "night" mode.
        self.night()
        

  def end_game(self, game_ender):
    "Quit a game in progress."

    if not self.game_in_progress:
      self.say_public(\
               "No game is in progress.  Use 'start game' to begin a game.")
    elif game_ender != self.game_starter:
      self.say_public(\
        ("Sorry, only the starter of the game (%s) may end it." %\
         self.game_starter))
    else:
      self.say_public("The game has ended.")
      self.reveal_all_identities()
      self._reset_gamedata()
      self.game_in_progress = 0


  def reveal_all_identities(self):
    "Print everyone's identities."

    self.say_public(("*** The two wolves were %s and %s." % \
                     (self.originalwolf1, self.originalwolf2)))
    self.say_public(("*** The seer was %s." % self.seer))
    self.say_public("*** Everyone else was a normal villager.")


  def check_game_over(self):
    """End the game if either villagers or werewolves have won.
    Return 1 if game is over, 0 otherwise."""

    # If all wolves are dead, the villagers win.
    if len(self.wolves) == 0:
      self.say_public("The wolves are dead!  The VILLAGERS have WON.")
      self.end_game(self.game_starter)
      return 1

    # If the number of non-wolves is the same as the number of wolves,
    # then the wolves win.
    if (len(self.live_players) - len(self.wolves)) == len(self.wolves):
      self.say_public(\
        "There are now an equal number of villagers and werewolves.")
      msg = "The werewolves have no need to hide anymore; "
      msg = msg + "They attack the remaining villagers. "
      msg = msg + "The WEREWOLVES have WON."
      self.say_public(msg)    
      self.end_game(self.game_starter)
      return 1

    return 0


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

    if (self.wolf_target is not None) and seer_done:
      return 1
    else:
      return 0

  def on_mode(self, c, e):
    nick = nm_to_n(e.source())
    chan = e.target()
    try:
      mode = e.arguments()[0];
      who = e.arguments()[1]
    except IndexError:
      return

        
        
  def night(self):
    "Declare a NIGHT episode of gameplay."

    chname, chobj = self.channels.items()[0]
#    self.connection.mode(chname, '+m')

    self.time = "night"

    # Clear any daytime variables
    self.villager_votes = {}
    self.tally = {}

    # Declare nighttime.
    self.print_alive()
    for text in night_game_texts:
      self.say_public(text)

    # Give private instructions to wolves and seer.
    if self.seer in self.live_players:
      for text in night_seer_texts:
        self.say_private(self.seer, text)
    for text in night_werewolf_texts:
      for wolf in self.wolves:
        self.say_private(wolf, text)
    if len(self.wolves) >= 2:
      self.say_private(self.wolves[0],\
                       ("The other werewolf is %s.  Confer privately."\
                        % self.wolves[1]))
      self.say_private(self.wolves[1],\
                       ("The other werewolf is %s.  Confer privately."\
                        % self.wolves[0]))

    # ... bot is now in 'night' mode;  goes back to doing nothing but
    # waiting for commands.


  def day(self):
    "Declare a DAY episode of gameplay."

    self.time = "day"

    # Discover the dead wolf victim.
    self.say_public("DAY Breaks!  Sunlight pierces the sky.")
    self.say_public(("The village awakes in horror..." + \
                     "to find the mutilated body of %s!!"\
                     % self.wolf_target.upper()))

    if not self.kill_player(self.wolf_target):
      # Clear all the nighttime voting variables:
      self.seer_target = None
      self.wolf_target = None
      self.wolf_votes = {}
      
      # Give daytime instructions.
      self.print_alive()
      for text in day_game_texts:
        self.say_public(text)
      self.say_public("Remember:  votes can be changed at any time.")

      # ... bot is now in 'day' mode;  goes back to doing nothing but
      # waiting for commands.



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


  def kill(self, from_private, who):
    "Allow a werewolf to express intent to 'kill' somebody."

    if self.time != "night":
      self.reply("Are you a werewolf?  In any case, it's not nighttime.",\
                 from_private)
    else:
      if from_private not in self.wolves:
        self.reply("Huh?", from_private)
      else:
        if who not in self.live_players:          
          self.reply("That player either doesn't exist, or is dead.",\
                     from_private)
        else:
          if len(self.wolves) == 2:
            # two wolves are alive:
            self.wolf_votes[from_private] = who
            self.reply("Your vote is acknowledged.", from_private)

            # if both wolves have voted, look for agreement:
            voters = self.wolf_votes.keys()
            if len(voters) == 2:
              if self.wolf_votes[voters[0]] == self.wolf_votes[voters[1]]:
                self.wolf_target = self.wolf_votes[voters[0]]
                self.reply("It is done.  You and the other werewolf agree.",\
                           from_private)
                if self.check_night_done():
                  self.day()
              else:
                self.reply("Hm, I sense disagreement or ambivalence.",\
                           from_private)
                self.reply("You two wolves should decide on one target.",\
                           from_private)            
          else:
            # only one wolf alive, no need to agree with anyone.
            self.wolf_target = who
            self.reply("Your decision is acknowledged.", from_private)
            if self.check_night_done():
              self.day()


  def kill_player(self, player):
    "Make a player dead.  Return 1 if game is over, 0 otherwise."

    self.live_players.remove(player)
    self.dead_players.append(player)

    if player in self.wolves:
      id = "a WEREWOLF!"
      self.wolves.remove(player)
    elif player == self.seer:
      id = "the SEER!"
    else:
      id = "a normal villager."

    self.say_public(\
        ("*** Examining the body, you notice that this player was %s" % id))
    if self.check_game_over():
      return 1
    else:
      self.say_public(("(%s is now dead, and should stay quiet.)") % player)
      self.say_private(player, "You are now DEAD.  You may observe the game,")
      self.say_private(player, "but please stay quiet until the game is over.")
      return 0


  def tally_votes(self):
    "Count votes in villager_votes{}, store results in tally{}."

    self.tally = {}
    for key in self.villager_votes.keys():
      lynchee = self.villager_votes[key]
      if self.tally.has_key(lynchee):
        self.tally[lynchee] = self.tally[lynchee] + 1
      else:
        self.tally[lynchee] = 1


  def check_for_majority(self):
    """If there is a majority of lynch-votes for one player, return
    that player's name.  Else return None."""

    majority_needed = (len(self.live_players)/2) + 1 
    for lynchee in self.tally.keys():
      if self.tally[lynchee] >= majority_needed:
        return lynchee
    else:
      return None
  
  
  def print_tally(self):
    "Publically display the vote tally."

    majority_needed = (len(self.live_players)/2) + 1 
    msg = ("%d votes needed for a majority.  Current vote tally: " \
           % majority_needed)
    for lynchee in self.tally.keys():
      if self.tally[lynchee] > 1:
        msg = msg + ("(%s : %d votes) " % (lynchee, self.tally[lynchee]))
      else:
        msg = msg + ("(%s : 1 vote) " % lynchee)
    self.say_public(msg)

      
  def print_alive(self):
    "Declare who's still alive."
    
    msg = "The following players are still alive: "
    msg = msg + `self.live_players`
    self.say_public(msg)


  def match_name(self, nick):
    """Match NICK to a username in users(), insensitively.  Return
    matching nick, or None if no match."""

    chname, chobj = self.channels.items()[0]
    users = chobj.users()
    users.remove(self._nickname)

    for user in users:
      if user.upper() == nick.upper():
        return user
    return None



  def lynch_vote(self, lyncher, lynchee):
    "Register a vote from LYNCHER to lynch LYNCHEE."

    # sanity checks
    if self.time != "day":
      self.reply("Sorry, lynching only happens during the day.")
    elif lyncher not in self.live_players:
      self.reply("Um, only living players can vote to lynch someone.")
    elif lynchee not in self.live_players:
      self.reply("Um, only living players can be lynched.")
    elif lynchee == lyncher:
      self.reply("Um, you can't lynch yourself.")

    else:
      self.villager_votes[lyncher] = lynchee
      self.say_public(("%s has voted to lynch %s!" % (lyncher, lynchee)))
      self.tally_votes()
      victim = self.check_for_majority()
      if victim is None:
        self.print_tally()
      else:
        self.say_public(("The majority has voted to lynch %s!! Mob violence ensues.  This player is now DEAD." % victim))
        if not self.kill_player(victim):
          # Day is done;  flip bot back into night-mode.
          time.sleep(5)
          self.night()


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
      target = from_private
    
    cmds = cmd.split(" ")
    numcmds = len(cmds)

    # Dead players should not speak.
    if from_private in self.dead_players:
      if (cmd != "stats") and (cmd != "status") and (cmd != "help"):
        self.reply("Please -- dead players should keep quiet.", target)
        return 0

    if cmd == "help":
        self.reply(\
        "Valid commands: 'help', 'stats', 'start game', 'end game', 'renick'", target)

    elif cmd == "stats" or cmd == "status":
      if self.game_in_progress:
        self.print_alive()
        if self.time == "day":
          self.tally_votes()
          self.print_tally()
      else:
        self.reply("No game is in progress.", target)
    elif cmd == "start game":      
      self.start_game(nm_to_n(e.source()))

    elif cmd == "end game":
      self.end_game(nm_to_n(e.source()))
    elif len(cmds)==2 and cmds[0] == "renick":
      self.connection.nick(cmds[1])
    elif cmds[0] == "see":
      if numcmds == 2:
        viewee = self.match_name(cmds[1])
        if viewee is not None:        
          self.see(target, viewee)
        else:
          self.reply("See who?", target)
      else:
        self.reply("See who?", target)

    elif cmds[0] == "kill":
      if numcmds == 2:
        killee = self.match_name(cmds[1])
        if killee is not None:
          self.kill(target, killee)
        else:
          self.reply("Kill who?", target)
      else:
        self.reply("Kill who?", target)

    elif cmds[0] == "lynch":
      if numcmds == 2:
        lynchee = self.match_name(cmds[1])
        if lynchee is not None:
          self.lynch_vote(nm_to_n(e.source()), lynchee)
        else:
          self.reply("Lynch who?", target)
      else:
        self.reply("Lynch who?", target)


    else:
      # unknown command:  respond appropriately.
      
      # reply either to public channel, or to person who /msg'd
      if self.time is None:
        self.reply("I don't understand '%s'."%(cmd), target)
      elif self.time == "night":
        self.reply("SSSHH!  It's night, everyone's asleep!", target)
      elif self.time == "day":
        self.reply("Hm?  Get back to lynching.", target)


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
    port = defaultPort
  channel = sys.argv[2]
  nickname = sys.argv[3]

  bot = WolfBot(channel, nickname, server, port)
  bot.start()

if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print "Shutting down."

