from plugin_manager import BasePlugin
from utils import Command, respond, process_args
from random import choice
from asyncio import get_event_loop
from math import ceil
from youtube_dl.utils import DownloadError


class MusicPlayer(BasePlugin):
    name = "music_player"
    default_config = {
        'music_channel': "CHANNEL ID HERE",
        'force_music_channel': False,
        'no_permission_lines': [
            "**NEGATIVE. Insufficient permissions for funky beats in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for rocking you like a hurricane in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for putting hands in the air in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for wanting to rock in channel: {}.**",
            "**NEGATIVE. Insufficient permissions for dropping the beat in channel: {}.**"
        ],
        'max_video_length': 10 * 60,
        'max_queue_length': 30,
        'default_volume': 100,
        'ytdl_options': {
            'format': 'bestaudio/best',
            'extractaudio': True,
            'audioformat': 'mp3',
            'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
            'restrictfilenames': True,
            'noplaylist': True,
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'quiet': True,
            'no_warnings': False,
            'default_search': 'auto',
            'source_address': '0.0.0.0'
        }
    }

    def activate(self):
        c = self.plugin_config
        self.vc = False
        self.player = False
        self.queue = []
        self.vote_set = set()
        # stuff from config
        self.no_perm_lines = c.no_permission_lines
        self.ytdl_options = c.ytdl_options
        self.volume = c.default_volume
        self.max_length = c.max_video_length
        self.max_queue = c.max_queue_length
        self.m_channel = c.music_channel if c.force_music_channel else False

    @Command("joinvc",
             category="voice",
             syntax="",
             doc="Joins same voice channel as user.")
    async def _joinvc(self, data):
        """
        Joins the same voice chat as the caller.
        Checks the permissions before joining - must be able to join, speak and not use ptt.
        """
        # leave if there's already a vc client in self.
        if self.vc:
            self.vc.disconnect()
        for server in self.client.servers:
            # doublecheck, just in case bot crashed earlier and discord is being weird
            if self.client.is_voice_connected(server):
                await self.client.voice_client_in(server).disconnect()
            a_voice = self.m_channel
            if not self.m_channel:
                a_voice = data.author.voice.voice_channel
            perms = server.me.permissions_in(a_voice)
            if perms.connect and perms.speak and perms.use_voice_activation:
                self.vc = await self.client.join_voice_channel(a_voice)
                await respond(self.client, data, f"**AFFIRMATIVE. Connected to: {a_voice}.**")
            else:
                await respond(self.client, data, choice(self.no_perm_lines).format(a_voice))

    @Command("playvc",
             "play",
             category="voice",
             syntax="[URL or search query]",
             doc="Plays presented youtube video or searches for one.\nNO PLAYLISTS ALLOWED.")
    async def _playvc(self, data):
        """
        Decorates the input to make sure ytdl can eat it and filters out playlists before pushing the video in the
        queue.
        """
        if not self.vc:
            await self._joinvc(data)
            #await respond(self.client, data, "**WARNING: Can not play music while not connected.**")
        args = data.content.split(' ', 1)
        if len(args) > 1:
            if not (args[1].startswith("http://") or args[1].startswith("https://")):
                args[1] = "ytsearch:" + args[1]
            if args[1].find("list=") > -1:
                raise SyntaxWarning("No playlists allowed!")
            await self.play_video(args[1], data)
        else:
            raise SyntaxError("Expected URL or search query.")

    async def play_video(self, vid, data):
        """
        Processes provided video request, either starting to play it instantly or adding it to queue.
        :param vid: URL or ytsearch: query to process or NEXT for skipping
        :param data: message data for responses
        """
        if self.player and not self.player.is_done() and vid != "NEXT":
            t_player = await self.vc.create_ytdl_player(vid, ytdl_options=self.ytdl_options,
                                                        after=lambda: t_loop.create_task(self.play_video("NEXT",
                                                                                                         data)))
            if t_player.duration > self.max_length:
                await respond(self.client, data, f"**NEGATIVE. ANALYSIS: Song over the maximum duration of "
                                                 f"{t_player.duration//60}:{t_player.duration%60}.**")
                return
            if len(self.queue)<self.max_queue:
                self.queue.append(t_player)
                await respond(self.client, data, f"**AFFIRMATIVE. ADDING \"{t_player.title}\" to queue.\n"
                                                 f"Current queue:**\n```{self.build_queue()}```")
            else:
                await respond(self.client, data, f"**NEGATIVE. ANALYSIS: Queue full. Dropping \"{t_player.title}\".\n"
                                                 f"Current queue:**\n```{self.build_queue()}```")
        else:
            self.vote_set = set()
            if vid != "NEXT":
                t_loop = get_event_loop()
                # creates a player with a callback to play next video
                self.player = await self.vc.create_ytdl_player(vid, ytdl_options=self.ytdl_options,
                                                               after=lambda: t_loop.create_task(self.play_video("NEXT",
                                                                       data)))
            elif len(self.queue) > 0:
                self.player = self.queue.pop(0)
            else:
                await respond(self.client, data, "**ANALYSIS: Queue complete.**")
            if self.player.duration <= self.max_length:
                self.player.volume = self.volume / 100
                self.player.start()
                await respond(self.client, data, f"**CURRENTLY PLAYING: \"{self.player.title}\"**")
            else:
                self.player.stop()
                await respond(self.client, data, f"**WARNING: \"{self.player.title}\" is too long, skipping.**")

    def build_queue(self):
        """
        builds a nice newline separated queue
        :return: returns queue string
        """
        t_string = ""
        for player in self.queue:
            title = player.title[0:36].ljust(39) if len(player.title) < 36 else player.title[0:36] + "..."
            mins, secs = divmod(player.duration, 60)
            t_string = f"{t_string}{title} [{mins}:{secs:02d}]\n"
        return t_string

    @Command("skipvc",
             category="voice",
             syntax="",
             doc="Skips current video.")
    async def _skipvc(self, data):
        """
        Collects votes for skipping current song or skips if you got mute_members permission
        """
        self.vote_set.add(data.author.id)
        override = data.author.permissions_in(self.vc.channel).mute_members
        votes = len(self.vote_set)
        m_votes = (len(self.vc.channel.voice_members)-1)/2
        if votes >= m_votes or override:
            if self.player:
                self.player.stop()
                await respond(self.client, data, "**AFFIRMATIVE. Skipping current song.**"
                              if not override else "**AFFIRMATIVE. Override accepted. Skipping current song.**")
        else:
            await respond(self.client, data, f"**Skip vote: ACCEPTED. {votes} out of required {ceil(m_votes)}**")


    @Command("volvc",
             category="voice",
             syntax="[volume from 0 to 200]",
             doc="Adjusts volume, from 0 to 200%.")
    async def _volvc(self, data):
        """
        Checks that the user didn't put in something stupid and adjusts volume.
        """
        args = process_args(data.content.split())
        if len(args) > 1:
            try:
                vol = int(args[1])
            except ValueError:
                raise SyntaxError("Expected integer value between 0 and 200!")
            if vol < 0:
                vol = 0
            if vol > 200:
                vol = 200
            self.volume = vol
            if self.player:
                self.player.volume = vol / 100
        else:
            await respond(self.client, data, f"**ANALYSIS: Current volume: {self.volume}/100.**")

    @Command("stopvc",
             perms={"mute_members"},
             category="voice",
             syntax="",
             doc="Stops the music. All of it.")
    async def _stopvc(self, data):
        if len(self.queue) > 0:
            self.queue = []
        if self.player:
            self.player.stop()
        await respond(self.client, data, "**AFFIRMATIVE. Ceasing the rhythmical noise.**")

    @Command("queuevc",
             category="voice",
             syntax="",
             doc="Writes out the current queue.")
    async def _queuevc(self, data):
        if len(self.queue) > 0:
            await respond(self.client, data, f"**ANALYSIS: Current queue:**\n```{self.build_queue()}```")
        else:
            await respond(self.client, data, "**ANALYSIS: queue empty.**")

    @Command("nowvc",
             category="voice",
             syntax="",
             doc="Writes out the current queue.")
    async def _nowvc(self, data):
        if self.player:
            t_string = "**CURRENTLY PLAYING:\n**```"
            t_string += "TITLE: "+self.player.title+"\n\n"
            t_string += "DESCRIPTION: "+self.player.description.replace("https://", "").replace("http://","")+"\n\n"
            t_string += "DURATION: "+str(self.player.duration//60)+":"+str(self.player.duration%60)+"```"
            await respond(self.client, data, t_string)
