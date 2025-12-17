import minqlx
import threading
import time

DUEL_TYPE = "duel"
TIMELIMIT_FRAGS_DELTA_SEC = 30
COMMAND_FORFEIT = "forfeit"
DUEL_SIZE = 2
TEAM_FREE = "free"
LC_TIMELIMIT_OFFSET = 100
DELAY_MATCH_START_SEC = 1
SEC_IN_MIN = 60
WIN_TYPE_TIED = 0
WIN_TYPE_DEFENDED = 1
WIN_TYPE_OUTPLAYED = 2


# Golden Frag based on the Diabotical
class golden_frag(minqlx.Plugin):
    def __init__(self):
        super().__init__()
        self.add_hook("game_start", self.handle_game_start)
        self.add_hook("game_end", self.handle_game_end)
        self.add_hook("frame", self.handle_frame)
        self.add_hook("player_loaded", self.handle_player_loaded)
        self.add_hook("death", self.handle_death, priority=minqlx.PRI_HIGH)
        self.add_hook("player_disconnect", self.handle_player_disconnect, priority=minqlx.PRI_HIGH)
        self.add_hook("team_switch_attempt", self.handle_team_switch_attempt, priority=minqlx.PRI_HIGH)
        self.add_hook("client_command", self.handle_client_command, priority=minqlx.PRI_HIGH)
        self.add_command("gf", self.cmd_gf)
        self.add_command("gftl", self.cmd_gftl)

        self.player_data_lock = threading.RLock()

        self.golden_frag_active = False
        self.original_timelimit = None
        self.end_time = 0
        self.end_time_saved = 0
        self.game_started = False
        self.golden_frag_time_active = False
        self.lead_id = None
        self.underdog_id = None
        self.winner_id = None
        self.loser_id = None
        self.win_type = WIN_TYPE_TIED
        self.player_names = {}
        self.player_kills = {}
        self.save_timelimit = self.get_cvar("timelimit")

    @minqlx.delay(DELAY_MATCH_START_SEC)
    def handle_game_start(self, data):
        if not self.golden_frag_active or self.game.type_short != DUEL_TYPE:
            return

        with self.player_data_lock:
            for player in self.players():
                if player.team == TEAM_FREE:
                    self.player_kills[player.steam_id] = 0
                    self.player_names[player.steam_id] = player.name

            player_count = len(self.player_kills)
            if player_count != DUEL_SIZE:
                self.logger.warning("Incorrect player count: {}".format(player_count))
                return

            start_time = time.time() - DELAY_MATCH_START_SEC
            original_timelimit = self.get_cvar("timelimit")
            timelimit_sec = int(original_timelimit) * SEC_IN_MIN

            self.set_timelimit(LC_TIMELIMIT_OFFSET + int(original_timelimit))
            self.original_timelimit = original_timelimit
            self.end_time = start_time + timelimit_sec
            self.end_time_saved = self.end_time

            self.game_started = True

    def handle_team_switch_attempt(self, player, old_team, new_team):
        self.check_golden_frag_completion_by_other_reasons(player)

    def handle_client_command(self, player, cmd):
        if cmd.lower() == COMMAND_FORFEIT:
            self.check_golden_frag_completion_by_other_reasons(player)

    def handle_player_disconnect(self, player, reason):
        self.check_golden_frag_completion_by_other_reasons(player)

    def handle_game_end(self, data):
        if self.winner_id is not None:
            msg = None
            if self.win_type == WIN_TYPE_TIED:
                msg = "{} ^3won!".format(self.player_names[self.winner_id])
            elif self.win_type == WIN_TYPE_DEFENDED:
                msg = "{} ^3defended his victory!".format(self.player_names[self.winner_id])
            elif self.win_type == WIN_TYPE_OUTPLAYED:
                msg = "{} ^3outplayed {}!".format(self.player_names[self.winner_id],
                                                  self.player_names[self.loser_id])
            if msg is not None:
                self.msg(msg)
        self.reset()

    def handle_frame(self):
        if not self.game_started or self.golden_frag_time_active:
            return
        if time.time() > self.end_time:
            self.golden_frag_activation()

    def check_golden_frag_completion_by_other_reasons(self, player):
        with self.player_data_lock:
            if not self.golden_frag_time_active:
                return

            lead_id = next((k for k in self.player_kills if k != player.steam_id), None)
            underdog_id = player.steam_id
            if self.lead_id is None:
                self.end_game(lead_id, underdog_id, WIN_TYPE_TIED)
            elif self.lead_id == lead_id:
                self.end_game(lead_id, underdog_id, WIN_TYPE_DEFENDED)
            else:
                self.end_game(lead_id, underdog_id, WIN_TYPE_OUTPLAYED)

    def check_golden_frag_completion_by_frags(self, steam_id, delta):
        if not self.golden_frag_time_active:
            return

        lead_id, lead_kills, underdog_id, underdog_kills = self.get_lead_and_underdog_kills_info()
        if self.lead_id is None and lead_id is not None:
            self.end_game(lead_id, underdog_id, WIN_TYPE_TIED)
        elif self.lead_id is not None:
            if ((lead_id == self.lead_id and steam_id == self.lead_id and delta > 0)
                    or (steam_id == self.underdog_id and delta < 0)):
                self.end_game(lead_id, underdog_id, WIN_TYPE_DEFENDED)
            elif lead_id is not None and lead_id == self.underdog_id:
                self.end_game(lead_id, underdog_id, WIN_TYPE_OUTPLAYED)

    def get_lead_and_underdog_kills_info(self):
        kills_values = list(self.player_kills.values())
        lead_kills = max(kills_values)
        underdog_kills = min(kills_values)
        if lead_kills == underdog_kills:
            return None, None, None, None

        lead_id = next(k for k, v in self.player_kills.items() if v == lead_kills)
        underdog_id = next(k for k, v in self.player_kills.items() if v == underdog_kills)
        return lead_id, lead_kills, underdog_id, underdog_kills

    def golden_frag_activation(self):
        with self.player_data_lock:
            lead_id, lead_kills, underdog_id, underdog_kills = self.get_lead_and_underdog_kills_info()
            self.lead_id = lead_id
            self.underdog_id = underdog_id
            if lead_id is None:
                msg = "^3GOLDEN FRAG! Scores are tied!"
            else:
                msg = "^3GOLDEN FRAG! Outplay {}^3!".format(self.player_names[self.lead_id])
            self.golden_frag_time_active = True
            self.msg(msg)
            self.center_print(msg)
            self.play_sound("sound/golden_frag/golden_frag.ogg")

    def handle_player_loaded(self, player):
        player.tell("^3Plugin https://github.com/shuhho/minqlx-plugins")
        self.show_golden_frag_status(player)

    def handle_death(self, victim, killer, data):
        if not self.game_started:
            return

        with self.player_data_lock:
            if killer and killer != victim:
                self.player_kills[killer.steam_id] = self.player_kills.get(killer.steam_id) + 1
                self.check_golden_frag_completion_by_frags(killer.steam_id, 1)
            else:
                self.player_kills[victim.steam_id] = self.player_kills.get(victim.steam_id) - 1
                self.check_golden_frag_completion_by_frags(victim.steam_id, -1)

            self.change_timelimit()

    def change_timelimit(self):
        if self.golden_frag_time_active:
            return
        kills_values = list(self.player_kills.values())
        lead_kills = max(kills_values)
        underdog_kills = min(kills_values)
        delta = (lead_kills - underdog_kills)
        self.end_time = self.end_time_saved - delta * TIMELIMIT_FRAGS_DELTA_SEC
        original_timelimit = int(self.original_timelimit)
        if delta % 2 == 0:
            timer = "{}:00".format(original_timelimit - int(delta / 2))
        else:
            timer = "{}:30".format(original_timelimit - int((delta - 1) / 2) - 1)
        msg = "^3New timelimit: {}".format(timer)
        self.msg(msg)

    def cmd_gf(self, player, msg, channel):
        if len(msg) < 2:
            self.show_golden_frag_status(player)
            return

        if self.game_started:
            self.show_golden_frag_status(player)
            self.msg("Cannot be changed, game is underway.")
            return

        if msg[1] == "1":
            self.save_timelimit = self.get_cvar("timelimit")
            self.golden_frag_active = True
            self.msg("Golden frag: On")
        elif msg[1] == "0":
            self.set_timelimit(self.save_timelimit)
            self.golden_frag_active = False
            self.msg("Golden frag: Off")
        else:
            self.msg("Invalid value. Use 0 (Off) or 1 (On).")

    def end_game(self, winner_id, loser_id, win_type):
        self.golden_frag_time_active = False
        self.game_started = False
        self.win_type = win_type
        self.winner_id = winner_id
        self.loser_id = loser_id
        self.set_timelimit(-1)

    def reset(self):
        self.set_timelimit(self.save_timelimit)
        self.original_timelimit = None
        self.end_time = 0
        self.end_time_saved = 0
        self.game_started = False
        self.golden_frag_time_active = False
        self.lead_id = None
        self.underdog_id = None
        self.winner_id = None
        self.loser_id = None
        self.win_type = WIN_TYPE_TIED

        with self.player_data_lock:
            self.player_names = {}
            self.player_kills = {}

    def show_golden_frag_status(self, player):
        player.tell("Golden frag: {}. Use '!gf 0' (Off) or '!gf 1' (On).".format(
            "On" if self.golden_frag_active else "Off"))

    def set_timelimit(self, timelimit):
        self.set_cvar("timelimit", timelimit)

    def cmd_gftl(self, player, msg, channel):
        self.play_sound("sound/golden_frag/golden_frag.ogg")
