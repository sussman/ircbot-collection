#!/usr/bin/env python
#
# IRC Bot to moderate a game of "Werewolf".
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
import irclib
from irclib import nm_to_n, nm_to_h, irc_lower, parse_channel_modes
from botcommon import OutputManager

#---------------------------------------------------------------------
# General texts for narrating the game.  Change these global strings
# however you wish, without having to muck with the core logic!

minUsers=6
defaultPort=6667

svn_url = \
"$URL$"
svn_url = svn_url[svn_url.find(' ')+1:svn_url.rfind('/')+1]

# Printed when a game first starts:

new_game_texts = \
["This is a game of paranoia and psychological intrigue.  Everyone\
 in this group appears to be a common villager, but three of\
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

IRC_BOLD = "\x02"

class WolfBot(SingleServerIRCBot):
  GAMESTATE_NONE, GAMESTATE_STARTING, GAMESTATE_RUNNING  = range(3)
  def __init__(self, channel, nickname, nickpass, server, port=defaultPort,
      debug=False):
    SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
    self.channel = channel
    # self.nickname is the nickname we _want_. The nickname we actually
    # have at any particular time is c.get_nickname().
    self.nickname = nickname
    self.nickpass = nickpass
    self.debug = debug
    self.moderation = True
    self._reset_gamedata()
    self.queue = OutputManager(self.connection, .9)
    self.queue.start()
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

  def _renameUser(self, old, new):
    for list in (self.live_players, self.dead_players, self.wolves,
        self.villagers, self.originalwolves):
      if old in list:
        list.append(new)
        list.remove(old)
    for map in (self.wolf_votes, self.villager_votes, self.tally):
      if map.has_key(new):
        map[new] = map[old]
        del map[old]
    for map in (self.wolf_votes, self.villager_votes):
      for k, v in map.items():
        if v == old:
          map[k] = new
    for var in ('game_starter', 'seer', 'seer_target', 'wolf_target'):
      if getattr(self, var) == old:
        setattr(self, var, new)

  def _removeUser(self, nick):
    if nick == self.game_starter:
      self.game_starter = None
    if nick in self.live_players:
      self.say_public("%s left while nobody was looking!" % nick)
      self.live_players.remove(nick)
      if self.gamestate == self.GAMESTATE_STARTING:
        # No more to do
        return
      self.dead_players.append(nick)
      if nick in self.wolves:
        self.wolves.remove(nick)
        self.say_public("%s's apartment always smelled like wet dog!" % nick)
      if nick in self.villagers:
        self.villagers.remove(nick)
        self.say_public("%s was a quiet, normal sort of feller. "
            "Kept to himself...." % nick)
      if nick == self.seer:
        self.say_public("%s was blessed with unusual insight into "
            "lycanthropism." % nick)
      if nick == self.seer_target:
        self.say_private("Due to %s's unexpected erasure from reality, "
            "you may See once again this night." % nick, self.seer)
        self.seer_target = None
      if nick == self.wolf_target:
        for wolf in self.wolves:
          self.say_private("Due to %s's unexpected erasure from reality, "
              "you can choose someone else to kill tonight." % nick, wolf)
        self.wolf_target = None
      for map in (self.wolf_votes, self.villager_votes, self.tally):
        if map.has_key(nick):
          del map[nick]
      for map in (self.wolf_votes, self.villager_votes):
        for k, v in map.items():
          if v == nick:
            del map[k]
      self.check_game_over()


  def on_join(self, c, e):
    nick = nm_to_n(e.source())
    if nick == c.get_nickname():
      chan = e.target()
      self.connection.mode(self.channel, '')

  def on_channelmodeis(self, c, e):
    c._handle_event(
        irclib.Event("mode", e.source(), e.arguments()[0], [e.arguments()[1]]))
    self.fix_modes()

  def on_mode(self, c, e):
    if e.target() == self.channel:
      try:
        if parse_channel_modes(e.arguments()[0]) == ['+','o',c.get_nickname()]:
          self.fix_modes()
      except IndexError:
        pass


  def on_quit(self, c, e):
    source = nm_to_n(e.source())
    self._removeUser(source)
    if source == self.nickname:
      # Our desired nick just quit - take the nick back
      c.nick(self.nickname)

  def on_nick(self, c, e):
    self._renameUser(nm_to_n(e.source()), e.target())


  def on_welcome(self, c, e):
    c.join(self.channel)
    if c.get_nickname() != self.nickname:
      # Reclaim our desired nickname
      c.privmsg('nickserv', 'ghost %s %s' % (self.nickname, self.nickpass))


  def fix_modes(self):
    chobj = self.channels[self.channel]
    is_moderated = chobj.is_moderated()
    should_be_moderated = (self.gamestate == self.GAMESTATE_RUNNING
        and self.moderation)
    if is_moderated and not should_be_moderated:
      self.connection.mode(self.channel, '-m')
    elif not is_moderated and should_be_moderated:
      self.connection.mode(self.channel, '+m')

    voice = []
    devoice = []
    for user in chobj.users():
      is_live = user in self.live_players
      is_voiced = chobj.is_voiced(user)
      if is_live and not is_voiced:
        voice.append(user)
      elif not is_live and is_voiced:
        devoice.append(user)
    self.multimode('+v', voice)
    self.multimode('-v', devoice)


  def multimode(self, mode, nicks):
    max_batch = 4 # FIXME: Get this from features message
    assert len(mode) == 2
    assert mode[0] in ('-', '+')
    while nicks:
      batch_len = len(nicks)
      if batch_len > max_batch:
        batch_len = max_batch
      tokens = [mode[0] + (mode[1]*batch_len)]
      while batch_len:
        tokens.append(nicks.pop(0))
        batch_len -= 1
      self.connection.mode(self.channel, ' '.join(tokens))


  def on_privnotice(self, c, e):
    source = e.source()
    if source and irc_lower(nm_to_n(source)) == 'nickserv':
      if e.arguments()[0].find('IDENTIFY') >= 0:
        # Received request to identify
        if self.nickpass and self.nickname == c.get_nickname():
          self.queue.send('identify %s' % self.nickpass, 'nickserv')


  GAME_STARTER_TIMEOUT_MINS = 4
  def check_game_control(self, e):
    "Implement a timeout for game controller."
    if self.game_starter is None:
      return
    nick = nm_to_n(e.source())
    if self.game_starter == nick:
      self.game_starter_last_seen = time.time()
    else:
      if self.game_starter_last_seen < (
          time.time() - self.GAME_STARTER_TIMEOUT_MINS * 60):
        self.say_public("Game starter '%s' has been silent for %d minutes. "
            "Game control is now open to all." % (self.game_starter,
              self.GAME_STARTER_TIMEOUT_MINS))
        self.game_starter = None

  def on_privmsg(self, c, e):
    self.check_game_control(e)
    self.do_command(e, e.arguments()[0])


  def on_part(self, c, e):
    self._removeUser(nm_to_n(e.source()))


  def on_pubmsg(self, c, e):
    self.check_game_control(e)
    a = string.split(e.arguments()[0], ":", 1)
    if len(a) > 1 and irc_lower(a[0]) == irc_lower(c.get_nickname()):
      self.do_command(e, string.strip(a[1]))


  def _reset_gamedata(self):
    self.gamestate = self.GAMESTATE_NONE
    self.time = None
    self.game_starter = None
    self.game_starter_last_seen = 0
    self.live_players = []
    self.dead_players = []
    self.wolves = []
    self.villagers = []
    self.seer = None
    self.originalwolves = []
    # Night round variables
    self.seer_target = None
    self.wolf_target = None
    self.wolf_votes = {}
    # Day round variables
    self.villager_votes = {}
    self.tally = {}


  def say_public(self, text):
    "Print TEXT into public channel, for all to see."

    self.queue.send(IRC_BOLD+text, self.channel)


  def say_private(self, nick, text):
    "Send private message of TEXT to NICK."
    self.queue.send(IRC_BOLD+text,nick)


  def reply(self, e, text):
    "Send TEXT to public channel or as private msg, in reply to event E."
    if e.eventtype() == "pubmsg":
      self.say_public("%s: %s" % (nm_to_n(e.source()), text))
    else:
      self.say_private(nm_to_n(e.source()), text)


  def start_game(self, game_starter):
    "Initialize a werewolf game -- assign roles and notify all players."
    chname, chobj = self.channels.items()[0]

    if self.gamestate == self.GAMESTATE_RUNNING:
      self.say_public("A game started by %s is in progress; "
          "that person must end it." % self.game_starter)
      return

    if self.gamestate == self.GAMESTATE_NONE:
      self._reset_gamedata()
      self.gamestate = self.GAMESTATE_STARTING
      self.game_starter = game_starter
      self.game_starter_last_seen = time.time()
      self.live_players.append(game_starter)
      self.say_public("A new game has been started by %s; "
          "say '%s: join' to join the game."
          % (self.game_starter, self.connection.get_nickname()))
      self.say_public("%s: Say '%s: start' when everyone has joined."
          % (self.game_starter, self.connection.get_nickname()))
      self.fix_modes()
      return

    if self.gamestate == self.GAMESTATE_STARTING:
      if self.game_starter and game_starter != self.game_starter:
        self.say_public("Game startup was begun by %s; "
            "that person must finish starting it." % self.game_starter)
        return
      self.game_starter = game_starter
      self.game_starter_last_seen = time.time()

      if len(self.live_players) < minUsers:
        self.say_public("Sorry, to start a game, there must be " + \
                        "at least active %d players."%(minUsers))
        self.say_public(("I count only %d active players right now: %s."
          % (len(self.live_players), self.live_players)))

      else:
        # Randomly select two wolves and a seer.  Everyone else is a villager.
        users = self.live_players[:]
        self.say_public("A new game has begun! Please wait, assigning roles...")
        self.wolves.append(users.pop(random.randrange(len(users))))
        self.wolves.append(users.pop(random.randrange(len(users))))
        self.originalwolves = self.wolves[:]
        self.seer = users.pop(random.randrange(len(users)))
        for user in users:
          self.villagers.append(user)

        # Private message each user, tell them their role.
        self.say_private(self.seer, seer_intro_text)
        for wolf in self.wolves:
          self.say_private(wolf, wolf_intro_text)
        for villager in self.villagers:
          self.say_private(villager, villager_intro_text)

        if self.debug:
          print "SEER: %s, WOLVES: %s" % (self.seer, self.wolves)

        for text in new_game_texts:
          self.say_public(text)
        self.gamestate = self.GAMESTATE_RUNNING

        self.fix_modes()

        # Start game by putting bot into "night" mode.
        self.night()


  def end_game(self, game_ender):
    "Quit a game in progress."

    if self.gamestate == self.GAMESTATE_NONE:
      self.say_public(\
               "No game is in progress.  Use 'start' to begin a game.")
    elif self.game_starter and game_ender != self.game_starter:
      self.say_public(\
        ("Sorry, only the starter of the game (%s) may end it." %\
         self.game_starter))
    else:
      self.say_public("The game has ended.")
      if self.gamestate == self.GAMESTATE_RUNNING:
        self.reveal_all_identities()
      self._reset_gamedata()
      self.gamestate = self.GAMESTATE_NONE
      self.fix_modes()


  def reveal_all_identities(self):
    "Print everyone's identities."

    self.say_public(("*** The two wolves were %s and %s, the seer was %s. "
      "Everyone else was a normal villager"
      % (self.originalwolves[0], self.originalwolves[1], self.seer)))

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


  def night(self):
    "Declare a NIGHT episode of gameplay."

    chname, chobj = self.channels.items()[0]

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



  def see(self, e, who):
    "Allow a seer to 'see' somebody."

    if self.time != "night":
      self.reply(e, "Are you a seer?  In any case, it's not nighttime.")
    else:
      if nm_to_n(e.source()) != self.seer:
        self.reply(e, "Huh?")
      else:
        if who not in self.live_players:
          self.reply(e, "That player either doesn't exist, or is dead.")
        else:
          if self.seer_target is not None:
            self.reply(e, "You've already had your vision for tonight.")
          else:
            self.seer_target = who
            if who in self.wolves:
              self.reply(e, "You're sure that player is a werewolf!")
            else:
              self.reply(e, "You're sure that player is a normal villager.")
            if self.check_night_done():
              self.day()


  def kill(self, e, who):
    "Allow a werewolf to express intent to 'kill' somebody."
    if self.time != "night":
      self.reply(e, "Are you a werewolf?  In any case, it's not nighttime.")
      return
    if nm_to_n(e.source()) not in self.wolves:
      self.reply(e, "Huh?")
      return
    if who not in self.live_players:
      self.reply(e, "That player either doesn't exist, or is dead.")
      return
    if len(self.wolves) > 1:
      # Multiple wolves are alive:
      self.wolf_votes[nm_to_n(e.source())] = who
      self.reply(e, "Your vote is acknowledged.")

      # If all wolves have voted, look for agreement:
      if len(self.wolf_votes) == len(self.wolves):
        for killee in self.wolf_votes.values():
          if who != killee:
            break
        else:
          self.wolf_target = who
          self.reply(e, "It is done. The werewolves agree.")
          if self.check_night_done():
            self.day()
          return
        self.reply(e, "Hm, I sense disagreement or ambivalence.")
        self.reply(e, "You wolves should decide on one target.")
    else:
      # only one wolf alive, no need to agree with anyone.
      self.wolf_target = who
      self.reply(e, "Your decision is acknowledged.")
      if self.check_night_done():
        self.day()


  def kill_player(self, player):
    "Make a player dead.  Return 1 if game is over, 0 otherwise."

    self.live_players.remove(player)
    self.dead_players.append(player)
    self.fix_modes()

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
        self.tally[lynchee] += 1
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
    msg = "The following players are still alive: %s"%', '.join(self.live_players)
    self.say_public(msg)
    if self.dead_players:
      msg = "The following players are dead : %s"%', '.join(self.dead_players)
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



  def lynch_vote(self, e, lynchee):
    "Register a vote to lynch LYNCHEE."

    lyncher = nm_to_n(e.source())
    # sanity checks
    if self.time != "day":
      self.reply(e, "Sorry, lynching only happens during the day.")
    elif lyncher not in self.live_players:
      self.reply(e, "Um, only living players can vote to lynch someone.")
    elif lynchee not in self.live_players:
      self.reply(e, "Um, only living players can be lynched.")
    elif lynchee == lyncher:
      self.reply(e, "Um, you can't lynch yourself.")

    else:
      self.villager_votes[lyncher] = lynchee
      self.say_public(("%s has voted to lynch %s!" % (lyncher, lynchee)))
      self.tally_votes()
      victim = self.check_for_majority()
      if victim is None:
        self.print_tally()
      else:
        self.say_public(("The majority has voted to lynch %s!! "
          "Mob violence ensues.  This player is now DEAD." % victim))
        if not self.kill_player(victim):
          # Day is done;  flip bot back into night-mode.
          self.night()


  def cmd_help(self, args, e):
    cmds = [i[4:] for i in dir(self) if i.startswith('cmd_')]
    self.reply(e, "Valid commands: '%s'" % "', '".join(cmds))

  def cmd_stats(self, args, e):
    if self.gamestate == self.GAMESTATE_RUNNING:
      self.print_alive()
      if self.time == "day":
        self.tally_votes()
        self.print_tally()
    elif self.gamestate == self.GAMESTATE_STARTING:
      self.reply(e, "A new game is starting, current players are %s"
          % (self.live_players,))
    else:
      self.reply(e, "No game is in progress.")

  def cmd_status(self, args, e):
    self.cmd_stats(args, e)

  def cmd_start(self, args, e):
    target = nm_to_n(e.source())
    self.start_game(target)

  def cmd_end(self, args, e):
    target = nm_to_n(e.source())
    self.end_game(target)

  def cmd_votes(self, args, e):
    non_voters = []
    voters = []
    if self.villager_votes.keys():
      for n in self.live_players:
        if not self.villager_votes.has_key(n):
          non_voters.append(n)
        else:
          voters.append(n)
      if non_voters:
        self.say_public("The following have no votes registered: %s"
            % (non_voters))
      else:
        self.say_public("Everyone has voted.")
    else:
      self.say_public("Nobody has voted yet.")

  def cmd_del(self, args, e):
    for nick in args:
      if nick not in self.live_players + self.dead_players:
        self.reply(e, "There's nobody playing by the name %s" % nick)
      self._removeUser(nick)

  def cmd_renick(self, args, e):
    if len(args) != 1:
      self.reply(e, "Usage: renick <nick>")
      return
    self.connection.nick(args[0])

  def cmd_see(self, args, e):
    target = nm_to_n(e.source())
    if len(args) == 1:
      viewee = self.match_name(args[0].strip())
      if viewee is not None:
        self.see(e, viewee.strip())
        return
    self.reply(e, "See who?")

  def cmd_kill(self, args, e):
    target = nm_to_n(e.source())
    if len(args) == 1:
      killee = self.match_name(args[0].strip())
      if killee is not None:
        self.kill(e, killee)
        return
    self.reply(e, "Kill who?")

  def cmd_lynch(self, args, e):
    target = nm_to_n(e.source())
    if len(args) == 1:
      lynchee = self.match_name(args[0])
      if lynchee is not None:
        self.lynch_vote(e, lynchee.strip())
        return
    self.reply(e, "Lynch who?")

  def cmd_join(self, args, e):
    if self.gamestate == self.GAMESTATE_NONE:
      self.reply(e, 'No game is running, perhaps you would like to start one?')
      return
    if self.gamestate == self.GAMESTATE_RUNNING:
      self.reply(e, 'Game is in progress; please wait for the next game.')
      return
    player = nm_to_n(e.source())
    if player in self.live_players:
      self.reply(e, 'You were already in the game!')
    else:
      self.live_players.append(player)
      self.reply(e, 'You are now in the game.')
      self.fix_modes()

  def cmd_aboutbot(self, args, e):
    self.reply(e, "I am a bot written in Python "
        "using the python-irclib library")
    self.reply(e, "My source code is available at %s" % svn_url)

  def cmd_moderation(self, args, e):
    if self.game_starter and self.game_starter != nm_to_n(e.source()):
      self.reply(e, "%s started the game, and so has administrative control. "
          "Request denied." % self.game_starter)
      return
    if len(args) != 1:
      self.reply(e, "Usage: moderation on|off")
      return
    if args[0] == 'on':
      self.moderation = True
    elif args[0] == 'off':
      self.moderation = False
    else:
      self.reply(e, "Usage: moderation on|off")
      return
    self.say_public('Moderation turned %s by %s'
        % (args[0], nm_to_n(e.source())))
    self.fix_modes()

  def do_command(self, e, cmd):
    """This is the function called whenever someone sends a public or
    private message addressed to the bot. (e.g. "bot: blah").  Parse
    the CMD, execute it, then reply either to public channel or via
    /msg, based on how the command was received.  E is the original
    event, and FROM_PRIVATE is the nick that sent the message."""

    cmds = cmd.strip().split(" ")

    if self.debug and e.eventtype() == "pubmsg":
      if cmds[0][0] == '!':
        e._source = cmds[0][1:] + '!fakeuser@fakehost'
        cmds = cmds[1:]

    # Dead players should not speak.
    if nm_to_n(e.source()) in self.dead_players:
      if (cmd != "stats") and (cmd != "status") and (cmd != "help"):
        self.reply(e, "Please -- dead players should keep quiet.")
        return 0

    try:
      cmd_handler = getattr(self, "cmd_" + cmds[0])
    except AttributeError:
      cmd_handler = None

    if cmd_handler:
      cmd_handler(cmds[1:], e)
      return

    # unknown command:  respond appropriately.

    # reply either to public channel, or to person who /msg'd
    if self.time is None:
      self.reply(e, "I don't understand '%s'."%(cmd))
    elif self.time == "night":
      self.reply(e, "SSSHH!  It's night, everyone's asleep!")
    elif self.time == "day":
      self.reply(e, "Hm?  Get back to lynching.")


def usage(exitcode=1):
  print "Usage: wolfbot.py [-d] [<config-file>]"
  sys.exit(exitcode)


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
    configfile = 'wolfbot.conf'

  import ConfigParser
  c = ConfigParser.ConfigParser()
  c.read(configfile)
  cfgsect = 'wolfbot'
  host = c.get(cfgsect, 'host')
  channel = c.get(cfgsect, 'channel')
  nickname = c.get(cfgsect, 'nickname')
  nickpass = c.get(cfgsect, 'nickpass')

  s = string.split(host, ":", 1)
  server = s[0]
  if len(s) == 2:
    try:
      port = int(s[1])
    except ValueError:
      print "Error: Erroneous port."
      sys.exit(1)
  else:
    port = defaultPort

  bot = WolfBot(channel, nickname, nickpass, server, port, debug)


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print "Caught Ctrl-C during initialization."
