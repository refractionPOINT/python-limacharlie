from functools import cache
from typing import Any, Dict, List, Optional
from . import Manager
from .Replay import Replay
import json
import cmd
import sys
try:
    import pydoc
except:
    pydoc = None
from tabulate import tabulate
from termcolor import colored
import os.path
try:
    import readline
except ImportError:
    readline = None

from .utils import Spinner

# Type hint for extension request response
ExtensionResponse = Dict[str, Any]

def main( sourceArgs: list[str] | None = None ):
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie ai-chat' )

    parser.add_argument( '--isid',
                         type = str,
                         required = False,
                         dest = 'isid',
                         default = None,
                         help = 'optional interactive session id to re-use.' )

    parser.add_argument( '--agent-name',
                         type = str,
                         required = False,
                         dest = 'agentName',
                         default = None,
                         help = 'name of the agent to use.' )

    args = parser.parse_args( sourceArgs )

    AIChat( Manager(), args.agentName, args.isid ).cmdloop()
    return

class AIChat( cmd.Cmd ):
    def __init__( self, lc: Manager, agentName: str, isid: Optional[str] = None ):
        self.intro = 'This LimaCharlie feature is in Beta, this capability requires the ext-ai-agent-engine extension to be installed.\nType /exit to quit.'
        self._billed = 0
        self._histfile = os.path.expanduser( '~/.limacharlie_ai_chat_history' )
        self._histfile_size = 1000
        self._lc = lc
        self._q = None
        self._outFile: Optional[str] = None
        self._isid: Optional[str] = isid
        self._agentName: Optional[str] = agentName
        if readline:
            readline.set_completer_delims( ' ' )
        super(AIChat, self).__init__()
        self._setPrompt()

    def preloop( self ):
        if readline and os.path.exists( self._histfile ):
            readline.read_history_file( self._histfile )

    def postloop( self ):
        if readline:
            readline.set_history_length( self._histfile_size )
            readline.write_history_file( self._histfile )

    def precmd( self, line: str ):
        self._logOutput( line, isNoPrint = True )
        return line

    def _logOutput( self, output: str, isNoPrint: bool = False ):
        print( output )

    def _handle_chat( self, inp: str ) -> bool:
        '''Send a message to the AI agent and display its response.
        
        Args:
            inp (str): The message to send to the AI agent.
        '''
        # If no input, just return
        if not inp:
            return False

        # If we don't have an ISID yet, we need to start a new session
        if self._isid is None:
            # Create the initial request
            request: Dict[str, Any] = {
                'initial_message': {
                    'msg': inp,
                    'data': {},
                },
                'mode': 'interactive',
            }
            
            # If agent name was specified, use it
            if self._agentName:
                request['agent_definition'] = self._agentName

            # Start the session
            resp: ExtensionResponse = self._lc.extensionRequest('ext-ai-agent-engine', 'start_session', request)
            resp = resp['data']

            # Store the ISID for future interactions
            if 'isid' in resp:
                self._isid = resp['isid']
                self._setPrompt()
            
            # Display initial interactions
            if 'interactions' in resp:
                self._outputInteractions(resp['interactions'])
            else:
                self._logOutput( 'No interactions received from the agent:\n' + json.dumps( resp, indent = 2 ) )
        else:
            # We have an existing session, submit a user interaction
            request: Dict[str, Any] = {
                'isid': self._isid,
                'message': {
                    'msg': inp,
                    'data': {},
                },
            }
            
            # Submit the interaction
            resp: ExtensionResponse = self._lc.extensionRequest('ext-ai-agent-engine', 'submit_user_interaction', request)
            resp = resp['data']
            
            # Display new interactions
            if 'interactions' in resp:
                self._outputInteractions(resp['interactions'])
            else:
                self._logOutput( 'No interactions received from the agent:\n' + json.dumps( resp, indent = 2 ) )

        return False

    def do_exit( self, inp: str ) -> bool:
        '''Exit the chat session.'''
        return False  # Not used anymore

    def do_slash_exit( self, inp: str ) -> bool:
        '''Exit the chat session.'''
        return True

    def default( self, line: str ) -> None:
        '''Handle any input as a chat message unless it's /exit.'''
        if line.strip() == '/exit':
            self.stop = True  # This is how cmd.Cmd handles stopping
            return
        self._handle_chat(line)
        return

    def _outputInteractions( self, toRender: List[Dict[str, Any]] ) -> None:
        # Filter out the interactions that don't have a "id" since it means they came from us.
        toRender = [ d for d in toRender if d.get('id', None) ]
        for d in toRender:
            if "ai_interaction" in d:
                self._logOutput( d['ai_interaction']['msg'] )
            else:
                self._logOutput( json.dumps( d, indent = 2 ) )

    def _setPrompt( self ):
        self.prompt = f"ISID {self._isid} | Agent {self._agentName} | > "

    def emptyline(self):
         return False

if '__main__' == __name__:
    main()