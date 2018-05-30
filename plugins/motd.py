import asyncio
import datetime
import json
from random import choice
from plugin_manager import BasePlugin
from rs_errors import CommandSyntaxError, ChannelNotFoundError
from rs_utils import respond
from command_dispatcher import Command


class MOTD(BasePlugin):
    name = "motd"
    default_config = {
        "motd_file": "config/motds.json"
    }

    async def activate(self):
        self.run_timer = True
        try:
            with open(self.plugin_config.motd_file, "r", encoding="utf8") as f:
                self.motds = json.load(f)
                asyncio.ensure_future(self._run_motd())
        except FileNotFoundError:
            with open(self.plugin_config.motd_file, "w", encoding="utf8") as f:
                self.motds = {}
                f.write("{}")
        except json.decoder.JSONDecodeError:
            self.logger.exception(f"Could not decode {self.plugin_config.motd_file}! ", exc_info=True)
        self.valid_months = {
            "January", "February", "March", "April", "May", "June", "July",
            "August", "September", "October", "November", "December", "Any"
        }
        self.valid_days = {
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Any",
            "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16",
            "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30", "31"
        }

    async def deactivate(self):
        self.run_timer = False

    async def _run_motd(self):
        now = datetime.datetime.utcnow().time()
        await asyncio.sleep(60 - now.second)
        while self.run_timer:
            now = datetime.datetime.utcnow().time()
            self.logger.debug(now)
            if now.hour is 0 and now.minute is 0:
                await self._display_motd()
            await asyncio.sleep(60 - now.second)

    def _save_motds(self):
        with open(self.plugin_config.motd_file, "w", encoding="utf8") as f:
            json.dump(self.motds, f, indent=2, ensure_ascii=False)

    async def _display_motd(self):
        today = datetime.date.today()
        month = today.strftime("%B")
        day = str(today.day)
        weekday = today.strftime("%A")
        holiday_lines = self._get_holiday(month, day, weekday)
        if holiday_lines:
            for guild in self.client.guilds:
                chan = self.channel_manager.get_channel(guild, "motd")
                asyncio.ensure_future(chan.send(choice(holiday_lines)))
        else:
            lines = []
            lines += self.motds.get("Any", {}).get("Any", [])
            lines += self.motds.get("Any", {}).get(day, [])
            lines += self.motds.get("Any", {}).get(weekday, [])
            lines += self.motds.get(month, {}).get("Any", [])
            lines += self.motds.get(month, {}).get(day, [])
            lines += self.motds.get(month, {}).get(weekday, [])
            for guild in self.client.guilds:
                try:
                    chan = self.channel_manager.get_channel(guild, "motd")
                    await chan.send(choice(lines))
                except ChannelNotFoundError:
                    pass

    def _get_holiday(self, month, day, weekday):
        holidays = self.motds.get("holidays", [])
        if f"{month}/{day}" in holidays:
            return self.motds[month][day]
        elif f"{month}/{weekday}" in holidays:
            return self.motds[month][weekday]
        elif f"{month}/Any" in holidays:
            return self.motds[month]["Any"]
        elif f"Any/{day}" in holidays:
            return self.motds["Any"][day]
        elif f"Any/{weekday}" in holidays:
            return self.motds["Any"][weekday]
        else:
            return

    @Command("AddMotD",
             doc="Adds a MotD message.",
             perms={"manage_guild"},
             category="bot_management",
             syntax="(month/Any) (day/weekday/Any) (message)")
    async def _addmotd(self, msg):
        args = msg.clean_content.split(" ")[1:]
        try:
            month = args[0].capitalize()
            day = args[1].capitalize()
            newmotd = " ".join(args[2:])
        except IndexError:
            raise CommandSyntaxError
        if month not in self.valid_months or day not in self.valid_days:
            raise CommandSyntaxError("Month or day is invalid. Please use full names.")
        try:
            if month not in self.motds:
                self.motds[month] = {}
            if day not in self.motds[month]:
                self.motds[month][day] = []
            self.motds[month][day].append(newmotd)
            self._save_motds()
            await respond(msg, f"**ANALYSIS: MotD for {month} {day} added successfully.**")
        except KeyError:
            raise CommandSyntaxError("Month or day is invalid. Please use full names.")

    @Command("AddHoliday",
             doc="Adds a holiday. Holidays do not draw from the \"any-day\" MotD pools.",
             perms={"manage_guild"},
             category="bot_management",
             syntax="(month/Any) (day/weekday/Any)")
    async def _addholiday(self, msg):
        args = msg.clean_content.split()[1:]
        try:
            month = args[0].capitalize()
            day = args[1].capitalize()
        except IndexError:
            raise CommandSyntaxError
        if month not in self.valid_months or day not in self.valid_days:
            self.logger.debug(month)
            self.logger.debug(day)
            raise CommandSyntaxError("Month or day is invalid. Please use full names.")
        holidaystr = month + "/" + day
        if holidaystr not in self.motds["holidays"]:
            self.motds["holidays"].append(holidaystr)
            await respond(msg, f"**ANALYSIS: Holiday {holidaystr} added successfully.**")
        else:
            await respond(msg, f"**ANALYSIS: {holidaystr} is already a holiday.**")

    @Command("TestMotDs",
             doc="Used for testing MOTD lines.",
             perms={"manage_guild"},
             category="debug",
             syntax="(month/Any) (day/Any) (weekday/Any)")
    async def _testmotd(self, msg):
        try:
            args = msg.clean_content.split()[1:]
            month = args[0].capitalize()
            day = args[1].capitalize()
            weekday = args[2].capitalize()
            if month not in self.valid_months or day not in self.valid_days or weekday not in self.valid_days:
                raise CommandSyntaxError("One of the arguments is not valid.")
            month = "" if month == "Any" else month
            day = "" if day == "Any" else day
            weekday = "" if weekday == "Any" else weekday
        except IndexError:
            raise CommandSyntaxError("Missing arguments.")
        holiday_lines = self._get_holiday(month, day, weekday)
        if holiday_lines:
            await respond(msg, choice(holiday_lines))
        else:
            lines = []
            lines += self.motds.get("Any", {}).get("Any", [])
            lines += self.motds.get("Any", {}).get(day, [])
            lines += self.motds.get("Any", {}).get(weekday, [])
            lines += self.motds.get(month, {}).get("Any", [])
            lines += self.motds.get(month, {}).get(day, [])
            lines += self.motds.get(month, {}).get(weekday, [])
            await respond(msg, "\n".join(lines))
