from __future__ import print_function

import logging
import os
import signal
import sys
import time

our_dir = os.path.dirname(os.path.abspath(__file__))

# For dev setups, we can find the API in the repo itself.
if os.path.exists(os.path.join(our_dir, '../api/zulip')):
    sys.path.insert(0, '../api')

from zulip import Client

def exit_gracefully(signum, frame):
    sys.exit(0)

class RateLimit(object):
    def __init__(self, message_limit, interval_limit):
        self.message_limit = message_limit
        self.interval_limit = interval_limit
        self.message_list = []

    def is_legal(self):
        self.message_list.append(time.time())
        if len(self.message_list) > self.message_limit:
            self.message_list.pop(0)
            time_diff = self.message_list[-1] - self.message_list[0]
            return time_diff >= self.interval_limit
        else:
            return True

class BotHandlerApi(object):
    def __init__(self, client):
        # Only expose a subset of our Client's functionality
        user_profile = client.get_profile()
        self._rate_limit = RateLimit(20, 5)
        self._client = client
        try:
            self.full_name = user_profile['full_name']
            self.email = user_profile['email']
        except KeyError:
            logging.error('Cannot fetch user profile, make sure you have set'
                          ' up the zuliprc file correctly.')
            sys.exit(1)

    def send_message(self, *args, **kwargs):
        if self._rate_limit.is_legal():
            self._client.send_message(*args, **kwargs)
        else:
            logging.error('-----> !*!*!*MESSAGE RATE LIMIT REACHED, EXITING*!*!*! <-----\n'
                          'Is your bot trapped in an infinite loop by reacting to'
                          ' its own messages?')
            sys.exit(1)

def run_message_handler_for_bot(lib_module, quiet, config_file):
    # Make sure you set up your ~/.zuliprc
    client = Client(config_file=config_file)
    restricted_client = BotHandlerApi(client)

    message_handler = lib_module.handler_class()

    class StateHandler(object):
        def __init__(self):
            self.state = None

        def set_state(self, state):
            self.state = state

        def get_state(self):
            return self.state

    state_handler = StateHandler()

    if not quiet:
        print(message_handler.usage())

    def handle_message(message):
        logging.info('waiting for next message')
        if message_handler.triage_message(message=message,
                                          client=restricted_client):
            message_handler.handle_message(
                message=message,
                client=restricted_client,
                state_handler=state_handler
            )

    signal.signal(signal.SIGINT, exit_gracefully)

    logging.info('starting message handling...')
    client.call_on_each_message(handle_message)
