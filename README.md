RunCommand is a vim plugin which helps you to edit and run shell command within
a vim buffer.

===== Install

Your vim should be compiled with Python support.

===== Usage

RunCommand assumes you have two monitors, and there is a terminal window on
each monitor. Each terminal is running Linux GNU screen, and the two GNU screen
sessions have the same number of windows. Last, Vim is running in one of the
window of the one of the GNU screen. If all of these requirements are met, the
RunCommand will:

1) <Leader>r will load a command file in a vim window. It will also change
the active window of the other GNU screen to the window with the same active
window number of the GNU screen session where Vim is running. It will also
change the current working directory (CWD) of the shell in that window to the
current working directory of the Vim session.

2) In the Vim window for the command file, you can edit shell commands. In Vim
normal mode, press <Enter> will send the current line as shell command to the
active window of the other screen session to execute.  In Vim visual mode,
select multiple lines of text and press <Enter> will send all these lines
(joined by one space) to the active window of the other screen session to
execute. Notice that in multiple line mode, if a line ends with '\', then the
next line is joined with it without a whitespace.

3) RunCommand maintains one command file for each directory in a temporary
directory, so if you load the command file (by <Leader>r) from a working
directory where you use RunCommand before, you will see all the commands you
used before.
