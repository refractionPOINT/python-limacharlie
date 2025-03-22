from typing import Any, Dict, List, Optional
from . import Manager
import json
import cmd
import os.path
try:
    import readline
except ImportError:
    readline = None

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

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
        self._console = Console()  # Rich console for nice output
        self.should_exit = False
        if readline:
            readline.set_completer_delims( ' ' )
        super(AIChat, self).__init__()
        self._setPrompt()

    def onecmd(self, line):
        """Override onecmd to check should_exit after each command."""
        super().onecmd(line)
        return self.should_exit

    def preloop( self ):
        if readline and os.path.exists( self._histfile ):
            readline.read_history_file( self._histfile )

    def postloop( self ):
        if readline:
            readline.set_history_length( self._histfile_size )
            readline.write_history_file( self._histfile )

    def precmd( self, line: str ):
        if line.strip() and not line.strip().startswith('/'):
            # Only show user messages, not commands
            self._console.print(Panel(
                Text(line, style="bold white"),
                title="[bold blue]User[/bold blue]",
                border_style="blue"
            ))
        return line

    def _logOutput( self, output: str, isNoPrint: bool = False, isMarkdown: bool = False, isError: bool = False ):
        if not isNoPrint:
            if isError:
                self._console.print(Panel(
                    Text(output, style="bold red"),
                    title="[bold red]Error[/bold red]",
                    border_style="red"
                ))
            elif isMarkdown:
                # Render markdown using rich inside a panel
                self._console.print(Panel(
                    Markdown(output),
                    title="[bold green]AI Agent[/bold green]",
                    border_style="green"
                ))
            else:
                # For system messages or other non-markdown content
                self._console.print(Panel(
                    Text(output, style="bold yellow"),
                    title="[bold yellow]System[/bold yellow]",
                    border_style="yellow"
                ))

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
                self._logOutput( 'No interactions received from the agent:\n' + json.dumps( resp, indent = 2 ), isError=True )
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
                self._logOutput( 'No interactions received from the agent:\n' + json.dumps( resp, indent = 2 ), isError=True )

        return False

    def do_slash_exit( self, inp: str ) -> bool:
        '''Exit the chat session.'''
        self.should_exit = True
        return True

    def default( self, line: str ) -> None:
        '''Handle any input as a chat message unless it's /exit.'''
        if line.strip() == '/exit':
            self.should_exit = True
            return
        self._handle_chat(line)
        return

    def _outputInteractions( self, toRender: List[Dict[str, Any]] ) -> None:
        # Filter out the interactions that don't have a "id" since it means they came from us.
        toRender = [ d for d in toRender if not d.get('user_interaction', None) ]
        for d in toRender:
            if "ai_interaction" in d:
                # Render AI messages as markdown
                self._logOutput( d['ai_interaction']['msg'], isMarkdown=True )
            elif "ai_function_call" in d:
                # Render tool calls as markdown
                for fc in d['ai_function_call']:
                    self._logOutput( f"Calling function: {fc['name']}({json.dumps(fc['args'])})", isMarkdown=False )
            elif "tool_results" in d:
                # Render tool results as markdown
                for tr in d['tool_results']:
                    self._logOutput( f"Tool result: {tr['name']}({json.dumps(tr['result'])})", isMarkdown=True )
            else:
                # For other interactions (like tool calls), show the raw JSON
                self._logOutput( json.dumps( d, indent = 2 ) )

    def _setPrompt( self ):
        self.prompt = f"ISID {self._isid} | Agent {self._agentName} | > "

    def emptyline(self):
         return False

if '__main__' == __name__:
    main()