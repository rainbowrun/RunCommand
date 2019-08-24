from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import os.path
import re
import subprocess
import tempfile
import vim

FREQUENT_SHELL_COMMAND = """
# Usage:
#     - In normal mode, press <Enter> to run that line.
#     - Visual select multiple lines and <Enter> to run those lines.

# Notes:
# In visual multiple lines mode, all the leading and trailing whitespaces of a
# line are stripped and then these lines are joined together with a whitespace.
# A backslash at the end of a line means the following line will be joined with
# this line WITHOUT a space.

# These set the target screen session and window number.
$target_screen=%s
$target_window=%s

# Frequent commands.
ls
ls -l
git status
"""


def ListScreenSession():
  screens = []
  for line in os.popen('/usr/bin/screen -list').read().splitlines():
    line = line.strip()
    if '(Attached)' in line or '(Detached)' in line or '(Multi)' in line:
      screens.append(line.split()[0])
  return screens


# Learn all the existing screen sessions.
#
# Return a tuple with 3 elements: (local screen, local window, remote screen)
def DetectScreenSessionAndWindow():
  # Detect local screen.
  if 'STY' not in os.environ:
    print('Vim is not running in a screen session')
    return (None, None, None)
  local_screen_pid = os.environ['STY'].split('.')[0]

  # List all the screen session and pick any screen other than the current
  # screen in which the vim is running as remote screen.
  #
  # It is weird that 'screen -list' returns 1 so that we can not use
  # subprocess.check_output.
  remote_screen_pid = None
  for screen in ListScreenSession():
      screen_pid = screen.split('.')[0]
      if local_screen_pid != screen_pid:
          remote_screen_pid = screen_pid
          break

  # Return local screen, local window and remote screen.
  return (local_screen_pid, os.environ['WINDOW'], remote_screen_pid)


def NormalGetCommand():
  return vim.current.line


def VisualGetCommand():
  command = vim.eval('GetVisualSelection()')

  # Get rid of the newline and the extra whitespace of each line.
  clean_lines = []
  for line in command.splitlines():
    line = line.strip()
    if not line:
      continue

    # The following code which process the leading comment and the shell prompt
    # is design for the case where example command lines which are usually
    # commented out in the source files, such as
    #    // $ borgcfg x.borg
    #    //   --vars=foo=bar
    #    //   up

    # Process the comment at the beginning of the line.
    if line.startswith('#'):
      line = line[1:]
      line = line.lstrip()
    elif line.startswith('//'):
      line = line[2:]
      line = line.lstrip()

    # Process the possibly '$' shell prompt
    if line.startswith('$'):
      line = line[1:]
      line = line.lstrip()
      
    # Process the backslash at the end of the line.
    if line.endswith('\\'):
      # If a line ends with backslash, it is meant to join with the next line
      # without any whitespace.
      line = line[:-1]     # Remove backslash first
    else:
      line += ' ' # Put a space at the end of the line so the following
                  # line is joined with this line separated by this space.
                  # It is fine with an extra space at the end of the whole
                  # command.

    clean_lines.append(line)

  return ''.join(clean_lines)


def GetTargetScreenAndWindowFromCommandFile():
  # Detect the target screen and target window by reading the current buffer.
  target_screen = None
  target_window = None
  for line in vim.current.buffer:
      if line.startswith('$target_screen='):
          target_screen = line.strip().split('=')[1]
          break
  for line in vim.current.buffer:
      if line.startswith('$target_window='):
          target_window = line.strip().split('=')[1]
          break
  if target_screen is None or target_window is None:
      print('Can not figure out target screen or target window.')
      return

  return target_screen, target_window


def RunShellCommand(get_command_func):
  vim.command("wall")

  (target_screen, target_window) = GetTargetScreenAndWindowFromCommandFile()

  command = get_command_func().strip()

  # Force the remote window to exit copy mode.
  if command == '^c' or command == '^C':
    subprocess.check_call('/usr/bin/screen -S %s -X msgwait 0' % target_screen,
                                     shell=True)
    subprocess.check_call(
        '/usr/bin/screen -S %s -p %s -X stuff "^c\n"' %
            (target_screen, target_window),
        shell=True,
        stdout=open('/dev/null', 'w'),
        stderr=subprocess.STDOUT)

    subprocess.check_call('/usr/bin/screen -S %s -X msgwait 5' % target_screen,
                                     shell=True)
    return

  # Run the remote command and ignore any output since it is available in the
  # other terminal by using '-X stuff'. This one has the limitation of buffer
  # size so we actually preferred the 'readbuf && paste' approach.
  #command = command.replace("\"", "\\\"").replace("'", "\\'")
  #subprocess.check_call(
  #    '/usr/bin/screen -S %s -p %s -X stuff "%s\n"' % (target_screen,
  #                                                     target_window, command),
  #    shell=True,
  #    stdout=open('/dev/null', 'w'),
  #    stderr=subprocess.STDOUT)

  # An alternative to implement by using 'readbuf && paste'.
  # Notice that this does not work if the source_screen and the target_screen
  # are the same GNU screen session. Instead, two separated commands have to be
  # used which introduces some delay.
  with open('/tmp/screen-exchange', 'w') as output_file:
    output_file.write(command + '\n')
  subprocess.check_call(
      '/usr/bin/screen -S %s -p %s -X eval "readbuf" "paste ."' %
          (target_screen, target_window),
      shell=True,
      stdout=open('/dev/null', 'w'),
      stderr=subprocess.STDOUT)
  #subprocess.check_call(
  #    '/usr/bin/screen -S %s -p %s -X readbuf' %
  #        (target_screen, target_window),
  #    shell=True,
  #    stdout=open('/dev/null', 'w'),
  #    stderr=subprocess.STDOUT)
  #subprocess.check_call(
  #    '/usr/bin/screen -S %s -p %s -X paste .' %
  #        (target_screen, target_window),
  #    shell=True,
  #    stdout=open('/dev/null', 'w'),
  #    stderr=subprocess.STDOUT)


# Show and target output window and change its working directory.
def PrepareTargetWindow(target_screen, target_window):
  # Making the target window visible.
  #
  # Since user friendly session name (main, aux, middle, etc.) may be specified,
  # we will try to figure its pid.
  target_screen_pid = None
  for screen in ListScreenSession():
      if target_screen in screen:
          target_screen_pid = screen.split('.')[0]
          break
  if target_screen_pid is None:
      print('Invalid target_screen %s' % target_screen)
      return

  if target_screen_pid in os.environ['STY']:   # Local, split half.
      subprocess.check_call(
          '/usr/bin/screen -S %s -X eval "only" "split" "focus" "select %s" "focus"' %
          (target_screen, target_window),
          shell=True,
          stdout=open('/dev/null', 'w'),
          stderr=subprocess.STDOUT)
  else:  # Remote, make it fullscreen.
      # Focus on the remote window with message disabled in case the remote
      # window has already been focused.
      subprocess.check_call('/usr/bin/screen -S %s -X msgwait 0' % target_screen,
                                       shell=True)
      subprocess.check_call(
          '/usr/bin/screen -S %s -X eval "only" "select %s"' %
          (target_screen, target_window),
          shell=True)
      subprocess.check_call('/usr/bin/screen -S %s -X msgwait 5' % target_screen,
                                       shell=True)

  # Set working directory.
  subprocess.check_call(
      '/usr/bin/screen -S %s -p %s -X stuff "cd %s\n"' %
      (target_screen, target_window, os.getcwd()),
      shell=True)


def MoveToNthWindowLeftToRight(n):
  if n == 'e':
    return
  elif n == 's':
    vim.command('new')
  elif n == 'v':
    vim.command('only')
    vim.command('vnew')
  else:
    vim.command('3wincmd h')
    right_step = int(n) - 1
    if right_step > 0:
      vim.command('%swincmd l' % right_step)


def RN(n):
  # Pick up the target screen session.
  local_screen, local_window, remote_screen = DetectScreenSessionAndWindow()
  if local_screen is not None and remote_screen is not None:
      target_screen = remote_screen
      target_window = local_window  # The same window number
  else:
      print('This feature requires two GNU screen sessions. We only found'
            '%s %s' % (local_screen, remote_screen))
      return

  # Prepare the command file and load it.
  # First read its content, update the screen/window setting and write it back.
  #
  # Now all the workspace share the same command file, let's see if this fits in
  # my workflow better.
  command_file_path = os.path.join(
      os.environ['HOME'],
      'tmp',
      os.getcwd().replace('/', 'YYY') + '-frequent-shell-command.sh')
  if os.path.exists(command_file_path):
    lines = []
    with open(command_file_path) as command_file:
      for line in command_file:
          lines.append(line.rstrip())
  else:
    lines = FREQUENT_SHELL_COMMAND.splitlines()
  with open(command_file_path, 'w') as command_file:
    for line in lines:
        if line.startswith('$target_screen='):
            command_file.write('$target_screen=%s\n' % target_screen)
        elif line.startswith('$target_window='):
            command_file.write('$target_window=%s\n' % target_window)
        else:
            command_file.write(line + '\n')
  MoveToNthWindowLeftToRight(n)
  vim.command('edit! %s' % command_file_path)

  # Set up mapping for the buffer.
  vim.command('nnoremap <buffer> <CR> '
              ':py RunShellCommand(NormalGetCommand)<CR>')
  vim.command('vnoremap <buffer> <CR> '
              ':py RunShellCommand(VisualGetCommand)<CR>')

  PrepareTargetWindow(target_screen, target_window)


# Map <Leader>r to default action.
vim.command("nnoremap <Leader>re :py RN('%s')<CR>" %
                (leading_character, window, function_name, window))
MapFunction('RN', 'r', ['e', 's', 'v', '1', '2', '3', '4'])
