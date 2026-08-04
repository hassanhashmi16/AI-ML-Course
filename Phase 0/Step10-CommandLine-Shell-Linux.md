# Step 10: Command Line, Shell & Linux

> **What it covers:** Navigating and manipulating the filesystem, pipes and redirection, permissions, processes and environment variables, SSH and remote machines, WSL on Windows, and shell scripting — the one skill every later step assumes and none of them teach.

---

## The Problem

Every tool you'll use from here on is driven from a terminal. `uv` (Step 7), Docker (Step 40), `kubectl` (Step 69), a rented GPU box (Step 68), every cloud CLI — all of them expect you to type commands, not click buttons. And the machines you deploy to are Linux even though your laptop isn't.

Without this step, every later one starts with you googling "how to unzip a file in Linux" while a rented GPU burns money. With it, the terminal becomes the fastest tool you own.

---

## Foundational Concepts

### The shell is a program, not a magic box

The **shell** (bash, zsh, fish) is a program that reads your typed line, splits it into a command plus arguments, and runs it. It's a programming environment: it has variables, conditionals, and loops. When you type `echo hello`, the shell looks up the `echo` program, passes it the argument `hello`, and prints it.

### The shell finds programs via `$PATH`

When you type a command that isn't a shell keyword, the shell searches the directories listed in the `$PATH` environment variable, in order, for a file with that name:

```bash
echo $PATH
# /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

which echo        # shows which file actually runs
# /usr/bin/echo
```

**What `$PATH` actually is:** a single list of folder locations, separated by `:`. It's the same concept as the PATH variable in Windows' Environment Variables dialog — the places the OS checks when you type a command name. It is *not* your current working directory (`pwd` shows that, and `cd` doesn't change `$PATH`).

**What lives in those folders:** programs — files with names like `echo`, `grep`, `python`. `$PATH` stores the *folder locations*; each folder contains the actual programs. Type a name, and the shell walks the folder list looking for a matching file, first match wins. When an installer (uv, CUDA, a cloud CLI) "adds itself to PATH," it's appending its own `bin` folder to this list so its commands work from anywhere.

If a program isn't in `$PATH`, you can run it by giving its path: `./my_script.sh`.

### Everything is a file

On Linux, nearly everything is a file: documents, directories, devices, even kernel settings (under `/sys`). That's why a single set of tools (`ls`, `cat`, `cp`, `rm`) covers so much. **Directories are themselves files** — a directory file's content is a list of names pointing to other files, which is why `ls` "lists" it and why permissions apply to directories too (`x` = allowed to enter). Every path ultimately resolves to a file; directories are just the files that organize the others.

### Every program has three streams

Standard input (stdin, where it reads from), standard output (stdout, where it prints), and standard error (stderr, where it reports problems). Normally all three connect to your terminal. The whole power of the shell comes from rewiring these streams: **redirect** them to files, or **pipe** one program's output into another's input.

---

## 10.1 — Navigating & Manipulating the Filesystem

### Where am I, what's here, go there

```bash
pwd                # print working directory — where am I?
ls                 # what's here?
ls -l              # long listing: permissions, owner, size, date
ls -a              # include hidden files (starting with .)
ls -la             # both — the default "look around" command
cd /path/to/dir    # go there
cd ~               # go home
cd ..              # go up one level
cd -               # back to the previous directory
```

A path starting with `/` is **absolute** (from the root of the filesystem). Any other path is **relative** (from where you are). `.` means "here", `..` means "parent":

```bash
cd /home/you/projects     # absolute path
cd ../..                  # relative: up two levels
../../bin/echo hello      # paths compose: "go up two, then into bin/echo" — runs it directly
```

### Manipulating files and directories

```bash
mkdir my-project        # make a directory
mkdir -p a/b/c          # make nested directories in one shot
touch notes.md          # create an empty file (or update its timestamp)

cp notes.md backup.md   # copy a file
cp -r src/ src-copy/    # copy a directory (recursive)
mv old.md new.md        # rename / move a file
rm notes.md             # delete a file — no trash, it's gone
rm -rf my-project/      # delete a directory and everything in it, forever
```

**`rm -rf` is permanent.** There is no undo. Double-check the path before you press enter.

### Reading files

```bash
cat train.log        # print the whole file
head -20 train.log   # first 20 lines
tail -20 train.log   # last 20 lines
tail -f train.log    # follow the file as it grows (Ctrl+C to stop)
less train.log       # scroll through a big file (q to quit)
```

`tail -f` is the command you'll live in while training models — it shows log lines as they're written.

### Finding things

```bash
grep "error" train.log          # lines containing "error"
grep -i "cuda" config.yaml      # case-insensitive
grep -r "learning_rate" .       # search all files under the current dir

find . -name "*.py"                     # all Python files below here
find . -name "*.ckpt" -size +1G         # checkpoints larger than 1GB
find . -name "*.py" | xargs wc -l | tail -1   # total lines in a project
find . -name "*.log" -mtime -1          # files modified in the last day
```

`grep` searches *inside* files; `find` searches *for* files by name and attributes (size, age). They're different tools — you'll use both constantly.

### Tab completion, history, and the two Ctrl keys

- **Tab** completes paths and command names. Press it early and often.
- **Ctrl+R** searches your command history — type part of a previous command, press Ctrl+R to cycle matches.
- **Ctrl+C** cancels the running command; **Ctrl+L** clears the screen.

---

## 10.2 — Pipes, Redirection & Composing Commands

### The three redirects

| Symbol | What it does |
|---|---|
| `>` | Write stdout to a file (overwrite) |
| `>>` | Append stdout to a file |
| `2>` | Write stderr to a file |
| `2>&1` | Send stderr to the same place as stdout |
| `\|` | Pipe: send one command's stdout as the next command's stdin |

```bash
echo hello > hello.txt     # write
cat hello.txt              # hello
echo again >> hello.txt    # append
cat < hello.txt            # feed a file as stdin
python train.py > output.log 2> errors.log    # split the two streams
python train.py > full.log 2>&1               # combine them
```

**Key insight:** `>` and `|` are done *by the shell*, not by the programs. `echo` doesn't know about `>`. That's why `sudo echo 3 > /sys/...` fails even with `sudo` — the *shell* opens the file, and the shell isn't root. The fix is `echo 3 | sudo tee /sys/...`, because `tee` (running as root) opens the file.

### Pipes: composing programs

A pipe takes the stdout of one program and feeds it as stdin to the next. This is the shell's superpower — small programs, each doing one thing, chained into pipelines:

```bash
# Count how many lines contain "loss"
cat train.log | grep "loss" | wc -l

# Take the first 5 lines
ls -l / | head -5

# Watch a log live, keeping only errors
tail -f train.log | grep --line-buffered "ERROR"
```

Think of a pipeline as a data-processing assembly line: each stage filters or transforms, and the data flows through one line at a time. For AI work, this is how you inspect training logs, parse experiment outputs, and summarize results without ever opening a file in an editor.

**A realistic example** — extract all loss values from a training log:

```bash
grep "loss:" train.log | awk '{print $NF}' > losses.txt
# grep keeps only lines with "loss:", awk prints the last field,
# > saves the numbers to a file
```

**The Unix philosophy**: small tools, each doing one thing well, composed. `awk` is the little text-processing workhorse you'll see in pipelines (`$NF` = last field, `$1`, `$2` = fields). You don't need to write awk programs — you need to recognize it in the wild and read it at a glance.

---

## 10.3 — Permissions, Processes & Environment Variables

### Permissions

Every file on Linux has an owner and a set of permission bits. `ls -l` shows them:

```bash
ls -l train.py
# -rwxr-xr-- 1 you users 2048 Mar 19 10:00 train.py
#  ^^^       owner: read, write, execute
#     ^^^    group: read, execute
#        ^^  everyone else: read only
```

The three letters are **r** (read), **w** (write), **x** (execute). The `d` in front means directory; a directory needs `x` to be entered (searchable) and `r` to list its contents. The file also has an **owner** and a **group** — that's the `you users` part of the listing. `chown you:team file` changes ownership (needs `sudo`).

Two commands fix almost every "Permission denied":

```bash
chmod +x train.sh        # make a script executable
chmod 755 deploy.sh      # owner: full; others: read+execute
chmod 644 config.yaml    # owner: read+write; others: read only
```

And `sudo` runs a single command as root — use it only when a command actually needs it, not for everything.

### Processes

Every running program is a **process** with a unique ID (PID):

```bash
ps aux | grep python     # find running Python processes
htop                     # interactive process viewer (q to quit)
kill 12345               # gracefully stop PID 12345
kill -9 12345            # force kill — only when graceful fails
nvidia-smi               # GPU processes and memory (if you have an NVIDIA GPU)
watch -n1 nvidia-smi     # re-run every second — live GPU monitor
```

Two useful background tricks for long jobs:

```bash
python train.py &                # run in the background (dies with the terminal)
nohup python train.py > train.log 2>&1 &   # survive terminal close; log to file
jobs                    # list background jobs
fg %1                   # bring job 1 back to the foreground
```

For anything longer than a few minutes, use `tmux` instead (see 10.4) — it survives disconnects and lets you reattach.

### Environment variables

Environment variables are named values inherited by every program you launch. They're how secrets, config, and API keys reach your code (you met `.env` in Step 8.5):

```bash
echo $PATH              # view a variable
env                     # list all of them
export MY_KEY=abc123    # set one for this terminal session

# Before a training run: is CUDA visible?
env | grep -i cuda
```

A variable set with `export` only lives for that terminal session. To make it permanent, add the line to your shell config (`~/.bashrc` for bash, `~/.zshrc` for zsh).

---

## 10.4 — SSH, scp & Working on a Remote Machine

### SSH: your doorway to another machine

**SSH** (Secure Shell) is an encrypted protocol that lets you run commands on a remote machine as if you were sitting at it. This is how you'll use every rented GPU box:

```bash
ssh user@gpu-box-ip              # connect
ssh -i ~/.ssh/my_key user@host   # with a specific key file

# Once connected, you're just in a shell. Everything from 10.1–10.3 works.
```

Your public key lives at `~/.ssh/id_ed25519.pub` (generate one with `ssh-keygen` if you don't have it). Cloud providers ask for that key so you can log in without a password.

### Transferring files

```bash
scp model.pt user@gpu-box:~/models/        # local → remote
scp user@gpu-box:~/results/metrics.json .  # remote → local
scp -r user@gpu-box:~/data/ ./local-dir/   # whole directory

rsync -avz --progress ./data/ user@gpu-box:~/data/   # sync a directory
```

**Use `rsync` over `scp` for anything large.** rsync only transfers the bytes that changed and resumes after interruptions — invaluable for moving datasets and checkpoints over flaky connections.

### Port forwarding: remote services, local browser

```bash
ssh -L 8888:localhost:8888 user@gpu-box
# now open http://localhost:8888 in YOUR browser — it tunnels to the remote box
```

This is how you use Jupyter or TensorBoard running on a remote machine.

### tmux: don't let your training die

When you SSH in and your laptop closes, your session dies — and so does your training. **tmux** solves this: it runs terminal sessions as background services you can detach from and reattach to later:

```bash
tmux new -s train        # start a session named "train"
# ... start training, then:
# Ctrl+B, then d         # detach — training keeps running
tmux ls                  # list sessions
tmux attach -t train     # reattach
# Inside: Ctrl+B % splits vertically, Ctrl+B " splits horizontally,
# Ctrl+B + arrow keys moves between panes
```

A typical training setup: one tmux session, three panes — training in one, `watch -n1 nvidia-smi` in another, `tail -f train.log` in the third.

### SSH config: stop typing the same flags

```bash
# ~/.ssh/config
Host gpu
    HostName 192.168.1.100
    User ubuntu
    IdentityFile ~/.ssh/gpu_key
# then just: ssh gpu
```

---

## 10.5 — WSL on Windows — Why Your Dev Environment Should Be Linux

### The problem it solves

Your roadmap assumes Linux. Paths start at `/`, commands live in `$PATH`, tools like `grep` and `rsync` are native. Windows (cmd/PowerShell) is a different world. **WSL2** gives you a real Linux kernel running alongside Windows — no dual-boot, no VM.

```bash
# In PowerShell (as admin):
wsl --install -d Ubuntu-24.04
# restart, then open Ubuntu from the Start menu
```

Everything in this step works inside WSL. Your Windows files are reachable at `/mnt/c/Users/YourName/`, and with an NVIDIA driver installed on the Windows side, GPU/CUDA work passes through into WSL.

### Windows vs. Linux: the gotchas

| Windows habit | Linux reality | Note |
|---|---|---|
| `dir` | `ls` | PowerShell has `ls` as an alias, but the flags differ |
| `C:\Users\you` | `/home/you` | different root, different separators |
| Explorer, GUI | `cat`, `less`, no GUI | on a remote box there is no Explorer |
| Line endings `\r\n` | `\n` | CRLF breaks bash scripts — `dos2unix` fixes them |
| Case-insensitive paths | case-sensitive | `Model.py` and `model.py` are different files |

The point isn't that Windows is bad — it's that the machines you deploy to, and the boxes you rent, run Linux. WSL makes your *local* machine match your *production* machine.

---

## 10.6 — Shell Scripting Basics: Running a Multi-Step Job Without Babysitting It

### The shell is a programming language

A **shell script** is a file of shell commands, run top to bottom. Any command you type at the prompt works in a script; plus you get variables, conditionals, and loops.

```bash
#!/bin/bash
# The shebang: tells the system this file should run with bash.
# When you encounter it in others' scripts: it's a comment, then
# the interpreter path. Single quotes here are deliberate — see
# "quoting" in the pitfalls.

set -e                # stop on the first error (best default for jobs)
set -u                # fail on unset variables (catches typos)

for i in $(seq 1 10); do
    echo "epoch $i loss: $(( 100 / i ))"
    sleep 1
done > train.log      # redirect the whole loop's output
```

Run it: `chmod +x job.sh` then `./job.sh` (or `bash job.sh`).

### Scripts get three things from the shell

1. **Variables** — `epoch=$i` (note: no spaces around `=`), and `$epoch` or `${epoch}` to read them. Special ones: `$0` (script name), `$1` `$2` (arguments), `$?` (exit code of the last command), `$@` (all arguments).
2. **Globbing** — `*.log` expands to all matching files *before* the command runs. `tail -f logs/*.log` follows every log at once.
3. **Exit codes** — every command ends with a number; `0` means success, anything else is an error. This is how `set -e` and CI pipelines (Step 16) know whether a step passed.

### Production habits worth stealing

These come from Google's Shell Style Guide and general Unix practice — adopt them from day one so you never develop the bad habits:

- **The shell is glue, not an application language.** Shell is for scripts that mostly call other tools and do little data manipulation. When a script passes ~100 lines or grows real logic, rewrite it in Python. "It's just a quick script" scripts grow.
- **`set -euo pipefail` is your friend.** `set -e` stops on the first error, `set -u` fails on unset variables (catches typos), `pipefail` makes a pipeline fail if *any* stage fails instead of only the last one.
- **Errors go to stderr, not stdout.** `echo "something went wrong" >&2` — that way normal output and problems don't mix, and `2>` can separate them.
- **Check exit codes and exit non-zero on failure.** A script that "fails" while returning 0 breaks every pipeline and CI job that depends on it.
- **Run ShellCheck** (shellcheck.net) on your scripts. It's a linter that catches the classic quoting/expansion bugs before they bite you.
- **Prefer `$(command)` over backticks** for command substitution — it nests cleanly: `result="$(python train.py)"`.

### A realistic training-job script

```bash
#!/bin/bash
set -euo pipefail      # strict mode: fail fast, fail loudly

mkdir -p logs
python train.py --epochs 100 --lr 1e-4 > logs/train.log 2>&1
python evaluate.py --checkpoint logs/best.pt >> logs/train.log
echo "Job finished at $(date)"
```

Run it with `nohup ./train_job.sh &` or inside tmux, and you've automated an entire experiment.

### Quoting matters

- **Single quotes** `'...'`: literal — `'$PATH'` is the characters `$PATH`, not the variable.
- **Double quotes** `"..."`: expands — `"path is $PATH"` inserts the value.
- **No quotes**: word splitting — `echo hello world` passes two arguments.
- **`"$@"`** preserves each argument as-is, even with spaces: `for f in "$@"; do ...` is the safe way to loop over arguments. Unquoted `$@` splits on spaces and mangles filenames.

This is the classic source of "it works interactively but not in my script."

---

## Pitfalls

1. **`rm -rf` has no undo.** One mistyped path and a dataset is gone. When deleting anything with a wildcard, run `ls` with the same pattern first.

2. **Spaces in filenames break unquoted commands.** `rm My File.txt` deletes two files. Quote: `rm "My File.txt"`, or escape: `My\ File.txt`.

3. **`>` overwrites without asking.** `python train.py > results.txt` destroys whatever was in `results.txt`. Use `>>` to append; back up before overwriting experiment outputs.

4. **`sudo` doesn't fix redirects.** `sudo echo 3 > /sys/...` fails because the *shell* (not root) opens the file. Use `echo 3 | sudo tee /sys/...`.

5. **A script won't run with `./script.sh`** — that's usually missing execute permission (`chmod +x script.sh`), or a missing/incorrect shebang line. `bash script.sh` always works as a fallback.

6. **A script that "works in the terminal" fails as a script** — usually quoting, or it relies on an alias you defined interactively (aliases aren't loaded in scripts). Use the full command in scripts.

7. **Your training dies when you close your laptop.** Any long-running job over SSH needs `tmux` or `nohup`; otherwise the connection drop kills the process.

8. **CRLF line endings break bash scripts.** If you edit scripts on Windows and get `$'\r': command not found`, run `dos2unix script.sh`.

---

## Quick Reference

| Task | Command |
|---|---|
| Where am I? | `pwd` |
| List files | `ls -la` |
| Go home | `cd ~` |
| Create directory | `mkdir -p a/b/c` |
| Copy / move / delete | `cp -r` / `mv` / `rm -rf` |
| Read / follow a file | `cat` / `less` / `tail -f` |
| Search inside files | `grep -r` |
| Find files | `find . -name "*.py"` |
| Count lines | `wc -l` |
| First / last lines | `head -20` / `tail -20` |
| Redirect stdout | `>` (overwrite), `>>` (append) |
| Redirect stderr | `2>` / `2>&1` |
| Pipe | `\|` |
| Make executable | `chmod +x file.sh` |
| Run as root | `sudo command` |
| Find processes | `ps aux \| grep name` |
| Kill a process | `kill PID` / `kill -9 PID` |
| Live GPU monitor | `watch -n1 nvidia-smi` |
| Background, disconnect-proof | `nohup cmd > log 2>&1 &` |
| Long job sessions | `tmux new -s name` / `tmux attach -t name` |
| Connect to remote | `ssh user@host` |
| Copy file remote | `scp file user@host:/path/` |
| Sync directories | `rsync -avz ./src/ user@host:/path/` |
| Set a variable | `export NAME=value` |
| View a variable | `echo $NAME` |
| Search history | Ctrl+R |

---

## Theory Summary

**The shell is a programming language for composing programs.** Every command is a small program; arguments and `$PATH` control which program runs; stdin/stdout/stderr are the interfaces; `>` and `|` rewire them. The terminal isn't a different way to use the computer — it's the same way every tool you'll use was designed to be driven.

**Files, processes, and streams are the universal currency.** On Linux everything is a file, everything running is a process with a PID, and every program talks through three streams. Learn those three facts and most commands stop being memorized incantations.

**Small tools, composed, beat big tools.** `grep` + `awk` + `wc` in a pipe is often better than any single "log analyzer." This philosophy — one thing per program, connect them with pipes — is the Unix design you'll see echoed everywhere, from Docker's layered design to Unix socket APIs in LLM tooling.

**The remote machine is Linux, and so should your dev environment be.** SSH, scp, rsync, and tmux are the survival kit for rented GPU boxes. WSL makes your Windows laptop behave like one, so what you practice locally is what you run in production.

**Scripts turn babysitting into automation.** A shell script with `set -euo pipefail` is a repeatable, auditable version of what you'd otherwise type by hand — and it's the smallest unit of the "multi-step job" pattern that CI pipelines (Step 16) scale up.

**The shell is glue, and knows it.** Shell's strength is composing other programs, not being a general language — when a script outgrows "call these tools in order," the production move is Python, not cleverer bash. Knowing when *not* to use the shell is part of knowing the shell.

---

## Deliverable

**`Phase 0/scripts/project_scout.sh`** — a shell script that inspects a project directory and prints a one-page report:

- counts of `.py`, `.md`, `.json` files (`find` + `wc`)
- total lines of Python (`find` + `xargs wc -l`)
- the 5 largest files by size (`find` + `du` + `sort`)
- any lines containing `TODO` or `FIXME` across source files (`grep -rn`)

Run it on this repo (`./project_scout.sh .`) and commit the script. It's the first script you'll reuse constantly as the course generates more and more code — and it exercises every subtopic in this step: filesystem navigation, pipelines, process-less text processing, and script mechanics. (No permissions/SSH/WSL in the artifact itself — those are exercised in the practice exercises above.)
