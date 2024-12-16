# -*- coding: utf-8 -*-
# --------------------------------------------------
# chubbcord.py - A Discord client, entirely in your terminal.
#  Inspired by 10cord - Quentin Dufournet, 2023
# --------------------------------------------------
# Built-in
import os
import json
import time
import argparse
import threading
import sys
import subprocess as sp

# 3rd party
from emoji import EMOJI_DATA
import requests
import fake_useragent

from rich import print as rprint
from rich.console import Console

from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout

import re

homedir = os.path.expanduser('~')
confdir = os.path.expanduser('~/.chubbcord')

def parse_args():
    """
    The `parse_args` function is used to parse command line arguments for the user's email,
    password, and channel ID.

    :return: The function `parse_args()` returns the parsed command-line arguments as an
    `argparse.Namespace` object.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-e', '--email',
        help='User email',
        default='foo',
    )
    parser.add_argument(
        '-p', '--password',
        help='User password',
        default='foo',
    )
    parser.add_argument(
        '-c', '--channel',
        help='Channel ID to get messages from',
        default=None
    )
    parser.add_argument(
        '-a', '--attach',
        help='Displays attachments (Requires chafa)',
        action='store_true'
   )
    parser.add_argument(
        '-t', '--token',
        help='Custom user token',
        default=None
    )

    return parser.parse_args()


class MyClient():
    def __init__(self) -> None:
        self.args = parse_args()
        self.url = 'https://discord.com/api/v9'

        if not os.path.exists(confdir):
            os.mkdir(confdir)
        if not os.path.exists(confdir + '/tmp'):
             os.mkdir(confdir + '/tmp')

        if not self.args.token:
            if os.path.exists(homedir + '/.chubbcord/user.token.json'):
                with open(homedir + '/.chubbcord/user.token.json', 'r', encoding='utf-8') as t:
                    data = json.load(t)
                    self.args.token = data['token']
            elif os.path.exists(homedir + '/.chubbcord/token.json'):
                with open(homedir + '/.chubbcord/token.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.user_id = data['user_id']
                    self.token = data['token']
                    self.timestamp = data['timestamp']
                if float(self.timestamp) + 3600 < time.time():
                    self.login()
            else:
                self.login()

        self.headers = {
            'User-Agent': fake_useragent.UserAgent().random,
            'Authorization': self.args.token if self.args.token else self.token
        }


        if self.args.token:
            self.user_id = self.get_my_id()

        self.ids = {}
        self.attachments = []

    def get_my_id(self):
        """
        The function `get_my_id` retrieves the user ID associated with the token from the
        Discord API.

        :return: the user ID associated with the token.
        """

        response = requests.get(
            f'{self.url}/users/@me',
            headers=self.headers,
            timeout=5
        )

        if response.status_code != 200:
            raise Exception(
                f'Get my ID failed : {response.status_code} {response.text}')

        return response.json()['id']

    def login(self):
        """
        The `login` function sends a POST request to a specified URL with login credentials,
        and if
        successful, saves the user ID, token, and timestamp to a JSON file.
        """

        data = {
            'login': self.args.email,
            'password': self.args.password,
            'undelete': False,
            'login_source': None,
            'gift_code_sku_id': None
        }

        response = requests.post(
            f'{self.url}/auth/login',
            json=data,
            timeout=5
        )

        if response.status_code != 200:
            raise Exception(
                f'Login failed : {response.status_code} {response.text}')

        self.user_id = response.json()['user_id']
        self.token = response.json()['token']
        self.timestamp = str(time.time())

        with open(homedir + '/.chubbcord/token.json', 'w', encoding='utf-8') as f:
            json.dump({'user_id': self.user_id, 'token': self.token,
                      'timestamp': self.timestamp}, f, indent=4)

    def get_messages(self):
        """
        The function `get_messages` retrieves the latest 35 messages from a specified
        channel using the Discord API.

        :return: a list of messages.
        """

        params = {
            'limit': '35',
        }

        response = requests.get(
            f'{self.url}/channels/{self.args.channel}/messages',
            params=params,
            headers=self.headers,
            timeout=5
        )

        if response.status_code != 200:
            raise Exception(
                f'Get messages failed : {response.status_code} {response.text}')

        messages = response.json()
        messages.reverse()

        return messages

    def manage_mentions(self, content):
        """
        The function `manage_mentions` replaces user mentions, the
        `@everyone` mention, and the `@here` mention in a given
        content with formatted text.

        :param content: The `content` parameter is a string that
        represents the content of a message
        :return: the modified content after managing mentions.
        """

        if '<@' in content and '<@&' not in content:
            all_user_id = re.findall("<@.?\d\d\d\d\d\d\d\d\d\d\d\d\d\d\d\d\d\d>", content)
            for user_id in all_user_id:
                user_id = content.split('<@')[1].split('>')[0].strip('!')
                if user_id not in self.ids:
                    self.ids[user_id] = self.get_username_from_id(user_id)
                username_in_content = self.ids[user_id]
                content = content.replace(
                        f'<@{user_id}>', f'[bold][dark_orange]@{username_in_content}[/dark_orange][/bold]')
        if '@everyone' in content:
            content = content.replace(
                '@everyone', '[bold][dark_orange]@everyone[/dark_orange][/bold]')
        if '@here' in content:
            content = content.replace(
                '@here', '[bold][dark_orange]@here[/dark_orange][/bold]')

        return content

    def manage_attachments(self, content, message):
        """ Manage attachments in a message (Download, display, etc.)

        :param content: The `content` parameter is a string that
        represents the content of a message
        :param message: The `message` parameter is a dict that
        represents the message object
        :return: the modified content after managing attachments.
        """

        if message['attachments'] != []:
            content += (
                f'[dark_green]{message["attachments"][0]["filename"]}[/dark_green]'
            ) if content == '' else (
                f'\n[dark_green]{message["attachments"][0]["filename"]}[/dark_green]'
            )

            if message['attachments'][0]['url'] not in self.attachments:
                if self.args.attach:
                    file = requests.get(
                        message['attachments'][0]['url'], headers=self.headers
                    )
                    if file.status_code == 200:
                        with open(f'{confdir}/tmp/{message["attachments"][0]["filename"]}', 'wb') as f:
                            f.write(file.content)
                        self.attachments.append(
                            message['attachments'][0]['url']
                        )

        return content

    def manage_referenced_message(self, content, message):
        """ Manage referenced message in a message

        :param content: The `content` parameter is a string that
        represents the content of a message
        :param message: The `message` parameter is a dict that
        represents the message object
        :return: the modified content after managing referenced message.
        """

        try:
            referenced_message = message['referenced_message']['content']
            referenced_message = self.manage_mentions(referenced_message)
            referenced_message = self.manage_attachments(
                referenced_message, message['referenced_message'])
            content += f'\n  [magenta][/magenta] [italic][bright_black]{referenced_message}[/bright_black][/italic]'
        except KeyError:
            referenced_message = None
        except TypeError:
            referenced_message = "Original Message was deleted."
            content += f'\n  [magenta][/magenta] [italic][bright_black]{referenced_message}[/bright_black][/italic]'

        return content

    def print_messages(self, messages):
        """
        The function "print_messages" takes in a list of messages and prints them.

        :param messages: The "messages" parameter is a list of messages that you want to
        print
        """

        for message in messages:
            date = message['timestamp'].replace('T', ' - ').split('.')[0]
            username = message['author']['global_name']
            if username == None:
            	username = message['author']['username']
            content = message['content']
            content = self.manage_mentions(content)
            content = self.manage_attachments(content, message)
            content = self.manage_referenced_message(content, message)

            rprint(
                f' [bold][blue][/blue] [green]\[[/green][red]{username}[/red][green]][/green][/bold] {content}')

            if message['attachments'] != [] and self.args.attach:
                if os.name == 'posix' and 'Chafa version' in sp.getoutput('chafa --version'):
                    rprint(f' ')
                    os.system(
                        f'chafa {homedir}/.chubbcord/tmp/{message["attachments"][0]["filename"]} --size=80x25 --animate=off'
                    )
                    rprint(f' ')

    def diff_messages(self, messages1, messages2):
        """
        The function `diff_messages` takes two lists of messages and returns a new list
        containing messages that are in the first list but not in the second list.

        :param messages1: A list of messages
        :param messages2: An other list of messages

        :return: a list of messages that are present in `messages1` but not in `messages2`.
        """

        return [message for message in messages1 if message not in messages2]

    def send_message(self, content, attachments=[]):
        """
        The `send_message` function sends a message to a specified channel using the
        Discord API.

        :param content: Message content that you want to send.

        :return: the JSON response from the API call.
        """

        data = {
            'content': content,
            'attachments': attachments
        }

        response = requests.post(
            f'{self.url}/channels/{self.args.channel}/messages',
            headers=self.headers,
            json=data,
            timeout=5
        )

        if response.status_code != 200:
            raise Exception(
                f'Send message failed : {response.status_code} {response.text}')

        #self.refresh_screen()
        #os.system(f'printf "\eM\r\e[2K"')

        return response.json()

    def get_username_from_id(self, user_id):
        """
        The function `get_username_from_id` retrieves the username associated with a
        given user ID from the Discord API.

        :param user_id: Unique identifier of a user.

        :return: the username of the user with the given user_id if the response status
        code is 200. Otherwise, it returns the user_id itself.
        """

        try:
            response = requests.get(
                f'https://discordlookup.mesalytic.moe/v1/user/{user_id}',
                timeout=5
            )

            if response.status_code != 200:
                if 'rate limited' in response.text:
                    time.sleep(2)
                    return self.get_username_from_id(user_id)
                return user_id

            return response.json()['username']
        except:
            return user_id

    def request_upload_attachment(self, path, size):
        """
        This function requests an upload link for a file to a specified channel using
        the Discord API.

        :param path: Path of the file you want to send.
        :param size: Size of the file you want to send.

        :return: the JSON response from the API call.
        """

        data = {
            'files': [
                {
                    'filename': path,
                    'file_size': size,
                },
            ],
        }

        response = requests.post(
            f'{self.url}/channels/{self.args.channel}/attachments',
            headers=self.headers,
            json=data,
        )

        if response.status_code != 200:
            raise Exception(
                f'Put attachment failed : {response.status_code} {response.text}')

        return response.json()

    def upload_attachment(self, path, link, filename):
        """
        This function uploads a file to a specified channel using the Discord API.

        :param path: Path of the file you want to send.
        :param link: Upload link of the file you want to send.
        :param filename: Name of the file in Discord storage.

        :return: 1 if the upload was successful.
        """

        params = {
            'upload_id': link.split('upload_id=')[1]
        }

        with open(path, 'rb') as f:
            data = f.read()

        response = requests.put(
            f'https://discord-attachments-uploads-prd.storage.googleapis.com/{filename}',
            params=params,
            headers=self.headers,
            data=data,
        )

        if response.status_code != 200:
            raise Exception(
                f'Put attachment failed : {response.status_code} {response.text}')

        return 1

    def put_attachment(self, path, size, content):
        """
        This function sends a file to a specified channel using the Discord API.

        :param path: The `path` parameter is the path of the file you want to send.
        :param size: The `size` parameter is the size of the file you want to send.
        :param content: The `content` parameter is the message content that you want
        to send.

        :return: Nothing if the file can't be found.
        """

        if not os.path.isfile(path):
            rprint(f'[bold][red]Is {path} a file?[/red][/bold]')
            return

        request_attachment = self.request_upload_attachment(path, size)
        upload_link = request_attachment['attachments'][0]['upload_url']
        upload_filename = request_attachment['attachments'][0]['upload_filename']
        self.upload_attachment(path, upload_link, upload_filename)

        attachment_data = [
            {
                'id': '0',
                'filename': path,
                'uploaded_filename': upload_filename,
            },
        ]

        self.send_message(content, attachment_data)

    def list_friends(self):
        """ Get friends from Discord API """

        response = requests.get(
            f'{self.url}/users/@me/channels',
            headers=self.headers,
            timeout=5
        )

        if response.status_code != 200:
            raise Exception(
                f'Get friends failed : {response.status_code} {response.text}')

        list_friends = [element for element in response.json()
                        if element['type'] == 1]
        self.friends = list_friends

    def list_guilds(self):
        """ Get guilds's user from Discord API """

        response = requests.get(
            f'{self.url}/users/@me/guilds',
            headers=self.headers,
            timeout=5
        )

        if response.status_code != 200:
            raise Exception(
                f'Get guilds failed : {response.status_code} {response.text}')

        self.guilds = response.json()

        for guild in self.guilds:
            self.list_channels_from_guild(guild['id'])
            time.sleep(0.5)

    def rprint_friends(self):
        """ Print friends in a rich format """

        content = ''
        local_id = 0

        for friend in self.friends:
            local_id += 1
            friend_print = f'   [#E01E5A]{local_id}[/#E01E5A] - ' + \
                f'{friend["recipients"][0]["username"]} - {friend["id"]}'
            friend_length = len(friend_print.replace(
                '[#E01E5A]', '').replace('[/#E01E5A]', ''))

            # Emoji or Special char. are 2 chars long
            for char in friend["recipients"][0]["username"]:
                if char in EMOJI_DATA:
                    friend_length += 1

            if friend_length > 80:
                friend_print = friend_print.replace(
                    friend["recipients"][0]["id"],
                    friend["recipients"][0]["id"][:80 -
                                                  friend_length - 8] + '...'
                )
                friend_length = len(friend_print.replace(
                    '[#E01E5A]', '').replace('[/#E01E5A]', '')) + 1

            friend_print += ' ' * \
                (80 - friend_length) + ' \n'

            self.friends[self.friends.index(friend)]['local_id'] = local_id

            content += friend_print

        content += ' '

        return content

    def list_channels_from_guild(self, guild_id):
        """ Get channels from a guild

        :param guild_id: the id of the guild you want to get channels from
        """

        response = requests.get(
            f'{self.url}/guilds/{guild_id}/channels',
            headers=self.headers,
            timeout=5
        )

        if response.status_code != 200:
            raise Exception(
                f'Get channels failed : {response.status_code} {response.text}')

        list_channels = [channel for channel in response.json()
                         if channel['type'] == 0]
        self.guilds[self.guilds.index(
            [guild for guild in self.guilds if guild['id'] == guild_id][0])]['channels'] = list_channels

    def rprint_guilds(self):
        """ Print guilds and channels in a rich format """

        # TODO: Rework or idk, the code looks horrible af
        content = ''
        local_id = 0

        for guild in self.guilds:
            guild_print = f'   - {guild["name"]} -'
            if guild['owner']:
                guild_print += ' [#E01E5A](owner)[/#E01E5A]'

            guild_length = len(guild_print.replace(
                '[#E01E5A]', '').replace('[/#E01E5A]', '')
            )

            if guild_length < 80:
                guild_print += ' ' * \
                    (79 - guild_length) + ' \n'

            content += guild_print

            for channel in self.guilds[self.guilds.index(guild)]['channels']:
                local_id += 1
                channel_print = f'      [#E01E5A]{local_id}[/#E01E5A] - {channel["name"]} - {channel["id"]}'
                channel_length = len(channel_print.replace(
                    '[#E01E5A]', '').replace('[/#E01E5A]', ''))

                # Emoji or Special char. are 2 chars long
                for char in channel['name']:
                    if char in EMOJI_DATA or char in ['｜']:
                        channel_length += 1

                if channel_length > 80:
                    channel_print = channel_print.replace(
                        channel['name'], channel['name'][:80 - channel_length - 8] + '...')
                    channel_length = len(channel_print.replace(
                        '[#E01E5A]', '').replace('[/#E01E5A]', '')) + 1

                channel_print += ' ' * \
                    (79 - channel_length) + ' \n'

                self.guilds[self.guilds.index(guild)]['channels'][self.guilds[self.guilds.index(guild)]['channels'].index(
                    channel)]['local_id'] = local_id

                content += channel_print

        content += ' '

        return content

    def refresh_screen(self):
        """ Refresh the screen and print the last messages """

        os.system('clear') if os.name == 'posix' else os.system('cls')
        self.messages = []
        new_messages = self.get_messages()
        diff_messages = self.diff_messages(new_messages, self.messages)
        self.print_messages(diff_messages)
        self.messages = new_messages

    def internal_command(self, command):
        """
        The `internal_command` function is used to execute internal commands.

        :param command: The `command` parameter is the command you want to execute.
        """

        if command == ':help':
            rprint()
            rprint('[#7289DA]' +
                   '    [dark_orange]COMMAND LIST:       [/dark_orange] \n' +
                   '      :help - Show this help      \n' +
                   '      :q - Exit chubbcord         \n' +
                   '      :attach - Attach a file     \n' +
                   '        (ex: :attach:poop.png:text)\n'+
                   '      :cr - Clear and Refresh     \n' +
                   '      :li - List Guilds & Chan.   \n'
                   '      :dm - List Direct Messages  \n'
                   '      :we - Print welcome message \n'
                   '[/#7289DA]'
                   )
            rprint()

        elif command == ':q':
            if self.running:
                self.kill_thread = True
                self.main_loop_thread.join()
            self.clean()
            sys.exit()

        elif command == ':cr':
            self.refresh_screen()

        elif ':attach:' in command:
            attachment = command.split(':')[2]
            if len(command.split(':')) == 4:
                content = command.split(':')[3]
            else:
                content = ''
            if os.path.exists(attachment):
                self.put_attachment(
                    attachment, os.path.getsize(attachment), content
                )
            else:
                rprint('[bold][red]File not found[/red][/bold]')

        elif command == ':we':
            self.print_welcome()

        elif command == ':li':
            rprint('\n[#7289DA]' +
                   ' \n' +
                   self.rprint_guilds()
                   )

            with patch_stdout(raw=True):
                self.args.channel = prompt('Channel ID: ')
            try:
                int(self.args.channel)
            except ValueError:
                if self.running:
                    self.kill_thread = True
                    self.main_loop_thread.join()
                sys.exit('Channel ID must be an integer')
            except KeyboardInterrupt:
                if self.running:
                    self.kill_thread = True
                    self.main_loop_thread.join()
                self.clean()
                sys.exit()

            if self.running:
                self.kill_thread = True
                self.main_loop_thread.join()
                self.running = False

            self.args.channel = self.list_id[int(self.args.channel)]
            self.main_loop_thread = threading.Thread(target=self.main_loop)
            self.main_loop_thread.start()
            self.refresh_screen()

        elif command == ':dm':
            rprint('\n[#7289DA]' +
                   ' \n' +
                   self.rprint_friends()
                   )

            with patch_stdout(raw=True):
                self.args.channel = prompt('Message ID: ')
            try:
                int(self.args.channel)
            except ValueError:
                if self.running:
                    self.kill_thread = True
                    self.main_loop_thread.join()
                sys.exit('Channel ID must be an integer')
            except KeyboardInterrupt:
                if self.running:
                    self.kill_thread = True
                    self.main_loop_thread.join()
                self.clean()
                sys.exit()

            if self.running:
                self.kill_thread = True
                self.main_loop_thread.join()
                self.running = False

            self.args.channel = self.friends[int(self.args.channel) - 1]['id']
            self.main_loop_thread = threading.Thread(target=self.main_loop)
            self.main_loop_thread.start()
            self.refresh_screen()

    def print_welcome(self):
        """ Print the welcome message and the commands list """
        whoami = self.get_username_from_id(self.user_id)
        rprint('\n[#7289DA]' +
               f'                                           [dark_orange]Available commands: [/dark_orange]\n' +
               f'    [dark_orange]░█▀▀░█░█░█░█░█▀▄░█▀▄░█▀▀░█▀█░█▀▄░█▀▄[/dark_orange]     :li - List Guilds & Channels\n' +
               f'    [dark_orange]░█░░░█▀█░█░█░█▀▄░█▀▄░█░░░█░█░█▀▄░█░█[/dark_orange]     :dm - List Friends DM \n' +
               f'    [dark_orange]░▀▀▀░▀░▀░▀▀▀░▀▀░░▀▀░░▀▀▀░▀▀▀░▀░▀░▀▀░[/dark_orange]     :attach - Attach a file\n' +
               f'                                             :help - Full command list\n' +
               f'          Logged in as: [dark_orange]{whoami}[/dark_orange]           :q  - Exit chubbcord\n[/#7289DA]'
               )

    def main_loop(self):
        """
        The main_loop function retrieves and prints messages, then continuously checks for new
        messages and prints any differences.
        """

        self.messages = self.get_messages()
        self.print_messages(self.messages)
        self.kill_thread = False
        self.running = True

        started = time.time()
        while not self.kill_thread:
            if time.time() - started >= 3:
                new_messages = self.get_messages()
                diff_messages = self.diff_messages(new_messages, self.messages)
                self.print_messages(diff_messages)
                self.messages = new_messages
                started = time.time()
            else:
                time.sleep(0.1)

    def clean(self):
        """ Clean the .chubbcord folder """

        for file in os.listdir(f'{confdir}/tmp'):
            os.remove(f'{confdir}/tmp/{file}')

    def main(self):
        """
        The main function starts a thread for the main loop and then waits for user input to send a
        message.
        """

        try:
            os.system(f'termtitle "chubbcord: a discord client -- {self.get_username_from_id(self.user_id)}"')
        except:
            pass

        self.print_welcome()

        self.running = False
        self.list_id = {}

        def query_data():
            """ Query data from Discord API in a thread """
            self.list_friends()
            self.rprint_friends()
            self.list_guilds()
            self.rprint_guilds()

        def loading_bar(symbol):
            """ Simple loading bar while we fetch the datas from the API

            :param symbol: the current symbol of the loading bar
            :return: the next symbol of the loading bar
            """
            symbols = [' ', '/', '-', '\\']
            return symbols[symbols.index(symbol) + 1] if symbols.index(symbol) < 3 else symbols[0]

        query_data_thread = threading.Thread(target=query_data)
        query_data_thread.start()

        symbol = ' '
        while query_data_thread.is_alive():
            symbol = loading_bar(symbol)
            print(f' Loading... {loading_bar(symbol)}', end='\r')
            time.sleep(0.1)

        for guild in self.guilds:
            for channel in guild['channels']:
                self.list_id[channel['local_id']] = channel['id']

        if not self.args.channel:
            while self.args.channel is None:
                try:
                    with patch_stdout(raw=True):
                        command = prompt(' READY >> ')
                    if command == ':cr' or ':attach' in command:
                        print('Please, select a channel first')
                    else:
                        self.internal_command(command)
                except KeyboardInterrupt:
                    if self.running:
                        self.kill_thread = True
                        self.main_loop_thread.join()
                    self.clean()
                    sys.exit()

        else:
            self.main_loop_thread = threading.Thread(target=self.main_loop)
            self.main_loop_thread.start()
            self.refresh_screen()

        commands_list = [':q', ':help', ':cr', ':li', ':dm', ':we']

        while 1:
            try:
                time.sleep(1)
                with patch_stdout(raw=True):
                    content = prompt(' >> ', wrap_lines=False, multiline=False)
                if content != '' and ':attach' not in content and content not in commands_list:
                    message_sent = self.send_message(content)
                if content == '':
                    self.refresh_screen()
                    self.internal_command(content)
                else:
                    self.internal_command(content)

            except KeyboardInterrupt:
                if self.running:
                    self.kill_thread = True
                    self.main_loop_thread.join()
                self.clean()
                sys.exit()


def main():
    """ This main function is used to make an entry point for the program."""

    client = MyClient()
    client.main()


if __name__ == "__main__":
    main()
