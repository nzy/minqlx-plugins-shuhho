import minqlx
import threading

TEAM_SPECTATOR = "spectator"
BOT_PREFIX = "900"


class add_bot(minqlx.Plugin):
    def __init__(self):
        super().__init__()
        self.add_hook("player_loaded", self.handle_player_loaded)
        self.add_hook("player_disconnect", self.handle_player_disconnect)
        self.add_command("addbot", self.cmd_addbot)
        self.add_command("kickbot", self.cmd_kickbot)

        self.bot_lock = threading.RLock()

        self.bot_active = False
        self.bot_name = "Xaero"
        self.bot_level = 1
        self.bot_thinktime = 200

    def handle_player_loaded(self, player):
        self.show_bot_status(player)

    def handle_player_disconnect(self, player, reason):
        with self.bot_lock:
            if self.bot_active and str(player.steam_id).startswith(BOT_PREFIX):
                self.bot_active = False

    def cmd_addbot(self, player, msg, channel):
        if player.team == TEAM_SPECTATOR:
            player.tell("Cannot be added in spectator mode.")
            return

        with self.bot_lock:
            if self.bot_active:
                player.tell("Bot already added.")
                return

            if len(msg) < 3:
                self.show_bot_status(player)
                return

            bot_level = int(msg[1])
            if not (1 <= bot_level <= 5):
                player.tell("Bot level must be between 1 and 5")
                return

            bot_thinktime = int(msg[2])
            if not (0 <= bot_thinktime <= 200):
                player.tell("Bot thinktime must be between 0 and 200")
                return

            self.bot_level = bot_level
            self.bot_thinktime = bot_thinktime

            self.set_cvar("bot_thinktime", self.bot_thinktime)
            minqlx.console_command("addbot {} {}".format(self.bot_name, self.bot_level))
            self.bot_active = True

    def cmd_kickbot(self, player, msg, channel):
        if player.team == TEAM_SPECTATOR:
            player.tell("Cannot be kicked in spectator mode.")
            return

        with self.bot_lock:
            if not self.bot_active:
                player.tell("Bot not found.")
                return

            minqlx.console_command("kick {}".format(self.bot_name))
            self.bot_active = False

    def show_bot_status(self, player):
        player.tell("^3Use !addbot <level [1 - 5]> <thinktime [0 - 200]> and !kickbot")
        if self.bot_active:
            player.tell("^3Current bot: level = {}, thinktime = {}".format(self.bot_level, self.bot_thinktime))
