#!/usr/bin/env python3
import os
import inspect
from collections import defaultdict
import json
import logging
import subprocess as sp

HOME = os.path.abspath(os.path.dirname(__file__))

class Command:
    def __init__ (self, target, action):
        self.target = target
        self.action = action
        self.parser = None
        self.impl = None 
        pass

class CommandRegister:
    def __init__ (self, command):
        self.command = command

    def __call__ (self, func):
        sig = inspect.signature(func)
        positional = []
        for name, param in sig.parameters.items():
            positional.append(name)
        assert positional[-1] == 'args'
        positional.pop()
        self.command.impl = func
        self.command.positional = positional
        return func

class App:
    def __init__ (self):
        self.commands = defaultdict(lambda: {})

    def register (self, func):
        target, action = func.__name__.split('_')
        cmd = Command(target, action)
        cmd.parser = func
        self.commands[target][action] = cmd
        return CommandRegister(cmd)

    def addParsers (self, parser):
        subs = parser.add_subparsers(help='', dest='target')
        for target, actions in self.commands.items():
            target_parser = subs.add_parser(target, help='')
            target_subs = target_parser.add_subparsers(help='', dest='action')
            for action, command in actions.items():
                action_parser = target_subs.add_parser(action, help='')
                command.parser(action_parser)

    def run (self):
        import argparse
        parser = argparse.ArgumentParser(prog='sandbox')
        self.addParsers(parser)
        args, unknown = parser.parse_known_args()
        target = args.target
        action = args.action
        command = self.commands[target][action]
        assert len(unknown) == len(command.positional)
        unknown.append(args)
        command.impl(*unknown)

app = App()

def back_quote (cmd):
    return sp.check_output(cmd, shell=True).decode('ascii').strip()

class Template:
    def __init__ (self, path=None):
        if not path is None:
            with open(path, 'r') as f:
                self.spec = json.load(f)
                return
        self.spec = {
                'python3': back_quote('python3 --version')
                }
        pass

    def dump (self, path):
        with open(path, 'w') as f:
            json.dump(self.spec, f, indent=4)

    def check (self, path):
        target = Template(path)
        for name, tmpl_value in target.items():
            env_value = self.spec.get(name, None)
            if tmpl_value != env_value:
                logging.error("f{name} has environmnet value {env_value} != template value {tmpl_value}")

@app.register
def tmpl_create (parser):
    parser.add_argument('--force', action='store_true')
    pass

@tmpl_create
def tmpl_create_impl (name, args):
    out_dir = os.path.join('tmpl', name, 'packages')
    os.makedirs(out_dir, exist_ok=args.force)
    tmpl = Template()
    tmpl.dump(os.path.join('tmpl', name, 'meta.json'))
    with open(os.path.join('tmpl', name, 'install.sh'), 'w') as f:
        f.write('''#!/bin/bash

TARGET=$1
SOURCE="${BASH_SOURCE[0]}"
HOME=`dirname "$SOURCE"`

if [ -z "$TARGET" ]
then
        exit
fi

. "$TARGET"/load.sh
pip3 install "$HOME/packages"/*
''')

@app.register
def venv_create (parser):
    parser.add_argument('-t', '--tmpl', type=str, required=True)
    parser.add_argument('--force', action='store_true')

@venv_create
def venv_create_impl (name, args):
    tmpl_dir=os.path.join(HOME, 'tmpl', args.tmpl)
    assert os.path.exists(tmpl_dir)
    os.makedirs('venv', exist_ok=True)
    out_dir = os.path.join('venv', name)
    assert (not os.path.exists(out_dir)) or args.force
    os.makedirs(out_dir, exist_ok=True)
    sp.call(f'python3 -m venv "{out_dir}"', shell=True)

    load_path = os.path.join(out_dir, 'load.sh')
    with open(load_path, 'w') as load:
        load.write(r'''
SOURCE="${BASH_SOURCE[0]}"
echo Loading sandbox $SOURCE
SANDBOX_HOME=`dirname "$SOURCE"`
SANDBOX_NAME=`basename "$SANDBOX_HOME"`
export SANDBOX_HOME
export SANDBOX_NAME
unset PYTHONPATH
unset LD_LIBRARY_PATH
unset CUDA_TOOLKIT_ROOT_DIR
unset CUDA_HOME
env | grep SANDBOX
. "$SANDBOX_HOME/bin/activate"
PS1="[$SANDBOX_NAME]\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$"
''')
    meta = Template()
    meta.dump(os.path.join('venv', name, 'meta.json'))
    sp.call(f'bash "{tmpl_dir}/install.sh" "{out_dir}"', shell=True)
    pass

@app.register
def venv_update (parser):
    pass

@venv_update
def venv_update_impl (name, args):
    out_dir = os.path.join('venv', name)
    assert not os.path.exists(out_dir)
    sp.call(f'python3 -m venv "{out_dir}"', shell=True)
    meta = Meta()
    meta.dump(os.path.join('venv', name, 'meta.json'))
    pass

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run()

